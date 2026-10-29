"""Compile real widget extensions and run shared storage checks in owned scratch."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import plistlib
import subprocess
import time

from logistics_build.build_retention import scratch
from mobile_build.build_support.widget_build import configure_ios, EXTENSIONS
from mobile_build.select_ios_sdk import choose, installed
from mobile_build.tests.tooling.widget_project import make_project

ROOT = Path(__file__).resolve().parents[2]


def run(command, env, output):
    with output.open('w') as stream:
        result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Native widget check failed; see {output}')


def watch_products(app, platform, env):
    watch = app / 'Watch/LogisticsWatch.app'
    complication = watch / 'PlugIns/LogisticsWatchWidget.appex'
    binaries = {}
    for product, name in ((watch, 'LogisticsWatch'), (complication, 'LogisticsWatchWidget')):
        info = plistlib.loads((product / 'Info.plist').read_bytes())
        if info['CFBundleVersion'] != '123' or info['DTPlatformName'] != platform:
            raise RuntimeError('Watch product version/platform does not match the containing app.')
        for binary in (product / name, *product.glob('*.dylib')):
            dependencies = subprocess.check_output(['xcrun', 'otool', '-L', str(binary)], env=env, text=True)
            if any(runtime in dependencies.lower() for runtime in ('python', 'toga', 'logisticscloud', 'vlckit')):
                raise RuntimeError('Application runtime dependency found in Watch product.')
            binaries[str(binary.relative_to(app))] = dict(bytes=binary.stat().st_size, libraries=dependencies)
    return binaries


def validate(output, *, device_build=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    developer, sdk = choose(installed())
    env = dict(os.environ, DEVELOPER_DIR=developer)
    started = time.monotonic()
    report = dict(status='running', sdk=sdk, scope='native storage/snapshot execution and iOS/watchOS simulator packaging',
                  physical_shortcuts_invocation=False, physical_widget_latency=False, physical_watch_sync=False,
                  unsigned_device_build=False)
    try:
        with scratch() as workspace:
            shared = ROOT / 'Python/commonUtils/ui/native/ios'
            checks = ROOT / 'Python/commonUtils/tests/native/WidgetValueStoreChecks.swift'
            run(['xcrun', 'swiftc', '-parse-as-library', '-module-cache-path', str(workspace / 'modules'),
                 str(shared / 'WidgetValueStore.swift'), str(checks), '-o', str(workspace / 'store-checks')],
                env, output / 'store-compile.log')
            run([str(workspace / 'store-checks'), str(workspace / 'values')], env, output / 'store-checks.log')
            run(['xcrun', 'swiftc', '-parse-as-library', '-module-cache-path', str(workspace / 'modules'),
                 str(shared / 'WidgetValueStore.swift'),
                 str(ROOT / 'Python/mobile/ios/widgets/WatchValueSnapshot.swift'),
                 str(ROOT / 'mobile_build/native_tests/ios/WatchValueSnapshotChecks.swift'),
                 '-o', str(workspace / 'watch-checks')], env, output / 'watch-compile.log')
            run([str(workspace / 'watch-checks'), str(workspace / 'watch-values')], env, output / 'watch-checks.log')
            pbx = make_project(workspace / 'project')
            configure_ios(pbx.parent.parent, include_watch=True)
            run(['xcodebuild', '-project', str(pbx.parent), '-scheme', 'Widget Probe', '-configuration', 'Debug',
                 '-sdk', 'iphonesimulator', '-destination', 'generic/platform=iOS Simulator',
                 '-derivedDataPath', str(workspace / 'derived'), 'CODE_SIGNING_ALLOWED=NO', 'ARCHS=arm64', 'build'],
                env, output / 'native-build.log')
            app = workspace / 'derived/Build/Products/Debug-iphonesimulator/Widget Probe.app'
            extensions = {}
            for product, suffix, _, local, generic in EXTENSIONS:
                folder = 'Extensions' if suffix == '.widget-actions' else 'PlugIns'
                extension = app / folder / (product + '.appex')
                metadata = json.loads((extension / 'Metadata.appintents/extract.actionsdata').read_text())
                dependencies = {}
                for binary in (extension / product, *extension.glob('*.dylib')):
                    text = subprocess.check_output(['xcrun', 'otool', '-L', str(binary)], env=env, text=True)
                    if any(name in text.lower() for name in ('python', 'toga', 'logisticscloud', 'vlckit')):
                        raise RuntimeError('Application runtime dependency found in lightweight extension.')
                    if suffix == '.widget-actions' and 'WatchConnectivity' in text:
                        raise RuntimeError('Watch Connectivity must run in the phone app, not Set Widget Value.')
                    dependencies[binary.name] = dict(bytes=binary.stat().st_size, libraries=text)
                extensions[product] = dict(actions=metadata['actions'], binaries=dependencies)
            action = extensions['LogisticsWidgetActions']['actions']['SetWidgetValue']
            if not action['isDiscoverable'] or action['openAppWhenRun']:
                raise RuntimeError('Set Widget Value must be discoverable and must not open the app.')
            host_actions = json.loads((app / 'Metadata.appintents/extract.actionsdata').read_text())['actions']
            sync_action = host_actions['SyncWidgetValuesToWatch']
            if not sync_action['isDiscoverable'] or sync_action['openAppWhenRun']:
                raise RuntimeError('Watch sync must be discoverable and run without foregrounding the app.')
            if 'SyncWidgetValuesToWatch' in extensions['LogisticsWidgetActions']['actions']:
                raise RuntimeError('Watch sync must execute in the containing phone app, not its extension.')
            watch_binaries = watch_products(app, 'watchsimulator', env)
            if device_build:
                run(['xcodebuild', '-project', str(pbx.parent), '-scheme', 'Widget Probe', '-configuration', 'Release',
                     '-sdk', 'iphoneos', '-destination', 'generic/platform=iOS',
                     '-derivedDataPath', str(workspace / 'derived-device'), 'CODE_SIGNING_ALLOWED=NO', 'build'],
                    env, output / 'native-device-build.log')
                device_app = workspace / 'derived-device/Build/Products/Release-iphoneos/Widget Probe.app'
                report.update(unsigned_device_build=True, device_watch_binaries=watch_products(device_app, 'watchos', env))
            report.update(extensions=extensions, host_actions=host_actions, watch_binaries=watch_binaries,
                source_sha256={str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
                for path in [*(shared / name for name in ('WidgetValueStore.swift', 'WidgetValueView.swift')),
                             *(ROOT / 'Python/mobile/ios/widgets').glob('*'),
                             *(ROOT / 'Python/mobile/ios/watch').glob('*.swift')]})
        report.update(status='passed', scratch_removed=True)
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        report.update(seconds=time.monotonic() - started, utc=datetime.now(timezone.utc).isoformat())
        (output / 'native-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Native widget/Watch storage and iOS/watchOS packaging passed; scratch removed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'test-results/widgets')
    parser.add_argument('--device-build', action='store_true', help='Also compile unsigned Release products for iPhone and Apple Watch hardware')
    args = parser.parse_args()
    validate(args.output, device_build=args.device_build)


if __name__ == '__main__':
    main()
