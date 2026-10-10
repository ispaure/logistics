"""Run a suite with periodic thread tracebacks for stalled platform checks."""
import argparse
import faulthandler
from pathlib import Path
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--traceback-after', type=float, default=60)
    args = parser.parse_args()
    if args.traceback_after <= 0:
        parser.error('--traceback-after must be positive')
    faulthandler.enable()
    faulthandler.dump_traceback_later(args.traceback_after, repeat=True)
    try:
        suite = unittest.defaultTestLoader.discover(str(args.directory))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return int(not result.wasSuccessful())
    finally:
        faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    raise SystemExit(main())
