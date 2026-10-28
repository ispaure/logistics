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
    'logistics_build/guest_attempts.py', 'logistics_build/guest_manager.py',
    'logistics_build/windows_backend.py', 'logistics_build/vm_backend.py', 'logistics_build/guest_results.py',
    'Python/tests/tooling/test_guest_results.py',
    'Python/tests/tooling/test_guest_attempts.py', 'Python/tests/tooling/test_guest_manager.py',
    'build-manager-dependency.json', 'logistics_build/continuation_inputs.py',
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


def verify_native_applicability(root, output, plan_identity, current, *, expect_identity=None):
    """Verify native inventories/toolchains separately from desktop/engine gates.

    Missing mutable QA binaries are explicitly unavailable for deployment. Their
    original tested digest and retained reports do not recreate those bytes.
    """
    import os
    from pathlib import Path
    from build_manager.history import load_run
    from build_manager.workflows import verify_artifacts
    from commonUtils.runtime.streams import file_sha256
    from logistics_build.manager_suites import native_cases, same_source
    root, output = Path(root), Path(output)
    plan, report = load_run(output/'result.json')
    if plan.identity != plan_identity or plan.source.get('dirty') is not False:
        raise ValueError('Native continuation requires the exact original clean source plan.')
    comparison = verify_current(root, plan.source['logistics_commit'], current)
    rows = {row['id']: row for row in report['phases']}
    phases = {phase.id: phase for phase in plan.phases}
    evidence = {}
    checks = []
    def artifact(step):
        row = rows.get(step, {})
        if row.get('status') != 'passed':
            raise ValueError('Original native prerequisite did not pass: '+step)
        verify_artifacts(row)
        paths = [Path(a['path']) for a in row.get('artifacts', []) if a['path'].endswith('.json')]
        if len(paths) != 1:
            raise ValueError('Native step needs exactly one declared JSON report: '+step)
        evidence[str(paths[0])] = file_sha256(paths[0])
        return json.loads(paths[0].read_text())
    def run(argv, phase):
        return subprocess.check_output(argv, env=dict(os.environ, **phase.environment),
            text=True, stderr=subprocess.STDOUT, timeout=30).strip()
    for target, names in (('ios', ('iphone', 'duo', 'ipad', 'ios-runtime')),
                          ('android', ('android-native', 'android-runtime'))):
        for name in names:
            step = target+'.validation.'+name
            data = artifact(step)
            if (not same_source(data.get('report', data).get('source', {}), plan.source)
                    or any(case['status'] != 'passed' for case in native_cases(
                        data, root, target, runtime=name.endswith('runtime')))
                    or target == 'ios' and data.get('owned_simulator_removed') is not True):
                raise ValueError('Native source, complete inventory or cleanup is unverified: '+step)
            if target == 'ios':
                command = phases[step].argv
                if '--' in command:
                    command = command[command.index('--')+1:]
                for flag, field in (('--model', 'model'), ('--runtime', 'runtime')):
                    if flag not in command or data.get(field) != command[command.index(flag)+1]:
                        raise ValueError('Native simulator identity differs from the selected plan: '+step)
            checks.append(dict(step=step, inventory_verified=True))
        step = target+'.validation.'+target+'-build'
        build = artifact(step)
        phase = phases[step]
        key = build['key']
        if not same_source(key['source'], plan.source):
            raise ValueError('Native build source differs from tested source.')
        if target == 'ios':
            from logistics_build.ios_backend import bundle_digest
            actual = dict(xcode=run(['xcodebuild', '-version'], phase),
                          sdk=run(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-build-version'], phase),
                          briefcase=run([phase.argv[0], '-m', 'briefcase', '--version'], phase))
            matches = actual == key['toolchain']
            binary = Path(build['app'])
            available = binary.is_dir() and bundle_digest(binary) == build['bundle_sha256']
        else:
            from logistics_build.android_backend import sdk_build_identity
            # SDK identity uses environment references; restore the caller exactly.
            previous = dict(os.environ)
            try:
                os.environ.update(phase.environment)
                sdk = sdk_build_identity()
            finally:
                os.environ.clear()
                os.environ.update(previous)
            matches = (sdk == key['sdk'] and run([str(Path(phase.environment['JAVA_HOME'])/'bin/java'),
                       '-version'], phase) == key['java'] and
                       run([phase.argv[0], '-m', 'briefcase', '--version'], phase) == key['briefcase'])
            binary = Path(build['apk'])
            available = binary.is_file() and file_sha256(binary) == build['apk_sha256']
        if not matches:
            raise ValueError('Native build toolchain changed: '+target)
        checks.append(dict(step=step, toolchain_verified=True, tested_binary_available=available,
                           tested_binary_digest=build.get('bundle_sha256', build.get('apk_sha256'))))
        cleanup = target+'.validation.'+('ios-runtime-cleanup' if target == 'ios' else 'android-cleanup')
        for step in (cleanup, target+'.validation.release-acceptance'):
            if rows.get(step, {}).get('status') != 'passed':
                raise ValueError('Native cleanup or acceptance did not pass: '+step)
            verify_artifacts(rows[step])
    receipt = dict(schema=1, plan_identity=plan.identity, current_commit=current,
                   original_report_sha256=file_sha256(output/'result.json'), comparison=comparison,
                   checks=checks, evidence=evidence, authorizes_reuse=False, fresh_execution=False,
                   remaining_checks=['original check closure/log binding', 'reviewed engine changes',
                                     'fresh changed desktop fixture validation', 'complete desktop coverage'])
    receipt['identity'] = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
    if expect_identity is not None and receipt['identity'] != expect_identity:
        raise ValueError('Native applicability review changed; inspect the new identity.')
    return receipt


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--previous', required=True)
    parser.add_argument('--current', required=True)
    parser.add_argument('--require-current-equivalent', action='store_true')
    parser.add_argument('--expect-identity')
    parser.add_argument('--native-output', type=Path)
    parser.add_argument('--native-plan-identity')
    args = parser.parse_args()
    if bool(args.native_output) != bool(args.native_plan_identity):
        parser.error('--native-output and --native-plan-identity must be supplied together')
    if args.native_output and not args.require_current_equivalent:
        parser.error('Native applicability requires --require-current-equivalent')
    if args.expect_identity and not args.require_current_equivalent:
        parser.error('--expect-identity requires --require-current-equivalent')
    if args.native_output:
        original = inventory(args.root, args.previous)  # Validate explicit exact previous SHA too.
        report = verify_native_applicability(args.root, args.native_output, args.native_plan_identity,
                                            args.current, expect_identity=args.expect_identity)
        if report['comparison']['previous_commit'] != args.previous or not original:
            parser.error('Native source plan differs from --previous')
    else:
        report = (verify_current(args.root, args.previous, args.current, expect_identity=args.expect_identity)
                  if args.require_current_equivalent else assess(args.root, args.previous, args.current))
    print(json.dumps(report, indent=2))
