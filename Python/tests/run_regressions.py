"""Run a suite with safe periodic progress and native-crash tracebacks."""
import argparse
import faulthandler
from fnmatch import fnmatchcase
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic
import unittest
from unittest.mock import patch

from regression_timing import TimedResult, TimingReport, default_report, timestamp


def run_isolated(directory, pattern, interval, include_patterns=(), report=None):
    """Give independent GUI test files their own QApplication and native state."""
    modules = sorted(path for path in directory.rglob(pattern)
                     if path.is_file() and all(fnmatchcase(path.name, extra) for extra in include_patterns))
    if not modules:
        print('Module isolation requires at least one matching test file.', file=sys.stderr)
        return 1
    failed = []
    for path in modules:
        started_at = timestamp()
        started = monotonic()
        print(f'Running isolated test file: {path.relative_to(directory)}', flush=True)
        command = [sys.executable, str(Path(__file__).resolve()), str(path.parent),
                   '--pattern', path.name, '--single-file', '--traceback-after', str(interval)]
        with TemporaryDirectory(prefix='logistics-test-timing-') as temporary:
            child_report = Path(temporary) / 'timing.json'
            command.extend(['--report', str(child_report), '--timing-child'])
            try:
                code = subprocess.run(command, timeout=300).returncode
                outcome = 'passed' if code == 0 else 'failed'
                if code < 0:
                    outcome = 'crashed'
            except subprocess.TimeoutExpired:
                code = 124
                outcome = 'timeout'
            if report is not None:
                records = []
                child_complete = False
                if child_report.exists():
                    child_data = json.loads(child_report.read_text(encoding='utf-8'))
                    records = child_data['tests']
                    child_complete = child_data['complete']
                relative = str(path.relative_to(directory))
                report.data['tests'].extend(dict(row, file=relative) for row in records)
                report.data['modules'].append({
                    'path': relative, 'started_at': started_at, 'finished_at': timestamp(),
                    'duration_seconds': monotonic() - started, 'exit_code': code,
                    'outcome': outcome, 'test_report_available': child_report.exists(),
                    'test_report_complete': child_complete,
                })
                report.save()
        if code:
            failed.append(str(path.relative_to(directory)))
            print(f'{path.name}: FAIL ({code})', file=sys.stderr, flush=True)
    print(f'Isolated test files: {len(modules)}; failures: {len(failed)}', flush=True)
    if failed:
        print('Failed isolated test files: ' + ', '.join(failed), file=sys.stderr, flush=True)
    return int(bool(failed))


