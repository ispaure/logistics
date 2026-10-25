"""Summarize native section timings from an acceptance report or timing cache."""
import argparse
import json
from pathlib import Path


def summarize(value):
    timings = value.get('timings', value.get('summary', value))
    sections = timings['sections']
    return dict(elapsed_s=timings['elapsed_s'],
                sections=sorted(sections, key=lambda row: row['self_s'], reverse=True),
                note=timings['note'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    report = summarize(json.loads(args.report.read_text()))
    print(f"Native suite: {report['elapsed_s']:.3f}s")
    print('Self seconds | Inclusive seconds | Count | Section / panel')
    for row in report['sections']:
        label = row['name'] + (' / ' + row['panel'] if row['panel'] else '')
        print(f"{row['self_s']:12.3f} | {row['elapsed_s']:17.3f} | {row['count']:5} | {label}")
    print(report['note'])


if __name__ == '__main__':
    main()
