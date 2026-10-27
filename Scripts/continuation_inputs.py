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
    'Scripts/windows_backend.py', 'Scripts/vm_backend.py', 'Scripts/guest_results.py',
    'Python/tests/tooling/test_guest_results.py',
    'Python/tests/tooling/test_guest_attempts.py', 'Python/tests/tooling/test_guest_manager.py',
    'build-manager-dependency.json', 'Scripts/continuation_inputs.py',
    'Python/tests/tooling/test_continuation_inputs.py',
})


# Fixture-only changes cannot change native application inputs, but must receive
# fresh desktop validation before any retained desktop coverage is accepted.
DESKTOP_FIXTURES = frozenset({'Python/tests/ide/test_ide_drag.py'})


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
                if name not in ORCHESTRATION | DESKTOP_FIXTURES and not name.startswith('docs/')}
    old, new = application(before), application(after)
    changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    def fingerprint(rows):
        return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(schema=1, previous_commit=previous, current_commit=current,
                application_inputs_equal=old == new,
                previous_application_inputs=fingerprint(old), current_application_inputs=fingerprint(new),
                changed_paths=changed,
                changed_desktop_fixtures=sorted(set(changed) & DESKTOP_FIXTURES),
                changed_application_paths=[name for name in changed if old.get(name) != new.get(name)],
                previous_manager_pin=before.get('build-manager-dependency.json'),
                current_manager_pin=after.get('build-manager-dependency.json'),
                authorizes_reuse=False,
                remaining_checks=['original passed evidence and cleanup', 'artifact integrity',
                                  'platform and toolchain identity', 'reviewed execution engine changes',
                                  'fresh validation for every changed desktop fixture'])


def verify_current(root, previous, current, *, expect_identity=None):
    """Bind an applicability check to the clean current checkout, not a past SHA.

    This is one continuation prerequisite. Desktop fixture validation, engine
    review and retained native evidence remain independently required.
    """
    # Validate exact revisions before using them in any command or comparison.
    report = assess(root, previous, current)
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                   text=True, timeout=30).strip()
    dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'],
                                    text=True, timeout=30)
    if head != current or dirty:
        raise ValueError('Continuation requires the exact clean current checkout.')
    if not report['application_inputs_equal']:
        raise ValueError('Application/native inputs changed; retained coverage is inapplicable.')
    report['current_checkout_verified'] = True
    report['identity'] = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    if expect_identity is not None and report['identity'] != expect_identity:
        raise ValueError('Continuation input review changed; inspect the new identity.')
    return report


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--previous', required=True)
    parser.add_argument('--current', required=True)
    parser.add_argument('--require-current-equivalent', action='store_true')
    parser.add_argument('--expect-identity')
    args = parser.parse_args()
    if args.expect_identity and not args.require_current_equivalent:
        parser.error('--expect-identity requires --require-current-equivalent')
    report = (verify_current(args.root, args.previous, args.current, expect_identity=args.expect_identity)
              if args.require_current_equivalent else assess(args.root, args.previous, args.current))
    print(json.dumps(report, indent=2))
