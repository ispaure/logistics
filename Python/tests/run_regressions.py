"""Run a suite with safe periodic progress and native-crash tracebacks."""
import argparse
import faulthandler
from pathlib import Path
import sys
from threading import Event, Thread
from time import monotonic
import unittest


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
    parser.add_argument('--traceback-after', type=float, default=60,
                        help='Seconds between safe progress reports; crash tracebacks remain enabled')
    args = parser.parse_args()
    if args.traceback_after <= 0:
        parser.error('--traceback-after must be positive')
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
    try:
        suite = unittest.defaultTestLoader.discover(str(args.directory))
        result = unittest.TextTestRunner(verbosity=2, resultclass=ProgressResult).run(suite)
        return int(not result.wasSuccessful())
    finally:
        stopped.set()
        reporter.join(timeout=1)


if __name__ == '__main__':
    raise SystemExit(main())
