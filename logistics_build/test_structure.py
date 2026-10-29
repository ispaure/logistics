"""Project-owned test roots and source-only preflight for every supported runner."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def inventory(root=ROOT):
    root = Path(root).resolve()
    sys.path.insert(0, str(root / 'Python'))
    from commonUtils.testing.stages import validate
    declaration = json.loads((root / 'test-structure.json').read_text())
    if (not isinstance(declaration, dict) or declaration.get('schema') != 1
            or not isinstance(declaration.get('roots'), list) or not declaration['roots']):
        raise ValueError('Expected test structure schema 1 and nonempty roots')
    paths, owners = [], {}
    for row in declaration['roots']:
        if (not isinstance(row, dict) or set(row) != {'owner', 'directory', 'patterns'}
                or not isinstance(row['owner'], str) or not row['owner']
                or not isinstance(row['directory'], str) or not row['directory']
                or Path(row['directory']).is_absolute()
                or not isinstance(row['patterns'], list) or not row['patterns']
                or any(not isinstance(pattern, str) or not pattern or '/' in pattern or '\\' in pattern
                       for pattern in row['patterns'])):
            raise ValueError('Each test root requires an owner, relative directory and filename patterns')
        directory = root / row['directory']
        if not directory.is_dir() or not directory.resolve().is_relative_to(root):
            raise ValueError('Missing or escaping test root: ' + row['directory'])
        selected = sorted({p for pattern in row['patterns'] for p in directory.rglob(pattern) if p.is_file()})
        if not selected:
            raise ValueError('Empty declared test root: ' + row['directory'])
        for path in selected:
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('Linked/escaping test source: ' + str(path))
            if path in owners:
                raise ValueError('Duplicate test root coverage: ' + str(path))
            owners[path] = row['owner']
        paths.extend(selected)
    rows = validate(paths)
    return [dict(path=r.path.relative_to(root).as_posix(), owner=owners[r.path],
                 stage=r.default.value, cases=r.inventory()) for r in rows]


def run_bridge(rows, profile, mode, fail_fast):
    from commonUtils.testing.stages import PROFILES, TestStage
    bridge = ROOT / 'mobile_build/rclone_bridge'
    failed = False
    for stage in PROFILES[profile]:
        selected = [r for r in rows if r['path'].endswith('_test.go') and r['stage'] == stage.value]
        if not selected:
            continue
        names = [name for row in selected for name in re.findall(
            r'^func (Test\w+)\(', (ROOT / row['path']).read_text(), re.M)]
        if not names:
            raise ValueError('No Go test functions in selected stage: ' + stage.value)
        command = ['go', 'test', './...', '-count=1', '-run', '^(' + '|'.join(names) + ')$']
        if fail_fast:
            command.append('-failfast')
        print('Bridge stage: ' + stage.value, flush=True)
        code = subprocess.run(command, cwd=bridge).returncode
        failed |= bool(code)
        if code and (fail_fast or mode == 'fast' and stage is TestStage.SMOKE):
            print('Remaining bridge stages not run after failure.', flush=True)
            break
    return int(failed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--inventory', action='store_true')
    parser.add_argument('--bridge', action='store_true')
    parser.add_argument('--profile', choices=('smoke', 'daily', 'full'), default='full')
    parser.add_argument('--mode', choices=('fast', 'diagnostic'), default='diagnostic')
    parser.add_argument('--fail-fast', action='store_true')
    args = parser.parse_args(argv)
    try:
        rows = inventory()
        if args.inventory:
            print(json.dumps(dict(schema=1, files=rows), indent=2))
        else:
            print('Test structure valid: ' + str(len(rows)) + ' files; ' + str(dict(Counter(r['stage'] for r in rows))))
        if args.bridge:
            return run_bridge(rows, args.profile, args.mode, args.fail_fast)
    except (ValueError, OSError, SyntaxError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
