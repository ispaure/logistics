"""Compile production Android video code in a disposable native PiP QA shell."""
import argparse
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

from PIL import Image
from build_manager.android_emulators import AndroidEmulator
from build_manager.retention import lease, remove_tree
from logistics_build.build_retention import scratch, owned_scratch
from mobile_build.deployment import manager_settings

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = 'io.github.ispaure.logisticsvideopipqa'


def project_files(project):
    template = ROOT / 'mobile_build/build/logisticsmobile/android/gradle'
    shutil.copytree(template / 'gradle', project / 'gradle', dirs_exist_ok=True)
    shutil.copy2(template / 'gradlew', project / 'gradlew')
    (project / 'settings.gradle').write_text("include ':app'\n")
    (project / 'gradle.properties').write_text('android.useAndroidX=true\norg.gradle.jvmargs=-Xmx1024m\n')
    (project / 'build.gradle').write_text("""buildscript {
        repositories { google(); mavenCentral() }
        dependencies { classpath 'com.android.tools.build:gradle:9.3.1' }
    }
    allprojects { repositories { google(); mavenCentral() } }
    """)
    app = project / 'app'
    (app / 'src/main/java').mkdir(parents=True, exist_ok=True)
    native = ROOT / 'Python/features/video/mobile/android'
    fixture = ROOT / 'mobile_build/validation/fixtures/VideoPipQAActivity.java'
    shutil.copy2(fixture, app / 'src/main/java/VideoPipQAActivity.java')
    (app / 'build.gradle').write_text("""apply plugin: 'com.android.application'
    android {
        namespace 'io.github.ispaure.logisticsvideopipqa'
        compileSdk 36
        defaultConfig {
            applicationId 'io.github.ispaure.logisticsvideopipqa'
            minSdk 30
            targetSdk 36
            versionCode 1
            versionName '1'
            ndk { abiFilters 'arm64-v8a' }
        }
        compileOptions { sourceCompatibility JavaVersion.VERSION_1_8; targetCompatibility JavaVersion.VERSION_1_8 }
        sourceSets.main.java.srcDir(""" + json.dumps(str(native)) + """)
    }
    dependencies {
        implementation 'org.videolan.android:libvlc-all:3.7.5'
        implementation 'androidx.appcompat:appcompat:1.7.1'
        implementation 'com.google.android.material:material:1.12.0'
        implementation 'androidx.constraintlayout:constraintlayout:1.1.3'
        implementation 'androidx.swiperefreshlayout:swiperefreshlayout:1.1.0'
        implementation 'androidx.webkit:webkit:1.15.0'
    }
    """)
    (app / 'src/main/AndroidManifest.xml').write_text("""<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET"/>
    <application android:theme="@android:style/Theme.Material.Light.NoActionBar" android:label="Video PiP QA">
    <activity android:name="io.github.ispaure.logistics.video.VideoPipQAActivity" android:exported="true"
        android:supportsPictureInPicture="true" android:resizeableActivity="true"
        android:configChanges="orientation|keyboardHidden|screenSize|smallestScreenSize|screenLayout|uiMode">
        <intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter>
    </activity></application></manifest>""")
    return app / 'src/main/assets', [*native.rglob('*.java'), fixture]


@contextmanager
def retained_workspace(path, *, keep=False):
    if path.parent != ROOT / 'test-results/build-scratch' or not owned_scratch(path) or not (path / '.keep').is_file():
        raise ValueError('Reuse requires an explicitly pinned manager scratch workspace.')
    try:
        with lease(path):
            yield path
    finally:
        if not keep:
            (path / '.keep').unlink()
            remove_tree(path, ownership_files=('.manager-scratch',))


