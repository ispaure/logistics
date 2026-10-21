"""Build and update Logistics on a paired iPhone or iPad, preserving identity."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

try:
    from .select_ios_sdk import choose, installed
    from .tools import stage
    from .deployment_paths import output_root, prepare_workspace
except ImportError:
    from select_ios_sdk import choose, installed
    from tools import stage
    from deployment_paths import output_root, prepare_workspace

ROOT = Path(__file__).resolve().parent
PROJECT = output_root(ROOT) / 'build/logisticsmobile/ios/xcode'
PBX = PROJECT / 'Logistics Mobile.xcodeproj/project.pbxproj'
INFO = PROJECT / 'LogisticsMobile/LogisticsMobile-Info.plist'
CONFIG = ROOT / '.device.json'
BUNDLE = 'io.github.ispaure.logisticsmobile'
DERIVED = output_root(ROOT) / 'build/physical-device'
APP = DERIVED / 'Build/Products/Debug-iphoneos/Logistics Mobile.app'


def run(args, *, env=None, log=None):
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        print(f'Running {args[0]}; log: {log}', flush=True)
        with log.open('w') as stream:
            result = subprocess.run(args, cwd=output_root(ROOT), env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'{args[0]} failed. See {log}\n' + '\n'.join(log.read_text(errors='replace').splitlines()[-18:]))
    else:
        subprocess.run(args, cwd=output_root(ROOT), env=env, check=True)


def device_json(args, env):
    with tempfile.TemporaryDirectory(prefix='logistics-device-') as temporary:
        output = Path(temporary) / 'result.json'
        run(['xcrun', 'devicectl', *args, '--timeout', '60', '--json-output', str(output)], env=env)
        data = json.loads(output.read_text())
    if data['info']['outcome'] != 'success':
        raise RuntimeError('Xcode device operation did not succeed.')
    return data['result']


def properties(device):
    current = device.get('properties', {})
    return (current.get('hardware', device.get('hardwareProperties', {})),
            current.get('connection', device.get('connectionProperties', {})))


def select_device(devices, requested=None):
    physical = [d for d in devices if properties(d)[0].get('reality') == 'physical'
                and properties(d)[0].get('deviceType') in ('iPhone', 'iPad')]
    if requested:
        physical = [d for d in physical if requested in
                    (d['identifier'], properties(d)[0].get('udid'),
                     d.get('properties', {}).get('state', {}).get('name'),
                     d.get('deviceProperties', {}).get('name'))]
    if len(physical) != 1:
        raise RuntimeError('Connect one paired iPhone or iPad, or specify its UDID with --device.')
    hardware, connection = properties(physical[0])
    if connection.get('pairingState') != 'paired':
        raise RuntimeError('Pair the device in Xcode first.')
    return physical[0], hardware['udid'], connection


def signing_settings(data, team):
    targets = [o['buildSettings'] for o in data['objects'].values()
               if o.get('isa') == 'XCBuildConfiguration'
               and 'PRODUCT_BUNDLE_IDENTIFIER' in o.get('buildSettings', {})]
    if len(targets) != 2 or any(s['PRODUCT_BUNDLE_IDENTIFIER'] != BUNDLE for s in targets):
        raise RuntimeError('Unexpected app identity/configurations; refusing to change them.')
    for settings in targets:
        existing = settings.get('DEVELOPMENT_TEAM')
        if existing and existing != team:
            raise RuntimeError('Existing Xcode signing team differs; refusing to replace it.')
        settings['DEVELOPMENT_TEAM'] = team
        settings['CODE_SIGN_STYLE'] = 'Automatic'
    return data


def normal_launcher(info):
    if info.get('CFBundleIdentifier') != BUNDLE:
        raise RuntimeError('Unexpected bundle identifier; refusing to change it.')
    info['MainModule'] = 'logisticsmobile'
    return info


def configured_ios_info():
    with (ROOT / 'pyproject.toml').open('rb') as stream:
        config = tomllib.load(stream)['tool']['briefcase']
    app = config['app']['logisticsmobile']
    return dict(app['iOS'].get('info', {}),
                CFBundleShortVersionString=config['version'], CFBundleVersion=str(app['build']))


def prepare_project(team):
    data = json.loads(subprocess.check_output(['plutil', '-convert', 'json', '-o', '-', str(PBX)]))
    PBX.write_bytes(plistlib.dumps(signing_settings(data, team), sort_keys=False))
    info = plistlib.loads(INFO.read_bytes())
    # Briefcase update refreshes Python sources but leaves the generated plist's
    # original extra keys in place. Reapply the canonical platform settings.
    info.update(configured_ios_info())
    INFO.write_bytes(plistlib.dumps(normal_launcher(info)))


def validate_app(app, team, udid):
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    if any(info.get(key) != value for key, value in configured_ios_info().items()):
        raise RuntimeError('Built app is missing configured iOS plist settings; refusing installation.')
    if info.get('CFBundleIdentifier') != BUNDLE or info.get('MainModule') != 'logisticsmobile':
        raise RuntimeError('Built app identity or launcher is incorrect; refusing installation.')
    profile = plistlib.loads(subprocess.check_output(['security', 'cms', '-D', '-i', str(app / 'embedded.mobileprovision')]))
    entitlements = plistlib.loads(subprocess.check_output(['codesign', '-d', '--entitlements', ':-', str(app)], stderr=subprocess.DEVNULL))
    expected = profile['Entitlements']['application-identifier']
    if (profile['TeamIdentifier'] != [team] or udid not in profile.get('ProvisionedDevices', [])
            or not expected.endswith('.' + BUNDLE)
            or entitlements.get('application-identifier') != expected
            or entitlements.get('com.apple.developer.team-identifier') != team):
        raise RuntimeError('Signing identity or device provisioning differs; refusing installation.')
    run(['codesign', '--verify', '--deep', '--strict', str(app)])
    return {'bundle_id': BUNDLE, 'team_id': team, 'application_identifier': expected,
            'keychain_access_groups': entitlements.get('keychain-access-groups', [])}


def refresh_sources(env):
    # Stage first; a failed staging attempt leaves the old payload untouched.
    workspace = prepare_workspace(ROOT)
    with tempfile.TemporaryDirectory(prefix='logistics-stage-', dir=workspace / 'build') as temporary:
        replacement = Path(temporary) / 'payload'
        stage(ROOT.parent, replacement, allow_dirty=True)
        payload = workspace / 'payload'
        if payload.exists():
            payload.rename(Path(temporary) / 'previous-payload')
        replacement.rename(payload)
        try:
            run([sys.executable, str(ROOT / 'cloud_build.py'), 'licenses'], env=env, log=workspace / 'logs/device-licenses.log')
        except Exception:
            shutil.rmtree(payload)
            previous = Path(temporary) / 'previous-payload'
            if previous.exists():
                previous.rename(payload)
            raise
    action = 'update' if PBX.exists() else 'create'
    command = [sys.executable, '-m', 'briefcase', action, 'iOS', '--no-input']
    if action == 'update':
        # Briefcase otherwise refreshes sources but retains stale app_packages.
        command.append('--update-requirements')
    run(command, env=env,
        log=workspace / 'logs/device-update.log')
    run([sys.executable, str(ROOT / 'cloud_build.py'), 'ios'], env=env, log=workspace / 'logs/device-bridge.log')


def saved_config():
    if not CONFIG.exists():
        raise RuntimeError('Run configure --team TEAM_ID once before building or deploying.')
    config = json.loads(CONFIG.read_text())
    if config['bundle_id'] != BUNDLE or not re.fullmatch(r'[A-Z0-9]{10}', config['team_id']):
        raise RuntimeError('Invalid saved app identity.')
    return config


def launch_app(config, env, developer, sdk, *, allow_wired=False, install=False):
    devices = device_json(['list', 'devices'], env)['devices']
    _, _, connection = select_device(devices, config['device_id'])
    transport = connection.get('transportType')
    if not allow_wired and transport not in ('wireless', 'localNetwork'):
        raise RuntimeError(f'Expected wireless transport, found {transport}. Unplug USB, unlock the device, and use the same Wi-Fi.')
    report = dict(config['signing_identity'], device_id=config['device_id'], developer_dir=developer, sdk=sdk,
                  transport=transport, installed=False, launched=False)
    report_path = output_root(ROOT) / 'logs/device-deployment.json'
    report_path.parent.mkdir(exist_ok=True)
    if install:
        # Never uninstall, reset, unpair, or retry with another identity.
        report['installation'] = device_json(['device', 'install', 'app', '--device', config['device_id'], str(APP)], env)
        report['installed'] = True
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    try:
        report['launch'] = device_json(['device', 'process', 'launch', '--device', config['device_id'], BUNDLE], env)
    except subprocess.CalledProcessError as error:
        raise RuntimeError('Launch failed; see the device error above. For a trust error, trust the developer in device Settings > General > VPN & Device Management, then run launch. Do not uninstall.') from error
    report['launched'] = True
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    (report_path.parent / f"device-deployment-{config['device_id']}.json").write_text(
        json.dumps(report, indent=2) + '\n')
    print(('Installed and launched' if install else 'Launched') + ' Logistics over ' + transport + '.')


def deploy_all(config, *, allow_wired=False):
    """Run the normal verified deployment for every explicitly saved target."""
    targets = config.get('device_ids', [config['device_id']])
    if (not isinstance(targets, list) or not targets
            or any(not isinstance(target, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', target)
                   for target in targets)):
        raise RuntimeError('device_ids must be a nonempty list of device UDIDs in .device.json.')
    failures = []
    for target in dict.fromkeys(targets):
        print(f'\nDeploying Logistics to {target}...', flush=True)
        command = [sys.executable, str(Path(__file__).resolve()), 'deploy', '--device', target]
        if allow_wired:
            command.append('--allow-wired')
        try:
            run(command)
        except (RuntimeError, subprocess.CalledProcessError) as error:
            failures.append(target)
            print(f'Deployment failed for {target}: {error}', file=sys.stderr, flush=True)
    if failures:
        raise RuntimeError('Deployment failed for: ' + ', '.join(failures))
    print(f'Updated all {len(set(targets))} saved iOS devices.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('configure', 'status', 'build', 'deploy', 'deploy-all', 'launch'))
    parser.add_argument('--team', help='Existing Apple development team ID (configure only)')
    parser.add_argument('--device', help='Paired iPhone/iPad UDID/name; defaults to the saved device')
    parser.add_argument('--allow-wired', action='store_true', help='Allow a USB-connected deployment')
    args = parser.parse_args()
    if args.command != 'configure' and args.team:
        parser.error('The signing team is pinned by configure, not overridden on deployment.')
    if args.command == 'deploy-all':
        if args.device:
            parser.error('Use deploy --device for a single target, or deploy-all for saved targets.')
        deploy_all(saved_config(), allow_wired=args.allow_wired)
        return
    developer, sdk = choose(installed())
    env = dict(os.environ, DEVELOPER_DIR=developer)
    prepare_workspace(ROOT)
    if args.command == 'configure':
        if not args.team or not re.fullmatch(r'[A-Z0-9]{10}', args.team):
            parser.error('configure requires the existing 10-character --team ID.')
        _, udid, _ = select_device(device_json(['list', 'devices'], env)['devices'], args.device)
        config = dict(bundle_id=BUNDLE, team_id=args.team, device_id=udid)
        previous = saved_config() if CONFIG.exists() else {}
        if previous and any(previous[k] != v for k, v in config.items()):
            raise RuntimeError('Saved identity/device differs. Review .device.json explicitly; it will not be replaced.')
        if PBX.exists():
            prepare_project(args.team)
        CONFIG.write_text(json.dumps(dict(previous, **config), indent=2) + '\n')
        print('Saved device and signing team in local .device.json.')
        return
    config = saved_config()
    default_device = config['device_id']
    if args.device:
        _, config['device_id'], _ = select_device(
            device_json(['list', 'devices'], env)['devices'], args.device)
    if args.command == 'launch':
        if not config.get('signing_identity'):
            raise RuntimeError('Build and deploy once before using launch.')
        launch_app(config, env, developer, sdk, allow_wired=args.allow_wired)
        return
    if args.command == 'status':
        result = device_json(['list', 'devices'], env)
        _, _, connection = select_device(result['devices'], config['device_id'])
        print(json.dumps(dict(config, developer_dir=developer, sdk=sdk, connection=connection), indent=2))
        return
    refresh_sources(env)
    prepare_project(config['team_id'])
    run(['xcodebuild', '-project', str(PBX.parent), '-scheme', 'Logistics Mobile',
         '-configuration', 'Debug', '-sdk', 'iphoneos', '-destination', f"id={config['device_id']}",
         '-derivedDataPath', str(DERIVED), '-allowProvisioningUpdates',
         '-allowProvisioningDeviceRegistration', 'build'], env=env, log=output_root(ROOT) / 'logs/device-build.log')
    identity = validate_app(APP, config['team_id'], config['device_id'])
    if config.get('signing_identity') and config['signing_identity'] != identity:
        raise RuntimeError('Previously built signing/keychain identity differs; refusing deployment.')
    config['signing_identity'] = identity
    CONFIG.write_text(json.dumps(dict(config, device_id=default_device), indent=2) + '\n')
    print('Verified signed physical-device build.', flush=True)
    if args.command == 'build':
        return
    launch_app(config, env, developer, sdk, allow_wired=args.allow_wired, install=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
