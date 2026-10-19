"""Run a suite with safe periodic progress and native-crash tracebacks."""
import argparse
import faulthandler
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic
import unittest


def run_isolated(directory, pattern, interval):
    """Give independent GUI test files their own QApplication and native state."""
    modules = sorted(directory.rglob(pattern))
    if not modules or any(path.parent != directory for path in modules):
        print('Module isolation requires a nonempty, flat test directory.', file=sys.stderr)
        return 1
    failed = []
    for path in modules:
        print(f'Running isolated test file: {path.name}', flush=True)
        command = [sys.executable, str(Path(__file__).resolve()), str(directory),
                   '--pattern', path.name, '--traceback-after', str(interval)]
        try:
            code = subprocess.run(command, timeout=300).returncode
        except subprocess.TimeoutExpired:
            code = 124
        if code:
            failed.append(path.name)
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
    parser.add_argument('--isolate-modules', action='store_true',
                        help='Run each test file in a fresh process; requires a flat test directory')
    parser.add_argument('--traceback-after', type=float, default=60,
                        help='Seconds between safe progress reports; crash tracebacks remain enabled')
    args = parser.parse_args()
    if args.traceback_after <= 0:
        parser.error('--traceback-after must be positive')
    if args.isolate_modules:
        return run_isolated(args.directory.resolve(), args.pattern, args.traceback_after)
    # The runner itself lives in Python/tests. A mobile suite can contain the
    # same module name (e.g. test_pdf_reader); discovery must import its own file
    # even when its directory already appears later in PYTHONPATH.
    sys.path.insert(0, str(args.directory.resolve()))
    faulthandler.enable()
    status = {'test': 'test discovery', 'started': monotonic(), 'completed': 0}

    class ProgressResult(unittest.TextTestResult):
        def startTest(self, test):
            status.update(test=test.id(), started=monotonic())
            super().startTest(test)

        def stopTest(self, test):
            status['completed'] += 1
            super().stopTest(test)

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
        suite = unittest.defaultTestLoader.discover(str(args.directory), pattern=args.pattern)
        result = unittest.TextTestRunner(verbosity=2, resultclass=ProgressResult).run(suite)
        return int(not result.wasSuccessful())
    finally:
        stopped.set()
        reporter.join(timeout=1)
        if directory_cache is not None:
            directory_cache.close()
            cache_directory.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