def run(output, *, reuse=None, image=None, model=None, software_decode=False, retain_build=False):
    output.mkdir(parents=True, exist_ok=False)
    options, _ = manager_settings.settings(ROOT / 'mobile_build')
    model = model or options['android.model']
    env = dict(os.environ, ANDROID_HOME=options['tools.android_sdk'],
               ANDROID_SDK_ROOT=options['tools.android_sdk'], JAVA_HOME=options['tools.java'])
    observations = {}
    def observe(emulator, serial, bundle, environment):
        request = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', bundle,
            'cat', 'cache/pip-capture.json'], env=environment, capture_output=True, timeout=15)
        try:
            value = json.loads(request.stdout)
        except (ValueError, UnicodeDecodeError):
            return
        name = value['name']
        if name not in ('fullscreen', 'white', 'yellow', 'back', 'off', 'restored'):
            raise ValueError('Unknown PiP evidence request')
        screen = subprocess.check_output([str(emulator.adb), '-s', serial, 'exec-out', 'screencap', '-p'],
            env=environment, timeout=15)
        if name == 'fullscreen':
            (output / 'fullscreen.png').write_bytes(screen)
            emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'rm', 'cache/pip-capture.json')
            emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'touch', 'cache/pip-capture-done')
            return
        image = Image.open(BytesIO(screen)).convert('RGB')
        # The fixture has a solid dark blue video plane; bright pixels inside
        # the PiP bounds are VLC's white/yellow subtitle glyphs.
        cropped = image.crop(tuple(value['bounds']))
        pixels = list(cropped.get_flattened_data())
        blue = sum(b > r + 20 and b > g + 10 and b < 150 for r, g, b in pixels)
        # Android briefly covers the resized PiP with an app-icon transition
        # surface. Wait for the actual video plane; white overlay pixels cannot
        # establish subtitle rendering.
        if blue < len(pixels) * .9:
            return
        (output / ('pip-' + name + '.png')).write_bytes(screen)
        observations[name] = dict(bounds=value['bounds'], clock=value['clock'], subtitle_track=value['subtitleTrack'],
            white=sum(r > 180 and g > 180 and b > 180 for r, g, b in pixels),
            yellow=sum(r > 180 and g > 180 and b < 100 for r, g, b in pixels),
            blue=blue)
        (output / 'pixels.json').write_text(json.dumps(observations, indent=2))
        emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'rm', 'cache/pip-capture.json')
        emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'touch', 'cache/pip-capture-done')
    with (scratch(ROOT) if reuse is None else retained_workspace(reuse, keep=retain_build)) as workspace:
        if retain_build: (workspace / '.keep').touch()
        (output / 'workspace.json').write_text(json.dumps(dict(workspace=str(workspace), retained=retain_build)))
        (output / 'configuration.json').write_text(json.dumps(dict(image=image or options['android.image'], model=model, software_decode=software_decode, gpu='host')))
        project = workspace / 'project'
        assets, sources = project_files(project)
        assets.mkdir(parents=True, exist_ok=True)
        (output / 'source.json').write_text(json.dumps({str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sources}, indent=2))
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
            'color=c=0x102040:size=640x360:rate=24', '-f', 'lavfi', '-i',
            'anullsrc=channel_layout=mono:sample_rate=44100', '-t', '60', '-threads', '1', '-c:v', 'libx264',
            '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '32k', '-shortest', str(assets / 'fixture.mp4')], check=True)
        (assets / 'captions.srt').write_text('1\n00:00:00,000 --> 00:00:10,000\nFIRST PIP CAPTION\n\n2\n00:00:10,000 --> 00:00:59,000\n<font color="#ffff00">SECOND PIP CAPTION</font>\n')
        with (output / 'android-build.log').open('w') as log:
            subprocess.run([str(project / 'gradlew'), '--offline', '--no-daemon', 'assembleDebug'], cwd=project,
                           env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1200, check=True)
        emulator = AndroidEmulator(options['tools.android_sdk'], workspace / ('emulator-' + uuid4().hex), environment=env,
                                   startup_timeout=600, gpu='host')
        record = None
        try:
            record = emulator.start(image or options['android.image'], model)
            serial = record['serial']
            emulator.invoke('-s', serial, 'install', str(project / 'app/build/outputs/apk/debug/app-debug.apk'), timeout=180)
            emulator.invoke('-s', serial, 'shell', 'settings', 'put', 'system', 'screen_off_timeout', '600000')
            # The OS tutorial can take focus after first entering immersive mode.
            emulator.invoke('-s', serial, 'shell', 'settings', 'put', 'secure', 'immersive_mode_confirmations', 'confirmed')
            emulator.invoke('-s', serial, 'shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
            emulator.invoke('-s', serial, 'shell', 'wm', 'dismiss-keyguard')
            emulator.invoke('-s', serial, 'shell', 'am', 'start', '-n', BUNDLE + '/io.github.ispaure.logistics.video.VideoPipQAActivity', '--ez', 'software_decode', str(software_decode).lower())
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                observe(emulator, serial, BUNDLE, env)
                value = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', BUNDLE,
                    'cat', 'cache/video-pip-result.json'], env=env, capture_output=True, timeout=15)
                try:
                    result = json.loads(value.stdout)
                except (ValueError, UnicodeDecodeError):
                    time.sleep(.3)
                    continue
                (output / 'android-result.json').write_text(json.dumps(result, indent=2))
                if not result['success']:
                    raise RuntimeError(result['error'])
                break
            else:
                raise TimeoutError('Native Android PiP acceptance timed out')
            assert set(observations) == {'white', 'yellow', 'back', 'off', 'restored'}, observations
            assert (output / 'fullscreen.png').is_file()
            for name in ('white', 'back', 'restored'):
                assert observations[name]['white'] > observations['off']['white'] + 10, observations
            assert observations['yellow']['yellow'] > observations['off']['yellow'] + 10, observations
            assert all(value['blue'] > 100 for value in observations.values()), observations
            acceptance = dict(success=True, controls=result['samples'], pixels=observations)
            (output / 'acceptance.json').write_text(json.dumps(acceptance, indent=2))
            print(json.dumps(acceptance), flush=True)
        finally:
            try:
                if record is not None:
                    (output / 'android-logcat.txt').write_text(emulator.invoke('-s', record['serial'], 'logcat', '-d'))
                    emulator.invoke('-s', record['serial'], 'uninstall', BUNDLE)
            finally:
                emulator.cleanup()
                lease = emulator.workspace / 'removed-lease.json'
                if lease.is_file(): shutil.copy2(lease, output / 'android-emulator-lease.json')
                log = emulator.workspace / 'emulator.log'
                if log.is_file(): shutil.copy2(log, output / 'android-emulator.log')
                (output / 'android-cleanup.json').write_text(json.dumps(dict(removed=not emulator.marker.exists())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse-workspace', type=Path, help='Explicitly pinned manager scratch build; removed after this run')
    parser.add_argument('--image', help='An already installed manager Android image')
    parser.add_argument('--model', help='Override the configured Android emulator hardware profile')
    parser.add_argument('--software-decode', action='store_true', help='Test-only workaround for virtual MediaCodec stalls')
    parser.add_argument('--retain-build', action='store_true', help='Pin the managed scratch build for an explicit retry; caller owns final removal')
    args = parser.parse_args()
    run(args.output.resolve(), reuse=args.reuse_workspace.resolve() if args.reuse_workspace else None,
        image=args.image, model=args.model, software_decode=args.software_decode, retain_build=args.retain_build)


if __name__ == '__main__':
    main()
