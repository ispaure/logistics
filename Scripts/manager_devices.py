"""Project-owned saved recipients and exact-artifact, reviewed device installation."""
import argparse
import hashlib
import json
import os
import plistlib
import re
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

from build_manager import Phase, Plan
from build_manager.profiles import save_json
from build_manager.run_fields import selection_ids
from commonUtils.runtime.streams import file_sha256

BUNDLE = 'io.github.ispaure.logisticsmobile'


def read_json(path, default=None):
    path = Path(path)
    if not path.exists() and default is not None:
        return default
    if not path.is_file() or path.stat().st_size > 262144:
        raise ValueError('Device configuration is missing or too large: ' + str(path))
    return json.loads(path.read_text())


def saved_devices(root, only=None):
    """Read only local saved metadata. Never discover, connect, wake or pair devices."""
    mobile = Path(root) / 'mobile_build'
    rows = read_json(mobile / '.tools/test-devices.json', [])
    if not isinstance(rows, list):
        raise ValueError('Saved device inventory must be a list.')
    config = read_json(mobile / '.device.json', {}) if only != 'android' else {}
    if not isinstance(config, dict):raise ValueError('Saved iOS device configuration must be an object.')
    ios_ids = config.get('device_ids') or ([config['device_id']] if config.get('device_id') else [])
    selection_ids(json.dumps(ios_ids))
    result = {'android': {}, 'ios': {}}
    for row in rows:
        if not isinstance(row, dict):continue
        platform = {'Android': 'android', 'iOS': 'ios'}.get(row.get('platform'))
        if not platform or (platform == 'ios' and row.get('id') not in ios_ids):continue
        key = row.get('id'); selection_ids(json.dumps([key]))
        connection = row.get('connection', key); selection_ids(json.dumps([connection]))
        result[platform][key] = dict(id=key, name=str(row.get('name') or key), connection=connection)
    for key in ios_ids:
        selection_ids(json.dumps([key]))
        result['ios'].setdefault(key, dict(id=key, name=key, connection=key))
    return result


def choices(root):
    return {'devices.' + platform: [dict(id=row['id'], label=row['name'] + ' · saved') for row in rows.values()]
            for platform, rows in saved_devices(root).items()}


def selected_devices(root, platform, overrides):
    ids = selection_ids(overrides.get('devices.' + platform, '[]'))
    if not ids:
        raise ValueError('Choose at least one ' + ('Android test device' if platform == 'android' else 'iPhone / iPad') + ' under Delivery → Mobile dev devices.')
    known = saved_devices(root, platform)[platform]
    targets = [dict(known.get(key, dict(id=key, name=key, connection=key))) for key in ids]
    if platform == 'android':
        connections = android_connections(overrides.get('devices.android_connections', '{}'))
        if set(connections) - set(ids):
            raise ValueError('Android connection overrides must name selected device IDs.')
        for target in targets:
            target['connection'] = connections.get(target['id'], target['connection'])
    return targets


def android_connections(value):
    """Validate explicit per-run transports; installation still checks hardware identity."""
    try:
        connections = json.loads(value)
    except (TypeError, ValueError) as error:
        raise ValueError('Android connections must be a JSON object of device ID to ADB serial.') from error
    if not isinstance(connections, dict):
        raise ValueError('Android connections must be a JSON object of device ID to ADB serial.')
    selection_ids(json.dumps(list(connections)))
    selection_ids(json.dumps(list(connections.values())))
    return connections


