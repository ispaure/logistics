"""Compile current iOS video chrome and test it on a disposable simulator.

Uses an explicit existing VLCKit simulator framework; outputs and the simulator
are removed through build_manager even when the probe fails. No personal app or
simulator is modified. Results cover UIKit/decoder behavior, not physical touch.
"""
import argparse
import json
from hashlib import sha256
from pathlib import Path
import plistlib
import shutil
import subprocess
import time
from uuid import uuid4

from build_manager.apple_simulators import AppleSimulators
from logistics_build.build_retention import scratch

ROOT = Path(__file__).resolve().parents[2]


def run(framework, output, model, orientation='portrait'):
    output.mkdir(parents=True, exist_ok=False)
    client = AppleSimulators()
    device = None
    name = 'Build Manager Video Chrome QA ' + uuid4().hex
    bundle = 'io.github.ispaure.logisticsvideochromeqa'
    with scratch() as workspace:
        app = workspace / 'Video Chrome QA.app'
        app.mkdir()
        (app / 'Frameworks').mkdir()
        shutil.copytree(framework, app / 'Frameworks/VLCKit.framework', symlinks=True)
        source = workspace / 'main.m'
        controller = ROOT / 'Python/features/video/mobile/ios/VideoPlayer.m'
        fixture = ROOT / 'mobile_build/validation/fixtures/video_chrome_checks.m'
        source.write_text('#import ' + json.dumps(str(controller)) + '\n' + fixture.read_text())
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'], text=True).strip()
        command = ['xcrun', 'clang', '-fobjc-arc', '-fmodules', '-fmodules-cache-path=' + str(workspace / 'modules'),
                   '-target', 'arm64-apple-ios17.0-simulator', '-isysroot', sdk, '-F', str(framework.parent),
                   '-framework', 'UIKit', '-framework', 'AVFoundation', '-framework', 'CallKit', '-framework', 'VLCKit',
                   '-Wl,-rpath,@executable_path/Frameworks', str(source), '-o', str(app / 'VideoChromeQA')]
        result = subprocess.run(command, text=True, capture_output=True)
        (output / 'compile.log').write_text(result.stdout + result.stderr)
        result.check_returncode()
        (output / 'source.json').write_text(json.dumps(dict(model=model,
            sources={str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest()
                     for p in [*controller.parent.glob('*.m'), fixture]}), indent=2))
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=128x72:rate=12', '-t', '30', '-c:v', 'libx264', '-preset', 'ultrafast',
                        '-threads', '1', '-pix_fmt', 'yuv420p', str(app / 'fixture.mp4')], check=True)
        (app / 'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier=bundle,
            CFBundleName='Video Chrome QA', QAOrientation=orientation, CFBundleExecutable='VideoChromeQA', CFBundleVersion='1',
            CFBundleShortVersionString='1.0', CFBundlePackageType='APPL', MinimumOSVersion='17.0',
            UIDeviceFamily=[1, 2], UILaunchScreen={},
            UIApplicationSceneManifest=dict(UIApplicationSupportsMultipleScenes=False, UISceneConfigurations={
                'UIWindowSceneSessionRoleApplication': [dict(UISceneConfigurationName='QA', UISceneDelegateClassName='LGVideoChromeChecks')]}),
            UISupportedInterfaceOrientations=['UIInterfaceOrientationPortrait', 'UIInterfaceOrientationLandscapeLeft',
                                              'UIInterfaceOrientationLandscapeRight'])))
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True, capture_output=True)
        try:
            runtimes = json.loads(client.invoke('list', 'runtimes', '--json'))['runtimes']
            supported = sorted((r for r in runtimes if r.get('isAvailable') and r['name'].startswith('iOS')),
                               key=lambda r: tuple(map(int, r['version'].split('.'))), reverse=True)
            runtime, identifier = next((r['identifier'], row['identifier'])
                for r in supported for row in r['supportedDeviceTypes']
                if model in row['name'] and (model != 'iPhone' or 'Duo' not in row['name']))
            device = client.create(name, identifier, runtime)
            client.boot(device)
            client.invoke('install', device, str(app), timeout=120)
            client.invoke('launch', device, bundle)
            cache = Path(client.invoke('get_app_container', device, bundle, 'data')) / 'Documents/result.json'
            deadline = time.monotonic() + 50
            while time.monotonic() < deadline:
                if cache.exists():
                    report = json.loads(cache.read_text())
                    (output / 'result.json').write_text(json.dumps(report, indent=2))
                    for screenshot in cache.parent.glob('*.png'):
                        shutil.copyfile(screenshot, output / screenshot.name)
                    if not report['success']:
                        raise RuntimeError(report['error'])
                    print(json.dumps(dict(success=True, model=model, samples=len(report['samples']))))
                    return
                time.sleep(.2)
            raise TimeoutError('Video chrome probe did not produce a result')
        finally:
            if device is not None:
                try:
                    if 'cache' in locals() and cache.with_name('progress.json').exists():
                        shutil.copyfile(cache.with_name('progress.json'), output / 'progress.json')
                    logs = client.invoke('spawn', device, 'log', 'show', '--last', '1m', '--style', 'compact',
                                         '--predicate', 'process == "VideoChromeQA"')
                    (output / 'native.log').write_text(logs)
                finally:
                    client.remove(device, name)
                    (output / 'cleanup.json').write_text(json.dumps(dict(simulator_removed=True, device=device)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--framework', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model', choices=('iPhone Duo', 'iPhone', 'iPad'), default='iPhone Duo')
    parser.add_argument('--orientation', choices=('portrait', 'landscape'), default='portrait')
    args = parser.parse_args()
    run(args.framework.resolve(), args.output.resolve(), args.model, args.orientation)


if __name__ == '__main__':
    main()
