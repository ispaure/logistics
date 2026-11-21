"""Exercise native selected-file sharing on one Manager-owned iPhone simulator."""
import argparse
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import sys
import time
from uuid import uuid4

from build_manager.apple_simulators import AppleSimulators
from logistics_build.build_retention import scratch
from logistics_build.incoming_acceptance import ios_apps
from logistics_build.ios_backend import bundle_digest
from logistics_build.test_environments import load, runtime_id
from mobile_build.build_support import incoming_build
from mobile_build.deployment import manager_settings
from mobile_build.tools import stage
from . import document_storage_tools as devices
from . import incoming_ios_tools as fixture

ROOT = Path(__file__).resolve().parents[2]
PROBE = 'tests.logisticsmobile.outbound_ios_probe'
RECEIVER_GROUP = 'group.io.github.ispaure.logisticsoutgoingqa'


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def build_receiver(work, output, env):
    """Use the native ingestion extension in a separate disposable endpoint."""
    work.mkdir()
    project = fixture._project_files(work)
    app_info = work / 'Sender-Info.plist'
    app_metadata = plistlib.loads(app_info.read_bytes())
    app_metadata['CFBundleDisplayName'] = 'Outbound QA Receiver'
    app_info.write_bytes(plistlib.dumps(app_metadata))
    driver = fixture.SOURCES / 'OutboundShareUITests.swift'
    shutil.copyfile(driver, work / 'IncomingFilesUITests.swift')
    # The shared installer locates the normal app's metadata and scene launcher.
    dummy = work / 'LogisticsMobile'
    dummy.mkdir()
    (dummy / 'main.m').write_text('#import <UIKit/UIKit.h>\n')
    (dummy / 'LogisticsMobile-Info.plist').write_bytes(plistlib.dumps(
        dict(CFBundleShortVersionString='1.0', CFBundleVersion='1')))
    incoming_build.configure_ios(work)
    extension = work / 'IncomingShare'
    for name in ('Main.entitlements', 'Share.entitlements', 'IncomingFiles.m'):
        path = extension / name
        path.write_text(path.read_text().replace(incoming_build.GROUP, RECEIVER_GROUP))
    info = extension / 'Info.plist'
    metadata = plistlib.loads(info.read_bytes())
    metadata['CFBundleDisplayName'] = 'Outbound QA Receiver'
    info.write_bytes(plistlib.dumps(metadata))
    command = fixture._xcodebuild(project, 'generic/platform=iOS Simulator')
    command.remove('CODE_SIGNING_ALLOWED=NO')
    command.extend(('CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
                    'CODE_SIGN_STYLE=Manual', 'DEVELOPMENT_TEAM=', 'build-for-testing'))
    if fixture._logged(command, env, output / 'receiver-build.log', timeout=300):
        raise RuntimeError('Could not build the disposable iOS receiving endpoint.')
    app = work / 'DerivedData/Build/Products/Debug-iphonesimulator/Sender.app'
    extension_info = plistlib.loads((app / 'PlugIns/LogisticsInbox.appex/Info.plist').read_bytes())
    if (extension_info['CFBundleDisplayName'] != 'Outbound QA Receiver'
            or extension_info['CFBundleIdentifier'] != fixture.SENDER_BUNDLE + '.inbox'):
        raise ValueError('Generated Share extension identity differs.')
    write(output / 'receiver-build.json', dict(bundle=fixture.SENDER_BUNDLE,
        extension=extension_info['CFBundleIdentifier'], sha256=bundle_digest(app),
        driver_sha256=sha256((work / 'IncomingFilesUITests.swift').read_bytes()).hexdigest()))
    return project, app