def make_plan(project, platform, targets, context, revision, *, shared=None):
    from Scripts.build_snapshots import materialize, PRIVATE_RUNTIME_NAMES
    source = context.source(project, revision)
    snapshot = project.private / 'snapshots' / source['fingerprint']
    materialize(project.root, snapshot, revision, expected=source)
    for name in PRIVATE_RUNTIME_NAMES:
        original, link = project.mobile / name, snapshot / 'mobile_build' / name
        if original.exists() and not link.exists():
            link.symlink_to(original, target_is_directory=original.is_dir())
    options = source['effective_settings']['values']
    workspace = project.private / 'workspaces' / 'devices' / platform / uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    recipe = dict(schema=1, platform=platform, source=source, root=str(snapshot), workspace=str(workspace), targets=targets)
    if shared is not None:
        recipe['shared_report'] = shared.artifacts[0]
    if platform == 'ios':
        config = project.mobile / '.device.json'
        data = read_json(config)
        if data.get('bundle_id') != BUNDLE or not data.get('team_id'):
            raise ValueError('Configure the existing Apple development signing team in the project device tool first.')
        recipe.update(config=str(config), config_sha256=file_sha256(config))
    path, report = workspace / 'recipe.json', workspace / 'prepared.json'
    save_json(path, recipe)
    package = workspace / ('app.apk' if platform == 'android' else 'app.zip')
    env = dict(PYTHONPATH=os.pathsep.join((str(snapshot), str(snapshot / 'Python'))),
               LOGISTICS_DEPLOY_WORKSPACE=str(workspace), PYTHONUNBUFFERED='1',
               PIP_FIND_LINKS=str(project.mobile / '.tools/release-wheels'),
               PATH=str(project.mobile / '.tools/go/bin') + os.pathsep + os.environ.get('PATH', ''))
    for key, name in [('tools.android_sdk', 'ANDROID_HOME'), ('tools.java', 'JAVA_HOME'), ('tools.xcode', 'DEVELOPER_DIR')]:
        if options.get(key):env[name] = options[key]
    if env.get('ANDROID_HOME'):env['ANDROID_SDK_ROOT'] = env['ANDROID_HOME']
    command = (options['tools.mobile_python'], '-m', 'Scripts.manager_devices')
    prepare = Phase('prepare-device-app', (*command, 'prepare', '--recipe', str(path), '--sha256', file_sha256(path)),
        str(snapshot), timeout=14400, environment=env, effect='build', kind='build',
        artifacts=(str(report), str(package)), resources={'host.mobile-build': 1, 'host.signing-keychain': 1},
        label=('Use shared Android Release APK' if platform == 'android' else 'Export & sign iOS Release for devices') if shared else
              ('Build Android Debug APK' if platform == 'android' else 'Build & sign iOS Debug app'),
        description='Reuse the selected Release build; no compilation' if shared else 'Development variant · separate from Release')
    phases = [prepare]
    for index, target in enumerate(targets):
        receipt = workspace / ('device-' + str(index) + '.json')
        label = re.sub(r'[^A-Za-z0-9]+', '-', target['name']).strip('-')[:40] or 'device'
        phases.append(Phase('install-' + str(index + 1) + '-' + label, (*command, 'install', '--report', str(report),
            '--device', target['id'], '--receipt', str(receipt)), str(snapshot), dependencies=(prepare.id,),
            environment=env, effect='deploy', kind='distribution', timeout=600, artifacts=(str(receipt),),
            resources={'device:' + platform + ':' + target['id']: 1, 'host.device-install': 1}))
    return Plan('Logistics', 'Prepare and install device app', source, tuple(phases), str(workspace),
        backend='This Mac', resource_locks=(str(project.mobile / '.deploy-workspaces/deploy.lock'),))


def check_source(recipe):
    from Scripts.build_snapshots import identity
    root = Path(recipe['root']); metadata = read_json(root / '.manager-source.json')
    if (any(metadata['source'].get(key) != recipe['source'].get(key)
            for key in ('fingerprint', 'logistics_commit', 'commonUtils_commit', 'dirty'))
            or identity(root)['fingerprint'] != metadata['snapshot_fingerprint']):
        raise ValueError('Captured source changed. Prepare a new device plan.')


