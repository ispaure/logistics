"""Execute an explicitly selected trusted local plan; adapters own its policy."""
import argparse
import json
from pathlib import Path
import signal
from threading import Event

from .executor import Executor
from .models import Plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    cancelled = Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: cancelled.set())
    def event(value):
        print(json.dumps(value), flush=True)
    try:
        report = Executor(cancelled=cancelled, event=event).run(
            Plan.load(args.plan), args.output, confirmed=args.confirm)
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps(dict(type='error', error=str(error))), flush=True)
        return 1
    return int(report['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
