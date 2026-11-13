"""Focused incoming-file acceptance using the existing mobile build owners.

Generated QA projects live in retention-owned scratch. Their only app overlay is
the disposable bundle identity; the ordinary launcher and native intake remain.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import sys
from uuid import uuid4

MAIN_BUNDLE = 'io.github.ispaure.logisticsmobile'
QA_BUNDLE = 'io.github.ispaure.logisticsinboxqa'
SENDER_BUNDLE = 'io.github.ispaure.logisticsincomingsender'


def command(arguments, log, *, cwd, environment, timeout=1800):
    from build_manager.executor import stop_process
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w') as stream:
        process = subprocess.Popen(list(map(str, arguments)), cwd=cwd, env=environment,
                                   stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout)
        finally:
            stop_process(process)
    if code:
        raise RuntimeError(f'Incoming acceptance command failed ({code}); see {log}')


def ios_identity(project):
    """Change bundle identifiers only; App Group identifiers match native code."""
    project = Path(project)
    pbx = next(project.glob('*.xcodeproj/project.pbxproj'))
    data = plistlib.loads(pbx.read_bytes())
    identities = []
    for item in data['objects'].values():
        settings = item.get('buildSettings', {})
        bundle = settings.get('PRODUCT_BUNDLE_IDENTIFIER', '')
        if bundle == MAIN_BUNDLE or bundle.startswith(MAIN_BUNDLE + '.'):
            settings['PRODUCT_BUNDLE_IDENTIFIER'] = QA_BUNDLE + bundle[len(MAIN_BUNDLE):]
            identities.append(settings['PRODUCT_BUNDLE_IDENTIFIER'])
    if QA_BUNDLE not in identities or QA_BUNDLE + '.inbox' not in identities:
        raise ValueError('Normal receiver project lacks its app or embedded Share extension.')
    pbx.write_bytes(plistlib.dumps(data, sort_keys=False))
    for path in project.rglob('*Info.plist'):
        metadata = plistlib.loads(path.read_bytes())
        bundle = metadata.get('CFBundleIdentifier', '')
        if bundle == MAIN_BUNDLE or bundle.startswith(MAIN_BUNDLE + '.'):
            metadata['CFBundleIdentifier'] = QA_BUNDLE + bundle[len(MAIN_BUNDLE):]
        path.write_bytes(plistlib.dumps(metadata))


def verify_ios(app):
    metadata = plistlib.loads((app / 'Info.plist').read_bytes())
    if metadata.get('CFBundleIdentifier') != QA_BUNDLE or metadata.get('MainModule') != 'logisticsmobile':
        raise ValueError('Acceptance requires the disposable normal-entry receiver.')
    extensions = [plistlib.loads(path.read_bytes()) for path in (app / 'PlugIns').glob('*.appex/Info.plist')]
    if not any(item.get('CFBundleIdentifier') == QA_BUNDLE + '.inbox' and
               item.get('NSExtension', {}).get('NSExtensionPointIdentifier') == 'com.apple.share-services'
               for item in extensions):
        raise ValueError('Acceptance receiver is missing its actual Share extension.')
    launcher = app / 'app/logisticsmobile/__main__.py'
    if launcher.read_text() != 'from mobile.app import main\n\nmain().main_loop()\n':
        raise ValueError('Acceptance receiver launcher differs from the ordinary application.')
    return dict(bundle=QA_BUNDLE, main_module=metadata['MainModule'],
                extensions=[item['CFBundleIdentifier'] for item in extensions])


def android_identity(project):
    """Retain Java/R namespaces, changing only the installed package identity."""
    from xml.etree import ElementTree as ET
    project = Path(project)
    gradle = project / 'app/build.gradle'
    updated, count = re.subn(r'applicationId "' + re.escape(MAIN_BUNDLE) + r'"',
                            'applicationId "' + QA_BUNDLE + '"', gradle.read_text())
    if count != 1:
        raise ValueError('Expected exactly one normal Android application identity.')
    gradle.write_text(updated)
    path = project / 'app/src/main/AndroidManifest.xml'
    namespace = 'http://schemas.android.com/apk/res/android'
    ET.register_namespace('android', namespace)
    tree = ET.parse(path)
    for provider in tree.getroot().findall('application/provider'):
        key = '{' + namespace + '}authorities'
        authority = provider.get(key, '')
        if authority.startswith(MAIN_BUNDLE + '.'):
            provider.set(key, QA_BUNDLE + authority[len(MAIN_BUNDLE):])
    tree.write(path, encoding='utf-8', xml_declaration=True)


def verify_android(project, apk, environment):
    from xml.etree import ElementTree as ET
    project, apk = Path(project), Path(apk)
    launcher = project / 'app/src/main/python/logisticsmobile/__main__.py'
    if launcher.read_text() != 'from mobile.app import main\n\nmain().main_loop()\n':
        raise ValueError('Android acceptance requires the ordinary launcher.')
    strings = ET.parse(project / 'app/src/main/res/values/briefcase.xml').getroot()
    if next((item.text for item in strings if item.get('name') == 'main_module'), None) != 'logisticsmobile':
        raise ValueError('Android acceptance cannot launch the full-suite test entry point.')
    aapt = Path(environment['ANDROID_HOME']) / 'build-tools/36.0.0/aapt'
    badging = subprocess.check_output([aapt, 'dump', 'badging', apk], text=True, env=environment, timeout=30)
    manifest = subprocess.check_output([aapt, 'dump', 'xmltree', apk, 'AndroidManifest.xml'],
                                      text=True, env=environment, timeout=30)
    if "package: name='" + QA_BUNDLE + "'" not in badging or 'application-debuggable' not in badging:
        raise ValueError('Expected a debuggable disposable Android package.')
    for value in ('io.github.ispaure.logisticsmobile.ReceiveActivity',
                  'android.intent.action.SEND', 'android.intent.action.SEND_MULTIPLE'):
        if value not in manifest:
            raise ValueError('Built Android receiver is missing native registration: ' + value)
    return dict(bundle=QA_BUNDLE, main_module='logisticsmobile', apk_sha256=sha256(apk.read_bytes()).hexdigest())


def prepare(root, platform, output, environment=None):
    """Build from a captured source; retain scratch until explicit cleanup."""
    from logistics_build.build_retention import scratch
    root, output = Path(root).resolve(), Path(output).resolve()
    source_file = root / '.manager-source.json'
    if not source_file.is_file():
        raise ValueError('Incoming acceptance requires a manager-owned source snapshot.')
    source = json.loads(source_file.read_text())
    output.mkdir(parents=True, exist_ok=True)
    recipe = output / 'receiver-build.json'
    if recipe.exists():
        raise ValueError('Existing acceptance build receipt must be cleaned up before replacement.')
    env = dict(os.environ, **(environment or {}))
    with scratch(root) as workspace:
        # An explicit durable hold supports a separately scheduled native slot.
        # cleanup() checks this exact recipe and the retention ownership marker.
        (workspace / '.keep').write_text('Send File 06 receiver; cleanup via receiver-build.json\n')
        record = dict(schema=1, platform=platform, workspace=str(workspace), root=str(root),
                      source=source, bundle=QA_BUNDLE, status='preparing')
        recipe.write_text(json.dumps(record, indent=2) + '\n')
        env.update(LOGISTICS_DEPLOY_WORKSPACE=str(workspace),
                   COMMONUTILS_STORAGE_ROOT=str(workspace / 'private-storage'))
        try:
            mobile = root / 'mobile_build'
            shutil.copyfile(mobile / 'pyproject.toml', workspace / 'pyproject.toml')
            shutil.copytree(mobile / 'native_tests', workspace / 'native_tests',
                            ignore=shutil.ignore_patterns('__pycache__'))
            command([sys.executable, 'tools.py', 'stage', str(workspace / 'payload'),
                     '--repo', root, '--allow-dirty'], output / 'receiver-stage.log',
                    cwd=mobile, environment=env)
            command([sys.executable, 'cloud_build.py', 'licenses', '--platform', platform],
                    output / 'receiver-licenses.log', cwd=mobile, environment=env)
            command([sys.executable, '-m', 'briefcase', 'create', 'iOS' if platform == 'ios' else 'android', '--no-input'],
                    output / 'receiver-create.log', cwd=workspace, environment=env)
            command([sys.executable, 'cloud_build.py', platform], output / 'receiver-native.log',
                    cwd=mobile, environment=env)
            if platform == 'ios':
                project = workspace / 'build/logisticsmobile/ios/xcode'
                ios_identity(project)
                command(['xcodebuild', '-project', project / 'Logistics Mobile.xcodeproj',
                         '-scheme', 'Logistics Mobile', '-sdk', 'iphonesimulator', '-configuration', 'Debug',
                         '-derivedDataPath', workspace / 'derived', 'CODE_SIGNING_ALLOWED=YES',
                         'CODE_SIGN_IDENTITY=-', 'CODE_SIGN_STYLE=Manual', 'DEVELOPMENT_TEAM=',
                         'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'build'], output / 'receiver-build.log',
                        cwd=workspace, environment=env)
                app = workspace / 'derived/Build/Products/Debug-iphonesimulator/Logistics Mobile.app'
                from logistics_build.ios_backend import bundle_digest
                record.update(status='built', app=str(app), identity=verify_ios(app),
                              bundle_sha256=bundle_digest(app))
            else:
                project = workspace / 'build/logisticsmobile/android/gradle'
                android_identity(project)
                command([sys.executable, '-m', 'briefcase', 'build', 'android', '--no-input'],
                        output / 'receiver-build.log', cwd=workspace, environment=env)
                apk = project / 'app/build/outputs/apk/debug/app-debug.apk'
                record.update(status='built', apk=str(apk), identity=verify_android(project, apk, env))
            if platform == 'ios':
                from mobile_build.validation.incoming_ios_tools import build_sender
                record['sender'] = build_sender(workspace, env, output)
            else:
                from mobile_build.validation.incoming_android import build_sender
                build_sender(workspace, env['ANDROID_HOME'], env['JAVA_HOME'], output)
                record['sender'] = json.loads((output / 'sender-apk.json').read_text())
        except BaseException as error:
            record.update(status='failed', error=str(error))
            raise
        finally:
            recipe.write_text(json.dumps(record, indent=2) + '\n')
    return record


def cleanup(recipe):
    """Remove only the scratch tree named by this receiver's build receipt."""
    from logistics_build.build_retention import owned_scratch, scratch_location
    from build_manager.locking import workspace_lock
    from build_manager.retention import remove_tree
    recipe = Path(recipe)
    record = json.loads(recipe.read_text())
    workspace, root = Path(record['workspace']), Path(record['root'])
    if (record.get('schema') != 1 or record.get('bundle') != QA_BUNDLE
            or not scratch_location(workspace, root)):
        raise ValueError('Refusing cleanup of an unowned incoming acceptance workspace.')
    if workspace.exists():
        lock = workspace.parent / ('.' + workspace.name + '.retention.lock')
        with workspace_lock(lock):
            if not scratch_location(workspace, root) or not owned_scratch(workspace):
                raise ValueError('Incoming acceptance scratch ownership is missing.')
            (workspace / '.keep').unlink(missing_ok=True)
            remove_tree(workspace, ownership_files=('.manager-scratch',))
    record['workspace_removed'] = not workspace.exists()
    recipe.write_text(json.dumps(record, indent=2) + '\n')