def prepare(path, digest):
    path = Path(path)
    if file_sha256(path) != digest:
        raise ValueError('Device preparation recipe changed; review a new plan.')
    data = read_json(path); check_source(data)
    workspace = Path(data['workspace']); platform = data['platform']
    if data.get('shared_report'):
        prepare_shared(data)
        package = Path(data['package'])
    elif platform == 'android':
        from mobile_build.deployment import android_deploy as android
        # No device queries or wireless connections while building.
        android.deploy(build_only=True, devices=[], discover=False)
        package = workspace / 'app.apk'
        shutil.copy2(android.PROJECT / 'app/build/outputs/apk/debug/app-debug.apk', package)
        data['identity'] = dict(bundle_id=BUNDLE, certificate=sign_android_debug(data, package))
    elif platform == 'ios':
        from mobile_build.deployment import device_tools as ios
        if file_sha256(data['config']) != data['config_sha256']:
            raise ValueError('Device signing configuration changed; review a new plan.')
        config = read_json(data['config'])
        developer, _ = ios.choose(ios.installed()); env = dict(os.environ, DEVELOPER_DIR=developer)
        ios.refresh_sources(env); ios.prepare_project(config['team_id'])
        ios.run(['xcodebuild', '-project', str(ios.PBX.parent), '-scheme', 'Logistics Mobile',
            '-configuration', 'Debug', '-sdk', 'iphoneos', '-destination', 'generic/platform=iOS',
            '-derivedDataPath', str(ios.DERIVED), 'build'], env=env, log=workspace / 'logs/device-build.log')
        identities = [ios.validate_app(ios.APP, config['team_id'], target['id']) for target in data['targets']]
        if config.get('signing_identity') and any(row != config['signing_identity'] for row in identities):
            raise ValueError('Existing device signing identity differs; installation is blocked.')
        data['identity'] = identities[0]
        package = workspace / 'app.zip'
        subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(ios.APP), str(package)], check=True)
    else:raise ValueError('Unsupported device platform.')
    data.update(package=str(package), package_sha256=file_sha256(package), bundle_id=BUNDLE)
    check_source(data); save_json(workspace / 'prepared.json', data)
    return data


def sign_android_debug(data, package):
    """Choose the declared key before review, without contacting any device."""
    from mobile_build.deployment import android_deploy as android
    env, _ = android.tools_environment(android.deployment_environment())
    tools = android.build_tools(env)
    mode = data['source'].get('run_overrides', {}).get('devices.android_signing', 'debug')
    if mode == 'debug':
        return android.apk_certificate(package, tools, env)
    if mode != 'beta':
        raise ValueError('Unknown Android Debug signing mode.')
    private = Path(data['root']) / 'mobile_build/.android-beta'
    key, record = private / 'signing.p12', private / 'signing.json'
    if not key.is_file() or not record.is_file():
        raise ValueError('Existing Logistics Beta signing key is missing; no key is created.')
    signing_env = dict(env, LOGISTICS_BETA_STORE_PASSWORD=read_json(record)['password'])
    public = subprocess.check_output([str(Path(env['JAVA_HOME']) / 'bin/keytool'), '-exportcert',
        '-keystore', str(key), '-alias', 'logistics-beta', '-storepass:env',
        'LOGISTICS_BETA_STORE_PASSWORD'], env=signing_env, stderr=subprocess.PIPE)
    certificate = hashlib.sha256(public).hexdigest()
    signed = Path(data['workspace']) / 'signed.apk'
    android.run([str(tools / 'apksigner'), 'sign', '--ks', str(key), '--ks-key-alias', 'logistics-beta',
        '--ks-pass', 'env:LOGISTICS_BETA_STORE_PASSWORD', '--out', str(signed), str(package)], signing_env)
    if android.apk_certificate(signed, tools, env) != certificate:
        raise ValueError('Prepared Android signature does not match the selected Beta key.')
    os.replace(signed, package)
    return certificate


