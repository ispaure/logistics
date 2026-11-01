"""Physical HDR probe using existing app signing; always restore the supplied app.

The temporary native-only app uses the same bundle ID without reading personal
files. Evidence goes to a unique cache folder. No uninstall or storage clearing.
"""
import argparse
from hashlib import sha1
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import time
from uuid import uuid4

from logistics_build.build_retention import scratch
from tests.readers.video_fixtures import hdr_movies

ROOT = Path(__file__).resolve().parents[2]


def require_hdr_success(report):
    """A collected report is evidence, not automatically a passing device test."""
    if not report.get('success'):
        raise RuntimeError(report.get('error') or 'Physical HDR probe failed')
    if not report.get('hdrActiveObserved'):
        raise RuntimeError('Physical HDR output was not observed')
    transitions = report.get('hdrTransitions', [])
    if [row.get('event') for row in transitions] != ['playing', 'paused', 'resumed'] * 2:
        raise RuntimeError('Physical HDR transition evidence is incomplete')


def restore_after_probe(device_command, template, bundle, folder, output, device):
    """Always attempt app restoration, even if the QA cleanup command raises."""
    cleaned = restored = None
    cleanup_error = restore_error = None
    try:
        try:
            cleaned = device_command('process', 'launch', '--terminate-existing', bundle,
                                     '--', '--cleanup-video-qa')
            (output / 'cache-cleanup.log').write_text(cleaned.stdout + cleaned.stderr)
            cleaned.check_returncode()
        except Exception as exc:
            cleanup_error = str(exc)
    finally:
        try:
            restored = device_command('install', 'app', template)
            (output / 'restore.log').write_text(restored.stdout + restored.stderr)
            restored.check_returncode()
        except Exception as exc:
            restore_error = str(exc)
            raise
        finally:
            (output / 'cleanup.json').write_text(json.dumps(dict(
                device=device, app_restored=restored is not None and restored.returncode == 0,
                cache_cleanup_requested=cleaned is not None and cleaned.returncode == 0,
                cache_folder=folder, cleanup_error=cleanup_error, restore_error=restore_error)))
    if cleanup_error:
        raise RuntimeError('Normal app restored, but QA cache cleanup failed: ' + cleanup_error)


def run(template, device, output, framework):
    output.mkdir(parents=True, exist_ok=False)
    info = plistlib.loads((template / 'Info.plist').read_bytes())
    bundle = info['CFBundleIdentifier']
    entitlements = subprocess.check_output(['codesign', '-d', '--entitlements', ':-', str(template)], stderr=subprocess.DEVNULL)
    folder = 'Library/Caches/LogisticsVideoQA-' + uuid4().hex
    def device_command(*args):
        return subprocess.run(['xcrun', 'devicectl', 'device', *map(str, args[:2]), '--device', device, *map(str, args[2:])],
                              capture_output=True, text=True, timeout=180)
    with scratch() as workspace:
        subprocess.run(['codesign', '-d', '--extract-certificates=' + str(workspace / 'signer'), str(template)],
                       check=True, capture_output=True)
        identity = sha1((workspace / 'signer0').read_bytes()).hexdigest()
        app = workspace / 'Video HDR QA.app'
        app.mkdir()
        (app / 'Frameworks').mkdir()
        shutil.copytree(framework, app / 'Frameworks/VLCKit.framework', symlinks=True)
        shutil.copyfile(template / 'embedded.mobileprovision', app / 'embedded.mobileprovision')
        source = workspace / 'main.m'
        source.write_text('#import ' + json.dumps(str(ROOT / 'Python/features/video/mobile/ios/VideoPlayer.m')) + '\n'
                          + (ROOT / 'mobile_build/validation/fixtures/video_chrome_checks.m').read_text())
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
        result = subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-fmodules',
            '-fmodules-cache-path=' + str(workspace / 'modules'), '-target', 'arm64-apple-ios17.4',
            '-isysroot', sdk, '-F', str(framework.parent), '-framework', 'UIKit', '-framework', 'AVFoundation',
            '-framework', 'CallKit', '-framework', 'VLCKit', '-framework', 'CoreVideo',
            '-Wl,-rpath,@executable_path/Frameworks', str(source), '-o', str(app / 'VideoHDRQA')],
            text=True, capture_output=True)
        (output / 'compile.log').write_text(result.stdout + result.stderr)
        result.check_returncode()
        fixture = hdr_movies(workspace / 'fixtures')[0][3]
        shutil.copyfile(fixture, app / 'fixture.mp4')
        metadata = subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(fixture)], text=True)
        (output / 'fixture.json').write_text(metadata)
        info.update(CFBundleExecutable='VideoHDRQA', CFBundleName='Video HDR QA', QAHDR=True, QAHDRProbe=True,
                    QAOutputDirectory=folder, UILaunchScreen={}, UIDeviceFamily=[1, 2],
                    UIApplicationSceneManifest=dict(UIApplicationSupportsMultipleScenes=False, UISceneConfigurations={
                        'UIWindowSceneSessionRoleApplication': [dict(UISceneConfigurationName='QA', UISceneDelegateClassName='LGVideoChromeChecks')]}))
        info.pop('UIMainStoryboardFile', None)
        (app / 'Info.plist').write_bytes(plistlib.dumps(info))
        signing = workspace / 'entitlements.plist'
        signing.write_bytes(entitlements)
        subprocess.run(['codesign', '--force', '--sign', identity, str(app / 'Frameworks/VLCKit.framework')],
                       check=True, capture_output=True)
        signed = subprocess.run(['codesign', '--force', '--deep', '--sign', identity, '--entitlements', str(signing), str(app)],
                                text=True, capture_output=True)
        (output / 'sign.log').write_text(signed.stdout + signed.stderr)
        signed.check_returncode()
        try:
            installed = device_command('install', 'app', app)
            (output / 'install.log').write_text(installed.stdout + installed.stderr)
            installed.check_returncode()
            launched = device_command('process', 'launch', '--terminate-existing', '--console', bundle)
            (output / 'launch.log').write_text(launched.stdout + launched.stderr)
            launched.check_returncode()
            for line in launched.stdout.splitlines():
                if 'LOGISTICS_HDR_RESULT=' in line:
                    report = json.loads(line.split('LOGISTICS_HDR_RESULT=', 1)[1])
                    (output / 'result.json').write_text(json.dumps(report, indent=2))
                    print(json.dumps(report), flush=True)
                    require_hdr_success(report)
                    return
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                copied = device_command('copy', 'from', '--domain-type', 'appDataContainer', '--domain-identifier', bundle,
                    '--source', folder + '/result.json', '--destination', output / 'result.json')
                (output / 'copy.log').write_text(copied.stdout + copied.stderr)
                if copied.returncode == 0 and (output / 'result.json').is_file():
                    report = json.loads((output / 'result.json').read_text())
                    print(json.dumps(report), flush=True)
                    require_hdr_success(report)
                    return
                time.sleep(2)
            raise TimeoutError('Physical HDR probe produced no report; normal app will be restored.')
        finally:
            # Only our UUID cache folder is removed, by the test executable.
            restore_after_probe(device_command, template, bundle, folder, output, device)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--framework', type=Path, required=True, help='Pinned VLCKit iPhoneOS framework with its SDK headers.')
    args = parser.parse_args()
    run(args.app.resolve(), args.device, args.output.resolve(), args.framework.resolve())
