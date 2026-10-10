"""Run a suite with periodic thread tracebacks for stalled platform checks."""
import argparse
import faulthandler
import sys
from threading import Event, Thread, get_ident
import traceback
from pathlib import Path
import unittest


def report_stalls(interval, stopped):
    # CPython's native dump_traceback_later watchdog reads live frames without
    # the GIL and can segfault while their metadata is freed (python/cpython#116008).
    # Owned Python frame references preserve periodic diagnostics safely.
    while not stopped.wait(interval):
        print(f'Periodic regression trace ({interval:g}s):', file=sys.stderr, flush=True)
        report_threads()


def report_threads():
    # Release every captured frame before the next wait: keeping a completed
    # test's frame alive can retain its SQLite readers or Qt session locks.
    frames = sys._current_frames()
    frames.pop(get_ident(), None)
    for identifier, frame in frames.items():
        print(f'Thread {identifier}:', file=sys.stderr)
        traceback.print_stack(frame, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--traceback-after', type=float, default=60)
    args = parser.parse_args()
    if args.traceback_after <= 0:
        parser.error('--traceback-after must be positive')
    faulthandler.enable()
    stopped = Event()
    reporter = Thread(target=report_stalls, args=(args.traceback_after, stopped), daemon=True)
    reporter.start()
    try:
        suite = unittest.defaultTestLoader.discover(str(args.directory))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return int(not result.wasSuccessful())
    finally:
        stopped.set()
        reporter.join(timeout=1)


if __name__ == '__main__':
    raise SystemExit(main())