def create_ios(client, workspace, role, model, runtime):
    """Record a newly acquired UUID immediately, before boot or app actions."""
    workspace = Path(workspace)
    path = workspace / (role + '-lease.json')
    if role not in ('sender', 'iphone', 'ipad') or path.exists():
        raise ValueError('Choose a fresh supported incoming simulator lease.')
    workspace.mkdir(parents=True, exist_ok=True)
    family = 'ipad' if role == 'ipad' else 'iphone'
    name = 'Build Manager ' + family + ' ' + uuid4().hex
    device = client.create(name, model, runtime)
    value = dict(device=device, name=name, role=role, model=model, runtime=runtime)
    path.write_text(json.dumps(value, indent=2) + '\n')
    return value


def cleanup_ios(client, workspace, output):
    """Uninstall only disposable IDs, then delete positively matched devices."""
    from uuid import UUID
    workspace, output = Path(workspace), Path(output)
    outcomes = []
    for role in ('ipad', 'iphone', 'sender'):
        path = workspace / (role + '-lease.json')
        if not path.exists():
            continue
        record = json.loads(path.read_text())
        device, name = record['device'], record['name']
        UUID(device)
        family = 'ipad' if role == 'ipad' else 'iphone'
        if (record.get('role') != role or not re.fullmatch('Build Manager ' + family + r' [0-9a-f]{32}', name)):
            raise ValueError('Incoming simulator lease identity is invalid; refusing cleanup.')
        result = dict(record, removed=False, uninstalled=[])
        try:
            row = client.matching(device, name)
            if row is not None:
                try:
                    apps = ios_apps(client, device)
                except Exception as error:
                    raise RuntimeError('Cannot inspect installed apps on the owned simulator '
                                       f'({row.get("state", "unknown state")}); preserving its app data. '
                                       'Retry cleanup after the device can be inspected.') from error
                if MAIN_BUNDLE in apps:
                    raise RuntimeError('The main Logistics app is present; preserving this device and all app data.')
                for bundle in (SENDER_BUNDLE + '.uitests.xctrunner', QA_BUNDLE, SENDER_BUNDLE):
                    if bundle in apps:
                        client.invoke('uninstall', device, bundle)
                        result['uninstalled'].append(bundle)
                remaining = ios_apps(client, device)
                result['temporary_apps_remaining'] = [bundle for bundle in
                    (SENDER_BUNDLE + '.uitests.xctrunner', QA_BUNDLE, SENDER_BUNDLE) if bundle in remaining]
                if result['temporary_apps_remaining']:
                    raise RuntimeError('Temporary app uninstall did not settle.')
            client.remove(device, name)
            result['removed'] = client.matching(device, name) is None
            if result['removed']:
                path.rename(path.with_name(role + '-removed-lease.json'))
        except Exception as error:
            result['error'] = str(error)
        outcomes.append(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(outcomes, indent=2) + '\n')
    if any(not item['removed'] for item in outcomes):
        raise RuntimeError('Owned simulator cleanup incomplete; inspect ' + str(output))
    return outcomes


