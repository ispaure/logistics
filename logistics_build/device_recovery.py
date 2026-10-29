"""Independently verify retained iOS output without rewriting a failed build."""
import argparse
from dataclasses import replace
from pathlib import Path
import subprocess

from build_manager.history import load_run
from commonUtils.runtime.streams import file_sha256
from logistics_build.manager_devices import check_source, read_json, save_json, BUNDLE


def retained_build(output):
    output = Path(output).resolve()
    plan, report = load_run(output / 'result.json')
    if report['status'] not in {'failed', 'cancelled'}:
        raise ValueError('Recovery requires a stopped failed or cancelled run.')
    builds = [phase for phase in plan.phases if phase.id == 'ios.devices.prepare-device-app']
    if len(builds) != 1 or len(plan.phases) != 3:
        raise ValueError('Recovery supports only the standalone single-device iOS plan.')
    phase = builds[0]
    rows = {row['id']: row for row in report['phases']}
    if rows[phase.id]['status'] not in {'failed', 'cancelled'}:
        raise ValueError('The original preparation must remain failed or cancelled.')
    if any(rows.get(p.id, {}).get('status') != 'skipped' for p in plan.phases if p.id != phase.id):
        raise ValueError('Reconcile admitted device operations before recovery.')
    argv = phase.argv
    if tuple(argv[1:4]) != ('-m', 'logistics_build.manager_devices', 'prepare'):
        raise ValueError('The retained build is not the owning device preparation command.')
    recipe = Path(argv[argv.index('--recipe') + 1])
    if file_sha256(recipe) != argv[argv.index('--sha256') + 1]:
        raise ValueError('The original preparation recipe changed.')
    data = read_json(recipe)
    # Journey wrappers may add platform-plan metadata; every captured recipe
    # input must still match the original reviewed source without substitution.
    if (data['platform'] != 'ios' or data.get('shared_report')
            or any(plan.source.get(key) != value for key, value in data['source'].items())):
        raise ValueError('Recovery requires the exact captured standalone iOS source.')
    check_source(data)
    return plan, phase, data


def make_plan(output):
    plan, build, _ = retained_build(output)
    helper = Path(__file__).resolve()
    command = (build.argv[0], str(helper), 'verify', '--run', str(Path(output).resolve()),
               '--helper-sha256', file_sha256(helper))
    verified = replace(build, argv=command, timeout=300,
        label='Verify retained iOS app after failed build',
        description='Fresh source, provisioning and signature checks; original build remains failed.')
    return replace(plan, operation='Recover and install retained iOS device app',
                   phases=tuple(verified if phase.id == build.id else phase for phase in plan.phases))


def verify(output, helper_digest):
    if file_sha256(Path(__file__)) != helper_digest:
        raise ValueError('Recovery helper changed; review a new plan.')
    plan, _, data = retained_build(output)
    workspace = Path(data['workspace'])
    app = workspace / 'build/physical-device/Build/Products/Debug-iphoneos/Logistics Mobile.app'
    if file_sha256(data['config']) != data['config_sha256']:
        raise ValueError('Device signing configuration changed.')
    from mobile_build.tools import stage
    from logistics_build.build_retention import scratch
    with scratch() as temporary:
        expected = stage(Path(data['root']), temporary / 'payload', allow_dirty=True)
    if read_json(app / 'app/mobile/source.json') != expected:
        raise ValueError('Retained app does not contain the exact captured source.')
    from mobile_build.deployment import device_tools as ios
    config = read_json(data['config'])
    identities = [ios.validate_app(app, config['team_id'], target['id']) for target in data['targets']]
    if not config.get('signing_identity') or any(value != config['signing_identity'] for value in identities):
        raise ValueError('Existing signing identity differs; recovery cannot re-sign the app.')
    package = workspace / 'app.zip'
    subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(package)],
                   check=True, timeout=60)
    data.update(identity=identities[0], package=str(package), package_sha256=file_sha256(package), bundle_id=BUNDLE,
        recovery=dict(original_run=str(Path(output).resolve()), original_plan=plan.identity,
                      original_result_sha256=file_sha256(Path(output) / 'result.json'),
                      scope='Independent exact-source and recursive signing validation; original build remains failed.'))
    check_source(data)
    save_json(workspace / 'prepared.json', data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'verify'))
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--helper-sha256')
    args = parser.parse_args()
    if args.action == 'plan':
        if not args.output:
            parser.error('Planning requires --output for a new recovery plan.')
        plan = make_plan(args.run)
        plan.save(args.output)
        print(plan.identity)
    else:
        if not args.helper_sha256:
            parser.error('Verification requires the reviewed helper hash.')
        verify(args.run, args.helper_sha256)


if __name__ == '__main__':
    main()
