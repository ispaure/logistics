"""Run a suite with safe periodic progress and native-crash tracebacks."""
import argparse
import faulthandler
from fnmatch import fnmatchcase
import importlib.util
import json
import math
import os
import platform
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic
import unittest
from unittest.mock import patch

# Keep direct CI/standalone invocations on this checkout's shared source.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from regression_timing import TimedResult, TimingReport, default_report, timestamp, emit_progress
from runner_settings import ISOLATED_FILE_TIMEOUT, PROGRESS_INTERVAL
from commonUtils.testing.stages import TestStage, STAGE_ORDER, PROFILES, validate


def run_isolated(directory, pattern, interval, include_patterns=(), report=None, *,
                 stages=STAGE_ORDER, mode='diagnostic', fail_fast=False, timings=None):
    """Validate first, then run isolated files by stage and known duration."""
    modules = sorted(path for path in directory.rglob(pattern)
                     if path.is_file() and all(fnmatchcase(path.name, extra) for extra in include_patterns))
    if not modules:
        raise ValueError('Module isolation requires at least one matching test file.')
    classified = validate(modules)
    durations = {}
    if timings is not None:
        previous = json.loads(Path(timings).read_text())
        if (not isinstance(previous, dict) or not isinstance(previous.get('directory'), str)
                or Path(previous['directory']).resolve() != directory.resolve()
                or previous.get('python') != sys.executable or previous.get('platform') != platform.platform()
                or previous.get('test_environment') != {key: os.environ.get(key) for key in ('QT_QPA_PLATFORM', 'TOGA_BACKEND')}):
            raise ValueError('Timing order requires the same test root, interpreter, platform and backend environment.')
        if not isinstance(previous.get('modules'), list):
            raise ValueError('Timing order requires a report with module durations.')
        for row in previous['modules']:
            if not isinstance(row, dict):
                raise ValueError('Invalid timing module record.')
            if row.get('outcome') != 'passed':
                continue
            seconds = row.get('duration_seconds')
            if (not isinstance(row.get('path'), str) or not isinstance(seconds, (int, float))
                    or not math.isfinite(seconds) or seconds < 0):
                raise ValueError('Invalid successful module duration in timing report.')
            durations[row['path'], row.get('stage')] = seconds
    plan = [(level, row) for level in stages for row in sorted(classified, key=lambda r: (
                durations.get((str(r.path.relative_to(directory)), level.value), 0), str(r.path)))
            if level in {value for _, value, _ in row.cases} or not row.cases and row.default is level]
    if not plan:
        raise ValueError('No tests selected for the requested execution stages.')
    if report is not None:
        report.data.update(stages=[s.value for s in stages], mode=mode, fail_fast=fail_fast,
                           classified_files=[dict(path=str(r.path.relative_to(directory)), stage=r.default.value,
                                                  cases=r.inventory()) for r in classified], not_run=[], coverage_complete=True)
    failed, stop_reason, active_stage, stage_failed = [], '', None, False
    for index, (level, row) in enumerate(plan):
        if active_stage is not None and level is not active_stage:
            if mode == 'fast' and active_stage is TestStage.SMOKE and stage_failed:
                stop_reason = 'Smoke gate failed'
            stage_failed = False
        active_stage = level
        if stop_reason:
            if report is not None:
                report.data['not_run'].extend(dict(file=str(p.path.relative_to(directory)), stage=s.value,
                                                   cases=[case for case in p.inventory() if case['stage'] == s.value],
                                                   reason=stop_reason) for s, p in plan[index:])
                report.data.update(stopped_early=True, coverage_complete=False)
                report.save()
            break
        path = row.path
        started_at = timestamp()
        started = monotonic()
        relative_file = str(path.relative_to(directory))
        print(f'Running isolated test file: {relative_file} [stage={level.value}]', flush=True)
        emit_progress('file_started', name=relative_file, stage=level.value)
        command = [sys.executable, str(Path(__file__).resolve()), str(path.parent),
                   '--pattern', path.name, '--single-file', '--traceback-after', str(interval), '--stage', level.value]
        if fail_fast:
            command.append('--fail-fast')
        with TemporaryDirectory(prefix='logistics-test-timing-') as temporary:
            child_report = Path(temporary) / 'timing.json'
            command.extend(['--report', str(child_report), '--timing-child'])
            try:
                code = subprocess.run(command, timeout=ISOLATED_FILE_TIMEOUT,
                                      env=dict(os.environ, BUILD_MANAGER_TEST_FILE=relative_file)).returncode
                outcome = 'passed' if code == 0 else 'preflight_error' if code == 2 else 'failed'
                if code < 0:
                    outcome = 'crashed'
            except subprocess.TimeoutExpired:
                code, outcome = 124, 'timeout'
            if report is not None:
                records, child_complete = [], False
                if child_report.exists():
                    child_data = json.loads(child_report.read_text(encoding='utf-8'))
                    records, child_complete = child_data['tests'], child_data['complete']
                    report.data['not_run'].extend(dict(r, file=relative_file) for r in child_data.get('not_run', []))
                    if child_data.get('not_run'):
                        report.data.update(stopped_early=True, coverage_complete=False)
                if not child_complete or not records:
                    if code == 0:
                        code, outcome = 2, 'preflight_error'
                    report.data['not_run'].append(dict(
                        file=relative_file, stage=level.value,
                        cases=[case for case in row.inventory() if case['stage'] == level.value
                               and not any(record['id'].endswith('.' + case['case']) for record in records)],
                        reason='Isolated module did not produce complete case evidence: ' + outcome))
                    report.data.update(stopped_early=True, coverage_complete=False)
                report.data['tests'].extend(dict(r, file=relative_file, stage=level.value) for r in records)
                report.data['modules'].append(dict(
                    path=relative_file, stage=level.value, started_at=started_at, finished_at=timestamp(),
                    duration_seconds=monotonic() - started, exit_code=code, outcome=outcome,
                    test_report_available=child_report.exists(), test_report_complete=child_complete))
                report.save()
        elapsed = report.data['modules'][-1]['duration_seconds'] if report is not None else monotonic() - started
        emit_progress('file_finished', name=relative_file, status=outcome, seconds=elapsed, stage=level.value)
        if code:
            failed.append(relative_file)
            stage_failed = True
            print(f'{path.name}: FAIL ({code})', file=sys.stderr, flush=True)
            if fail_fast or mode == 'fast' and code == 2:
                stop_reason = 'Fail-fast failure' if fail_fast else 'Test discovery/preflight failed'
    print(f'Isolated test files: {len({r.path for _, r in plan})}; failures: {len(failed)}', flush=True)
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
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--profile', choices=tuple(PROFILES), default='full')
    selection.add_argument('--stage', choices=[s.value for s in STAGE_ORDER], action='append')
    parser.add_argument('--mode', choices=('fast', 'diagnostic'), default='diagnostic')
    parser.add_argument('--fail-fast', action='store_true')
    parser.add_argument('--inventory', action='store_true', help='Validate and list classification without importing tests')
    parser.add_argument('--timings', type=Path, help='Prior report for deterministic duration ordering on this environment')
    parser.add_argument('--single-file', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--isolate-modules', action='store_true',
                        help='Run each matching test file in a fresh process, including nested directories')
    parser.add_argument('--traceback-after', type=float, default=PROGRESS_INTERVAL,
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
    args.stages = tuple(s for s in STAGE_ORDER if s.value in args.stage) if args.stage else PROFILES[args.profile]
    if args.inventory:
        try:
            rows = validate(args.directory.rglob(args.pattern))
            if not rows:
                raise ValueError('No matching test sources for inventory.')
        except (ValueError, OSError, SyntaxError) as error:
            parser.error(str(error))
        print(json.dumps([dict(file=str(r.path.relative_to(args.directory)), stage=r.default.value, cases=r.inventory()) for r in rows], indent=2))
        return 0
    report = TimingReport(args.report or default_report(args.directory), args.directory,
                          args.pattern, args.isolate_modules, args.junit)
    report.data['include_patterns'] = args.include_pattern
    report.save()
    try:
        code = run_with_report(args, report)
    except ValueError as error:
        report.data.update(preflight_error=str(error), coverage_complete=False,
                           not_run=[dict(file=str(p.relative_to(args.directory)), reason='Preflight failed')
                                    for p in sorted(args.directory.rglob(args.pattern)) if p.is_file()])
        print(str(error), file=sys.stderr, flush=True)
        code = 2
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
                            args.include_pattern, report, stages=args.stages, mode=args.mode,
                            fail_fast=args.fail_fast, timings=args.timings)
    validate(args.directory.rglob(args.pattern))
    # Keep default storage and preferences away from the contributor's live data,
    # including during test discovery. Children running isolated modules create
    # their own scope; ordinary helper subprocesses inherit private cache roots.
    with TemporaryDirectory(prefix='logistics-test-storage-') as temporary:
        root = Path(temporary)
        home = root / 'home'
        home.mkdir()
        environment = {
            'COMMONUTILS_STORAGE_ROOT': str(root / 'shared'),
            # A manager run's profile is input to the suite, never to its fixtures.
            'LOGISTICS_MANAGER_PROFILE': '',
            'LOGISTICS_MANAGER_ACCOUNT_DEFAULTS': '{}',
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
    stage_by_id = {}

    def result_factory(*result_args, **result_kwargs):
        result = TimedResult(*result_args, **result_kwargs)
        result.report = report
        result.status = status
        result.test_stages = stage_by_id
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
        if unittest.defaultTestLoader.errors:
            raise ValueError('Test discovery failed before execution:\n' + '\n'.join(unittest.defaultTestLoader.errors))
        def flatten(tests):
            for test in tests:
                if isinstance(test, unittest.TestSuite):
                    yield from flatten(test)
                else:
                    yield test
        rows = validate(args.directory.rglob(args.pattern))
        by_path = {r.path.resolve(): r for r in rows}
        cases = []
        for test in flatten(suite):
            module = sys.modules.get(type(test).__module__)
            source = getattr(module, '__file__', None)
            owner = by_path.get(Path(source).resolve()) if source else None
            if owner is None:
                raise ValueError('Discovered test belongs to an undeclared source: ' + test.id())
            level = owner.resolve(test)
            if not isinstance(level, TestStage):
                raise ValueError('Invalid runtime test stage: ' + test.id())
            if level in args.stages:
                cases.append((level, test))
        if not cases:
            raise ValueError('No tests selected for the requested execution stages.')
        cases.sort(key=lambda row: (STAGE_ORDER.index(row[0]), row[1].id()))
        stage_by_id.update((test.id(), level.value) for level, test in cases)
        report.data.update(stages=[s.value for s in args.stages], not_run=[],
                           planned_tests=[dict(id=t.id(), stage=s.value) for s, t in cases])
        class StagedSuite(unittest.TestSuite):
            def run(self, result, debug=False):
                for level in args.stages:
                    if result.shouldStop:
                        break
                    unittest.TestSuite(t for s, t in cases if s is level).run(result)
                    if args.mode == 'fast' and level is TestStage.SMOKE and not result.wasSuccessful():
                        break
                return result
        result = unittest.TextTestRunner(verbosity=2, resultclass=result_factory,
                                         failfast=args.fail_fast).run(StagedSuite())
        executed = {r['id'] for r in report.data['tests']}
        report.data['not_run'] = [dict(id=t.id(), stage=s.value, reason='Fail-fast failure' if args.fail_fast else 'Smoke gate or fixture failure')
                                  for s, t in cases if t.id() not in executed]
        report.data['coverage_complete'] = not report.data['not_run']
        report.data['stopped_early'] = bool(report.data['not_run'])
        return int(not result.wasSuccessful())
    finally:
        stopped.set()
        reporter.join(timeout=1)
        if directory_cache is not None:
            directory_cache.close()
            cache_directory.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