def android_signature_preflight(data, target, adb, env):
    """Reject incompatible prepared bytes before recording an install attempt."""
    from mobile_build.deployment import android_deploy as android
    certificate = data.get('identity', {}).get('certificate')
    if not certificate:
        return  # Compatibility for retained reports prepared before this field.
    prefix = [str(adb), '-s', target['connection']]
    paths = android.run([*prefix, 'shell', 'pm', 'path', BUNDLE], env)
    installed = next((line.removeprefix('package:') for line in paths.splitlines()
                      if line.startswith('package:') and line.endswith('/base.apk')), None)
    if installed is None:
        return
    previous = Path(data['workspace']) / ('signature-check-' + uuid4().hex + '.apk')
    try:
        android.run([*prefix, 'pull', installed, str(previous)], env)
        if android.apk_certificate(previous, android.build_tools(env), env) != certificate:
            raise ValueError('Installed Android signing identity differs. Prepare a new package with its existing key; app data is preserved.')
    finally:
        previous.unlink(missing_ok=True)


def prepare_shared(data):
    """Consume project-declared Release output without compiling or contacting devices."""
    workspace = Path(data['workspace'])
    if data['platform'] == 'android':
        report = read_json(data['shared_report'])
        if report.get('provider') != 'Firebase' or report.get('bundle_id') != BUNDLE:
            raise ValueError('Expected the shared verified Firebase APK.')
        apk = Path(report['apk'])
        if file_sha256(apk) != report['apk_sha256']:raise ValueError('Shared Release APK changed.')
        package = workspace / 'app.apk'
        shutil.copy2(apk, package)
        data['identity'] = dict(bundle_id=BUNDLE, certificate=report['certificate'])
    else:
        from Scripts.manager_packages import checked_archive
        from mobile_build.deployment import device_tools as ios
        state, record = checked_archive(data['shared_report'])
        config = read_json(data['config'])
        if file_sha256(data['config']) != data['config_sha256']:
            raise ValueError('Device signing configuration changed; review a new plan.')
        if record['identity']['team_id'] != config['team_id']:
            raise ValueError('Release and device signing teams differ.')
        options = workspace / 'DeviceExportOptions.plist'
        options.write_bytes(plistlib.dumps(dict(method='debugging', signingStyle='automatic',
            teamID=config['team_id'], destination='export', manageAppVersionAndBuildNumber=False)))
        developer, _ = ios.choose(ios.installed()); env = dict(os.environ, DEVELOPER_DIR=developer)
        exported = workspace / 'device-export'
        ios.run(['xcodebuild', '-exportArchive', '-archivePath', str(Path(state['workspace']) / 'Logistics.xcarchive'),
            '-exportOptionsPlist', str(options), '-exportPath', str(exported)], env=env,
            log=workspace / 'logs/device-export.log')
        ipas = list(exported.glob('*.ipa'))
        if len(ipas) != 1:raise ValueError('Expected one provisioned device export.')
        extracted = workspace / 'exported-app'; extracted.mkdir()
        try:
            subprocess.run(['/usr/bin/ditto', '-x', '-k', str(ipas[0]), str(extracted)], check=True)
            apps = list((extracted / 'Payload').glob('*.app'))
            if len(apps) != 1:raise ValueError('Unexpected device IPA layout.')
            identities = [ios.validate_app(apps[0], config['team_id'], target['id']) for target in data['targets']]
            if config.get('signing_identity') and any(row != config['signing_identity'] for row in identities):
                raise ValueError('Existing device signing identity differs.')
            # Extensions must also provision every selected device.
            for extension in apps[0].glob('PlugIns/*.appex'):
                profile_path = extension / 'embedded.mobileprovision'
                profile = plistlib.loads(subprocess.check_output(['security', 'cms', '-D', '-i', str(profile_path)]))
                if profile.get('TeamIdentifier') != [config['team_id']] or any(
                        target['id'] not in profile.get('ProvisionedDevices', []) for target in data['targets']):
                    raise ValueError('Extension profile does not authorize the selected devices.')
            data['identity'] = identities[0]
            package = workspace / 'app.zip'
            subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(apps[0]), str(package)], check=True)
        finally:shutil.rmtree(extracted)
    data.update(package=str(package), variant='release')


