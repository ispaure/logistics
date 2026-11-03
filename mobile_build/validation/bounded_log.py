"""Keep the latest two bounded log segments from a long-running native probe."""
import argparse
from pathlib import Path
import sys


def capture(source, destination, limit):
    if limit <= 0:
        raise ValueError('Log segment limit must be positive.')
    destination = Path(destination)
    previous = destination.with_name(destination.stem + '.previous' + destination.suffix)
    previous.unlink(missing_ok=True)
    size = 0
    stream = destination.open('wb', buffering=0)
    try:
        while chunk := source.read1(min(limit, 64 * 1024)):
            while chunk:
                if size == limit:
                    stream.close()
                    destination.replace(previous)
                    stream = destination.open('wb', buffering=0)
                    size = 0
                part, chunk = chunk[:limit - size], chunk[limit - size:]
                stream.write(part)
                size += len(part)
    finally:
        stream.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--limit', type=int, default=13_107_200)
    args = parser.parse_args()
    capture(sys.stdin.buffer, args.destination, args.limit)