def exercise(sender, output, env, *, receiver, project, bundle, result_name, runtime_id, **_options):
    client = AppleSimulators(env)
    runtime, model = devices.simulator_selection(client.devices()['devices'], 'iPhone', runtime_id)
    write(output / 'ios-build.json', dict(bundle=bundle, sha256=bundle_digest(sender)))
    token = 'Build Manager Outbound QA ' + uuid4().hex
    udid = client.create(token, model, runtime)
    lease = dict(device=udid, name=token, model=model, runtime=runtime, bundle=bundle)
    temporary = (fixture.RUNNER_BUNDLE, bundle, fixture.SENDER_BUNDLE)
    booted = False
    try:
        write(output / 'ios-lease.json', lease)
        client.boot(udid, name=token)
        booted = True
        if not client.matching(udid, token):
            raise RuntimeError('Simulator lease identity changed.')
        for app in (sender, receiver):
            client.invoke('install', udid, str(app), timeout=180)
        cache = Path(client.invoke('get_app_container', udid, bundle, 'data')) / 'Library/Caches'
        queue = fixture._container(udid, fixture.SENDER_BUNDLE, RECEIVER_GROUP, env) / 'Incoming'
        command = fixture._xcodebuild(project, f'platform=iOS Simulator,id={udid}')
        command.extend(('-collect-test-diagnostics', 'never', '-resultBundlePath', str(output / 'outbound.xcresult'),
                        '-only-testing:IntakeTests/OutboundShareUITests/testSelectedFileShare', 'test-without-building'))
        xctest = fixture._logged(command, env, output / 'outbound-xctest.log', timeout=360)
        report_file = cache / result_name
        deadline = time.monotonic() + (10 if xctest == 0 else 0)
        while not report_file.exists() and time.monotonic() < deadline:
            time.sleep(.2)
        if report_file.exists():
            shutil.copyfile(report_file, output / 'ios-result.json')
        state = fixture._queue_state(queue)
        write(output / 'recipient.json', state)
        if xctest or not report_file.exists():
            raise RuntimeError(f'iOS outbound XCTest did not pass (exit {xctest}); see outbound-xctest.log.')
        report = json.loads(report_file.read_bytes())
        if not report['success']:
            raise RuntimeError(report.get('error') or 'The iOS test app did not complete its checks.')
        expected = dict(name=report['filename'], raw_name=report['filename'],
                        length=report['bytes'], sha256=report['sha256'])
        if (list(state['ready'].values()) != [expected]
                or state['partial'] or state['failure']
                or list((cache / 'OutgoingShares').glob('share-*'))):
            raise RuntimeError('Recipient bytes or staging cleanup differ; see iOS and receiver reports.')
    finally:
        cleanup = dict(lease, removed=False, uninstalled=[], errors=[])
        try:
            if booted and client.matching(udid, token):
                apps = ios_apps(client, udid)
                for bundle_id in temporary:
                    if bundle_id in apps:
                        client.invoke('uninstall', udid, bundle_id, timeout=30)
                        cleanup['uninstalled'].append(bundle_id)
                cleanup['remaining'] = sorted(set(temporary).intersection(ios_apps(client, udid)))
        except Exception as error:
            cleanup['errors'].append(str(error))
        finally:
            try:
                client.remove(udid, token)
                cleanup['removed'] = client.matching(udid, token) is None
            finally:
                write(output / 'ios-cleanup.json', cleanup)
        if not cleanup['removed'] or cleanup.get('remaining'):
            raise RuntimeError('Owned iOS cleanup did not settle.')


def run(output):
    output.mkdir(parents=True)
    options, _ = manager_settings.settings(ROOT / 'mobile_build')
    with scratch(ROOT) as work:
        env = dict(os.environ, LOGISTICS_DEPLOY_WORKSPACE=str(work),
                   PATH=os.pathsep.join((str(Path(sys.executable).parent),
                       str(ROOT / 'mobile_build/.tools/go/bin'), os.environ['PATH'])),
                   GOCACHE=str(work / 'go-cache'), DEVELOPER_DIR=options['tools.xcode'])
        os.environ.update(env)
        payload = work / 'payload'
        write(output / 'source.json', stage(ROOT, payload, allow_dirty=True))
        project, receiver = build_receiver(work / 'endpoint', output, env)
        shutil.copyfile(ROOT / 'mobile_build/pyproject.toml', work / 'pyproject.toml')
        devices.run_ios(work, payload, output, env, entry_point=PROBE, result_name='outbound-share-result.json',
                        runtime_id=runtime_id(load(ROOT), 'iphone'),
                        exercise=partial(exercise, receiver=receiver, project=project))


def main():
    from build_manager.native_commands import interrupt
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupt)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    run(parser.parse_args().output.resolve())


if __name__ == '__main__':
    main()