def ios_apps(client, device):
    # The installed simctl exposes listapps as an OpenStep plist, without a
    # --json flag. Convert that captured value; never inspect another device.
    value = client.invoke('listapps', device)
    converted = subprocess.run(['plutil', '-convert', 'json', '-o', '-', '-'],
        input=value, capture_output=True, text=True, timeout=15, check=True)
    return json.loads(converted.stdout)


def plan(project, target, source, snapshot, workspace, options, environment):
    """Focused local plans; canonical native/runtime inventories stay separate."""
    from build_manager import Phase, Plan
    from logistics_build.test_environments import load, runtime_id, android_image
    settings = load(snapshot)
    env = dict(environment, LOGISTICS_STORAGE_OWNER_ROOT=str(project.root),
               PATH=str(project.mobile / '.tools/go/bin') + os.pathsep + os.environ.get('PATH', ''),
               PIP_FIND_LINKS=str(project.mobile / '.tools/release-wheels'),
               GOTOOLCHAIN='local', GOTELEMETRY='off')
    if options['tools.xcode']:
        env['DEVELOPER_DIR'] = options['tools.xcode']
    if target == 'ios':
        if sys.platform != 'darwin':
            raise ValueError('Incoming iOS acceptance requires the local macOS host.')
        from build_manager.apple_simulators import AppleSimulators
        from mobile_build.validation.incoming_ios_tools import ACCEPTANCE_CASES
        from mobile_build.validation.ui_tools import select_ios_device
        from mobile_build.select_ios_sdk import choose
        client = AppleSimulators(env)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'],
                                      env=dict(os.environ, **env), text=True, timeout=30).strip()
        choose([(env.get('DEVELOPER_DIR', 'selected Xcode'), sdk)], settings['ios_sdk'])
        inventory = client.devices()['devices']
        profiles = []
        for profile in ('iphone', 'ipad'):
            runtime = runtime_id(settings, profile)
            configured = options['ios.' + profile]
            rows = [row for row in inventory.get(runtime, []) if row.get('isAvailable')
                    and (not configured or configured in (row['udid'], row['name']))]
            selected = select_ios_device({'devices': {runtime: rows}}, ipad=profile == 'ipad')
            model = next(row.get('deviceTypeIdentifier') for row in rows if row['udid'] == selected)
            if not model:
                raise ValueError('The selected incoming simulator profile has no device model.')
            profiles.append(dict(profile=profile, model=model, runtime=runtime,
                                 intake_cases=list(ACCEPTANCE_CASES[profile]),
                                 window_routing_required=profile == 'ipad'))
        source = dict(source, simulator_toolchain=client.toolchain(), incoming_profiles=profiles)
    else:
        from build_manager.android_emulators import AndroidEmulator
        if settings['android_api'] != '36' or settings['android_local_abi'] != 'arm64-v8a':
            raise ValueError('Incoming Android fixtures currently require the reviewed API 36 ARM64 profiles.')
        if options['android.avd']:
            raise ValueError('Incoming acceptance creates disposable AVDs; existing AVD selection is not supported.')
        sdk, java = Path(options['tools.android_sdk']), Path(options['tools.java'])
        if not options['tools.android_sdk'] or not options['tools.java'] or not (java / 'bin/java').is_file():
            raise ValueError('Configure an Android SDK and Java JDK before incoming acceptance.')
        env.update(ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk), JAVA_HOME=str(java),
                   GRADLE_OPTS='-Dorg.gradle.daemon=false')
        image = android_image(settings)
        readiness = AndroidEmulator(sdk, workspace / 'incoming-inspection', environment=env).inspect(image)
        profiles = [dict(profile='phone', model='pixel_9'), dict(profile='tablet', model='pixel_tablet')]
        source = dict(source, sdk=str(sdk), java=str(java), image=image,
                      acceleration=readiness, incoming_profiles=profiles)
    run = project.results_directory / 'incoming' / target / uuid4().hex
    build_output = run / 'build'
    recipe = build_output / 'receiver-build.json'
    base = (options['tools.mobile_python'], '-m', 'logistics_build.incoming_acceptance')
    build_id = target + '-build'
    phases = [Phase(build_id, (*base, 'prepare', '--root', str(snapshot), '--platform', target,
                    '--output', str(build_output), '--owner-root', str(project.root)), str(snapshot),
                    timeout=3600, environment=env, kind='build', artifacts=(str(recipe),))]
    previous = build_id
    cleanup_ids = []
    for row in profiles:
        profile = row['profile']
        device_workspace = workspace / (('simulators-' if target == 'ios' else 'incoming-') + uuid4().hex)
        output = run / profile
        common = ('--platform', target, '--profile', profile, '--workspace', str(device_workspace),
                  '--recipe', str(recipe), '--output', str(output))
        native_id = target + '-incoming-' + profile
        arguments = common
        if target == 'ios':
            arguments += ('--model', row['model'], '--runtime', row['runtime'])
        phases.append(Phase(native_id, (*base, 'test', *arguments), str(snapshot), timeout=5400,
                            environment=env, dependencies=tuple(dict.fromkeys((build_id, previous))),
                            artifacts=(str(output / 'result.json'),)))
        cleanup_id = native_id + '-cleanup'
        phases.append(Phase(cleanup_id, (*base, 'cleanup-devices', *common), str(snapshot), timeout=240,
                            environment=env, dependencies=(native_id,), always=True, kind='cleanup',
                            artifacts=(str(output / 'final-cleanup.json'),)))
        cleanup_ids.append(cleanup_id)
        previous = cleanup_id
    phases.append(Phase(target + '-incoming-build-cleanup', (*base, 'cleanup', '--recipe', str(recipe)),
                        str(snapshot), timeout=240, environment=env, dependencies=tuple(cleanup_ids),
                        always=True, kind='cleanup', artifacts=(str(recipe),)))
    return Plan('Logistics', 'Incoming files on phone and tablet',
                dict(source, incoming_receiver=QA_BUNDLE, device_lifecycle='new owned sender and receiver per profile; remove after evidence'),
                tuple(phases), str(workspace), backend=project.backend_options(target, 'Test')[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'test', 'cleanup-devices', 'cleanup'))
    parser.add_argument('--root', type=Path)
    parser.add_argument('--platform', choices=('ios', 'android'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--recipe', type=Path)
    parser.add_argument('--owner-root', type=Path)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--profile', choices=('phone', 'tablet', 'iphone', 'ipad'))
    parser.add_argument('--model')
    parser.add_argument('--runtime')
    args = parser.parse_args()
    from build_manager.native_commands import interrupt
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupt)
    if args.action == 'cleanup':
        if args.recipe is None:
            parser.error('cleanup requires --recipe')
        if args.recipe.exists():
            cleanup(args.recipe)
    elif args.action == 'prepare':
        if args.root is None or args.platform is None or args.output is None:
            parser.error('prepare requires --root, --platform and --output')
        if args.owner_root is None:
            prepare(args.root, args.platform, args.output)
        else:
            from logistics_build.build_retention import compiler_cache
            with compiler_cache('incoming-go', args.owner_root) as cache:
                prepare(args.root, args.platform, args.output, environment={'GOCACHE': str(cache)})
    else:
        if any(value is None for value in (args.recipe, args.platform, args.profile, args.workspace, args.output)):
            parser.error('test and cleanup-devices require --recipe, --platform, --profile, --workspace and --output')
        if args.action == 'cleanup-devices' and not args.workspace.exists():
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / 'final-cleanup.json').write_text('[]\n')
            return
        record = json.loads(args.recipe.read_text())
        if args.platform == 'ios':
            from build_manager.apple_simulators import AppleSimulators
            from mobile_build.validation.incoming_ios_tools import run_suite
            if args.action == 'cleanup-devices':
                from build_manager.locking import operation_lock_path, workspace_lock
                with workspace_lock(operation_lock_path(args.workspace)):
                    cleanup_ios(AppleSimulators(), args.workspace, args.output / 'final-cleanup.json')
            else:
                if args.model is None or args.runtime is None:
                    parser.error('iOS test requires --model and --runtime')
                run_suite(record, record['sender'], args.workspace, args.output,
                          profile=args.profile, model=args.model, runtime=args.runtime)
        else:
            from mobile_build.validation.incoming_android import run_suite, cleanup as cleanup_android
            if args.action == 'cleanup-devices':
                rows = cleanup_android(args.workspace, record['sender'], args.output, profile=args.profile)
                (args.output / 'final-cleanup.json').write_text(json.dumps(rows, indent=2) + '\n')
            else:
                run_suite(record, record['sender'], args.workspace, args.output, profile=args.profile)


if __name__ == '__main__':
    main()