def install(report, device, receipt):
    from Scripts.distribute_prepared import reviewed
    data = reviewed(report)
    targets = [row for row in data['targets'] if row['id'] == device]
    if len(targets) != 1:raise ValueError('Device is not a reviewed recipient.')
    target = targets[0]; receipt = Path(receipt); attempt = receipt.with_suffix('.attempt.json')
    if receipt.exists() or attempt.exists():
        raise ValueError('Reconcile the recorded device installation before retrying.')
    package = Path(data['package'])
    if data['bundle_id'] != BUNDLE or file_sha256(package) != data['package_sha256']:
        raise ValueError('Reviewed device app changed.')
    # Do every read-only identity/availability check before recording an attempt.
    if data['platform'] == 'android':
        from mobile_build.deployment import android_deploy as android
        env, adb = android.tools_environment(android.deployment_environment())
        serial = target['connection']
        if android.run([str(adb), '-s', serial, 'get-state'], env).strip() != 'device':
            raise ValueError('Selected Android device is offline or unauthorized.')
        if serial != target['id'] and android.run([str(adb), '-s', serial, 'shell', 'getprop', 'ro.serialno'], env).strip() != target['id']:
            raise ValueError('Selected Android device identity changed; reload saved devices.')
        android_signature_preflight(data, target, adb, env)
        # Exact reviewed bytes, no compatibility re-sign, downgrade or uninstall.
        command = [str(adb), '-s', serial, 'install', '-r', str(package)]
        perform = lambda: android.run(command, env, timeout=300)
    elif data['platform'] == 'ios':
        from mobile_build.deployment import device_tools as ios
        if file_sha256(data['config']) != data['config_sha256']:
            raise ValueError('Device signing configuration changed; prepare a fresh plan.')
        developer, _ = ios.choose(ios.installed()); env = dict(os.environ, DEVELOPER_DIR=developer)
        _, udid, _ = ios.select_device(ios.device_json(['list', 'devices'], env)['devices'], device)
        extracted = Path(data['workspace']) / ('install-' + uuid4().hex)
        extracted.mkdir()
        try:
            subprocess.run(['/usr/bin/ditto', '-x', '-k', str(package), str(extracted)], check=True)
            app = extracted / 'Logistics Mobile.app'
            if ios.validate_app(app, data['identity']['team_id'], udid) != data['identity']:
                raise ValueError('Reviewed iOS signing identity changed.')
        except BaseException:
            shutil.rmtree(extracted); raise
        perform = lambda: ios.device_json(['device', 'install', 'app', '--device', device, str(app)], env)
    else:raise ValueError('Unsupported device platform.')
    receipt.parent.mkdir(parents=True, exist_ok=True)
    save_json(attempt, dict(schema=1, operation=os.environ.get('BUILD_MANAGER_OPERATION_ID'),
        plan=os.environ['BUILD_MANAGER_APPROVED_PLAN'], device=device, package_sha256=data['package_sha256'], status='unknown'))
    try:
        perform()
        result = dict(schema=1, status='installed', device=device, name=target['name'],
            platform=data['platform'], bundle_id=BUNDLE, package_sha256=data['package_sha256'],
            source=data['source'], operation=os.environ.get('BUILD_MANAGER_OPERATION_ID'))
        save_json(receipt, result); return result
    finally:
        if data['platform'] == 'ios':shutil.rmtree(extracted)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'install'])
    for name in ('recipe', 'report', 'receipt'):parser.add_argument('--' + name, type=Path)
    parser.add_argument('--sha256'); parser.add_argument('--device')
    args = parser.parse_args()
    if args.action == 'prepare':
        if not args.recipe or not args.sha256:parser.error('Preparation needs a recipe and its hash.')
        prepare(args.recipe, args.sha256)
    else:
        if not args.report or not args.device or not args.receipt:parser.error('Installation needs a report, device and receipt.')
        install(args.report, args.device, args.receipt)
    return 0


if __name__ == '__main__':
    try:raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        from build_manager.redaction import Redactor
        print(Redactor()(str(error)), file=sys.stderr); raise SystemExit(1)
