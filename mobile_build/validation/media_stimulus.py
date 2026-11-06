"""Disposable silent audio app for real system reservation changes in QA."""
from pathlib import Path
import plistlib
import subprocess
import wave

BUNDLE = 'io.github.ispaure.logisticsshellmediaqa'


def prepare(workspace, output):
    app = workspace / 'MediaQA.app'
    app.mkdir()
    with wave.open(str(app / 'silence.wav'), 'wb') as stream:
        stream.setparams((1, 2, 8000, 8000, 'NONE', 'not compressed'))
        stream.writeframes(b'\0' * 16000)
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'], text=True).strip()
    source = Path(__file__).resolve().parents[1] / 'native_tests/tests/logisticsmobile/silent_media.m'
    result = subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-fmodules',
        '-fmodules-cache-path=' + str(workspace / 'modules'), '-target', 'arm64-apple-ios17.0-simulator',
        '-isysroot', sdk, '-framework', 'UIKit', '-framework', 'AVFoundation', '-framework', 'MediaPlayer',
        str(source), '-o', str(app / 'MediaQA')], capture_output=True, text=True)
    (output / 'media-compile.log').write_text(result.stdout + result.stderr)
    result.check_returncode()
    info = dict(CFBundleIdentifier=BUNDLE, CFBundleName='Media QA', CFBundleExecutable='MediaQA',
        CFBundlePackageType='APPL', CFBundleVersion='1', CFBundleShortVersionString='1.0',
        MinimumOSVersion='17.0', UIDeviceFamily=[1, 2], UIBackgroundModes=['audio'], UILaunchScreen={},
        UIApplicationSceneManifest=dict(UIApplicationSupportsMultipleScenes=False,
            UISceneConfigurations={'UIWindowSceneSessionRoleApplication': [dict(
                UISceneConfigurationName='QA', UISceneDelegateClassName='MediaQA')]}),
        UISupportedInterfaceOrientations=['UIInterfaceOrientationPortrait',
            'UIInterfaceOrientationLandscapeLeft', 'UIInterfaceOrientationLandscapeRight'])
    (app / 'Info.plist').write_bytes(plistlib.dumps(info))
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True, capture_output=True)
    return app


def advance(client, device, cache, output, phase, host_bundle):
    """The probe, not the runner, asserts measured expansion AND contraction."""
    if phase == 'audio':
        client.invoke('launch', device, BUNDLE)
        ready = Path(client.invoke('get_app_container', device, BUNDLE, 'data')) / 'Documents/media-ready.json'
        import time
        deadline = time.monotonic() + 20
        while not ready.exists():
            if time.monotonic() > deadline:
                raise TimeoutError('Native audio did not start')
            time.sleep(.2)
        import json
        result = json.loads(ready.read_text())
        (output / 'media-ready.json').write_text(json.dumps(result))
        if not result.get('playing'):
            raise RuntimeError('Native audio did not play: ' + str(result))
        time.sleep(3)  # Let SpringBoard publish the real activity before returning.
        client.invoke('launch', device, host_bundle)
    elif phase == 'stopped':
        client.invoke('terminate', device, BUNDLE)
    else:
        raise ValueError('Unexpected media phase: ' + phase)
    (cache / 'continue').write_text(phase)