def report_stalls(interval, stopped, status):
    # Native dump_traceback_later can race with frame teardown (CPython#116008).
    # Capturing Python frames in a worker can also retain Qt objects until they
    # are released off the GUI thread. Keep only immutable test names/timestamps.
    while not stopped.wait(interval):
        print(f'Regression progress: {status["test"]} '
              f'({monotonic() - status["started"]:.1f}s in this test; '
              f'{status["completed"]} completed)', file=sys.stderr, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--pattern', default='test*.py', help='unittest discovery filename pattern')
    parser.add_argument('--include-pattern', action='append', default=[],
                        help='Require this additional filename glob (isolated mode only)')
    parser.add_argument('--require-module', action='append', default=[],
                        help='Fail before discovery if this dependency is unavailable')
    parser.add_argument('--single-file', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--isolate-modules', action='store_true',
                        help='Run each matching test file in a fresh process, including nested directories')
    parser.add_argument('--traceback-after', type=float, default=60,
                        help='Seconds between safe progress reports; crash tracebacks remain enabled')
    parser.add_argument('--report', type=Path,
                        help='JSON timing report (default: timestamped file under test-results/test-timings)')
    parser.add_argument('--timing-child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--junit', type=Path, help='Write measured testcase evidence for the build manager')
    args = parser.parse_args()
    if args.traceback_after <= 0:
        parser.error('--traceback-after must be positive')
    if args.include_pattern and not args.isolate_modules:
        parser.error('--include-pattern requires --isolate-modules')
    for name in args.require_module:
        try:
            available = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            available = False
        if not available:
            parser.error(f'Required test dependency is unavailable: {name}. Use the owning suite environment.')
    report = TimingReport(args.report or default_report(args.directory), args.directory,
                          args.pattern, args.isolate_modules, args.junit)
    report.data['include_patterns'] = args.include_pattern
    report.save()
    try:
        code = run_with_report(args, report)
    except BaseException:
        report.save()
        raise
    report.save(complete=True, exit_code=code)
    if not args.timing_child:
        report.summarize()
    return code


def run_with_report(args, report):
    if args.isolate_modules:
        return run_isolated(args.directory.resolve(), args.pattern, args.traceback_after,
                            args.include_pattern, report)
    # Keep default storage and preferences away from the contributor's live data,
    # including during test discovery. Children running isolated modules create
    # their own scope; ordinary helper subprocesses inherit private cache roots.
    with TemporaryDirectory(prefix='logistics-test-storage-') as temporary:
        root = Path(temporary)
        home = root / 'home'
        home.mkdir()
        environment = {
            'COMMONUTILS_STORAGE_ROOT': str(root / 'shared'),
            'XDG_CONFIG_HOME': str(home / '.config'),
            'XDG_CACHE_HOME': str(home / '.cache'),
            'APPDATA': str(home / 'AppData' / 'Roaming'),
            'LOCALAPPDATA': str(home / 'AppData' / 'Local'),
        }
        with patch.dict(os.environ, environment), patch.object(Path, 'home', return_value=home):
            return run_suite(args, report)


def run_suite(args, report):
    # The runner itself lives in Python/tests. A mobile suite can contain the
    # same module name (e.g. test_pdf_reader); discovery must import its own file
    # even when its directory already appears later in PYTHONPATH.
    sys.path.insert(0, str(args.directory.resolve()))
    faulthandler.enable()
    status = {'test': 'test discovery', 'started': monotonic(), 'completed': 0}

    def result_factory(*result_args, **result_kwargs):
        result = TimedResult(*result_args, **result_kwargs)
        result.report = report
        result.status = status
        return result

    stopped = Event()
    reporter = Thread(target=report_stalls, args=(args.traceback_after, stopped, status), daemon=True)
    reporter.start()
    # Browser tests must not contend with a running application's persistent
    # directory index. Keep the singleton identity so already-imported aliases
    # refer to the same private cache throughout this test process.
    from importlib.util import find_spec
    cache_directory = None
    directory_cache = None
    if find_spec('commonUtils') is not None:
        from commonUtils.filesystem.index import directory_cache
        cache_directory = TemporaryDirectory(prefix='logistics-test-index-')
        directory_cache.database = Path(cache_directory.name) / 'index.sqlite3'
        directory_cache._legacy_database = None
    try:
        if args.single_file:
            # Discovery recurses into packages, so it can run another same-named
            # nested module in this process before its own isolated invocation.
            module = Path(args.pattern).stem
            package_root = args.directory.resolve()
            while (package_root / '__init__.py').is_file():
                module = package_root.name + '.' + module
                package_root = package_root.parent
            # Preserve a nested test package's relative fixture imports.
            sys.path.insert(0, str(package_root))
            suite = unittest.defaultTestLoader.loadTestsFromName(module)
        else:
            suite = unittest.defaultTestLoader.discover(str(args.directory), pattern=args.pattern)
        if suite.countTestCases() == 0:
            print('No tests discovered.', file=sys.stderr)
            return 1
        result = unittest.TextTestRunner(verbosity=2, resultclass=result_factory).run(suite)
        return int(not result.wasSuccessful())
    finally:
        stopped.set()
        reporter.join(timeout=1)
        if directory_cache is not None:
            directory_cache.close()
            cache_directory.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
