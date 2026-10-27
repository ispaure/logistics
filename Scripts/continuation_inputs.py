"""Read-only application input comparison for a retained-run continuation review.

This is an applicability assessment, not a passed gate or authorization to reuse.
Execution/toolchain/platform and engine evidence must be verified separately.
"""
import hashlib
import json
import re
import subprocess


# These owners change guest orchestration or its tests, never application/native
# build inputs. The manager pin is reported independently, not treated as equal.
ORCHESTRATION = frozenset({
    'Scripts/guest_attempts.py', 'Scripts/guest_manager.py',
    'Scripts/windows_backend.py', 'Scripts/vm_backend.py',
    'Python/tests/tooling/test_guest_attempts.py', 'Python/tests/tooling/test_guest_manager.py',
    'build-manager-dependency.json', 'Scripts/continuation_inputs.py',
    'Python/tests/tooling/test_continuation_inputs.py',
})


def inventory(root, revision):
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Continuation inputs require an exact commit SHA.')
    result = subprocess.run(['git', '-C', str(root), 'ls-tree', '-r', '-z', revision],
                            capture_output=True, check=True, timeout=30)
    rows = {}
    for entry in result.stdout.split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        mode, kind, digest = metadata.decode('ascii').split()
        rows[name.decode('utf-8')] = dict(mode=mode, kind=kind, digest=digest)
    if not rows:
        raise ValueError('Continuation commit has no source inventory.')
    return rows


def assess(root, previous, current):
    before, after = inventory(root, previous), inventory(root, current)
    def application(rows):
        return {name: row for name, row in rows.items()
                if name not in ORCHESTRATION and not name.startswith('docs/')}
    old, new = application(before), application(after)
    changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    def fingerprint(rows):
        return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(schema=1, previous_commit=previous, current_commit=current,
                application_inputs_equal=old == new,
                previous_application_inputs=fingerprint(old), current_application_inputs=fingerprint(new),
                changed_paths=changed,
                changed_application_paths=[name for name in changed if old.get(name) != new.get(name)],
                previous_manager_pin=before.get('build-manager-dependency.json'),
                current_manager_pin=after.get('build-manager-dependency.json'),
                authorizes_reuse=False,
                remaining_checks=['original passed evidence and cleanup', 'artifact integrity',
                                  'platform and toolchain identity', 'reviewed execution engine changes'])


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--previous', required=True)
    parser.add_argument('--current', required=True)
    args = parser.parse_args()
    print(json.dumps(assess(args.root, args.previous, args.current), indent=2))
