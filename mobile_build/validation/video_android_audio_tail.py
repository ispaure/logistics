"""Exercise the Android LibVLC audio tail and seek recovery on an owned emulator."""

import argparse
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
from logistics_build.build_retention import scratch
from mobile_build.deployment import manager_settings
from mobile_build.validation.video_android_pip_tools import BUNDLE, ROOT, project_files

ACTIVITY = 'VideoAudioTailQAActivity'


def run(output, image=None, model=None, *, video_tail=False, captions=False, startup_control=False):
    if video_tail and startup_control:
        raise ValueError('The ordinary startup control compares the forward restore path')
    output.mkdir(parents=True, exist_ok=False)
    options, _ = manager_settings.settings(ROOT / 'mobile_build')
    sdk = options['tools.android_sdk']
    env = dict(os.environ, ANDROID_HOME=sdk, ANDROID_SDK_ROOT=sdk, JAVA_HOME=options['tools.java'])
    with scratch(ROOT) as workspace:
        project = workspace / 'project'
        assets, sources = project_files(project, ACTIVITY, config_changes=(
            '|density|fontScale|fontWeightAdjustment|locale|layoutDirection|colorMode'
            '|keyboard|navigation|touchscreen|mcc|mnc'))
        assets.mkdir(parents=True)
        (output / 'source.json').write_text(json.dumps({
            str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in sources
        }, indent=2))
        movie = assets / 'tail.mkv'
        video_seconds, audio_seconds = (12, 3) if video_tail else (4, 12)
        other_audio = ['-f', 'lavfi', '-i', f'sine=frequency=880:sample_rate=48000:duration={audio_seconds}']
        other_track = ['-map', '2:a', '-metadata:s:a:0', 'language=eng',
                       '-metadata:s:a:1', 'language=fra']
        subtitle_source, subtitle_track = [], []
        if captions:
            cues = workspace / 'captions.srt'
            cues.write_text('1\n00:00:00,100 --> 00:00:03,950\n<font color="#ffff00">BASELINE CAPTION</font>\n\n'
                            '2\n00:00:06,000 --> 00:00:20,000\n<font color="#ffff00">TAIL CAPTION</font>\n')
            subtitle_source = ['-i', str(cues)]
            subtitle_track = ['-map', '3:s', '-c:s', 'srt',
                '-metadata:s:s:0', 'language=eng', '-disposition:s:0', 'default']
        picture = 'color=c=0x102040:' if captions else 'testsrc2='
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
            f'{picture}size=160x90:rate=12:duration={video_seconds}', '-f', 'lavfi', '-i',
            f'sine=frequency=440:sample_rate=48000:duration={audio_seconds}', *other_audio, *subtitle_source,
            '-map', '0:v', '-map', '1:a', *other_track, *subtitle_track,
            '-c:v', 'libx265', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p10le',
            '-g', '24', '-bf', '2', '-x265-params', 'pools=1:frame-threads=1:log-level=error',
            '-c:a', 'eac3', '-ac', '6', str(movie)], check=True)
        with (output / 'android-build.log').open('w') as log:
            subprocess.run([str(project / 'gradlew'), '--offline', '--no-daemon', 'assembleDebug'],
                cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300, check=True)
        emulator = AndroidEmulator(sdk, workspace / ('emulator-' + uuid4().hex), environment=env,
                                   startup_timeout=600, gpu='host')
        record = None
        uninstalled = False
        try:
            record = emulator.start(image or options['android.image'], model or options['android.model'])
            serial = record['serial']
            apk = project / 'app/build/outputs/apk/debug/app-debug.apk'
            emulator.invoke('-s', serial, 'install', str(apk), timeout=180)
            emulator.invoke('-s', serial, 'shell', 'settings', 'put', 'system', 'screen_off_timeout', '600000')
            emulator.invoke('-s', serial, 'shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
            emulator.invoke('-s', serial, 'shell', 'wm', 'dismiss-keyguard')
            emulator.invoke('-s', serial, 'shell', 'am', 'start', '-n',
                BUNDLE + '/io.github.ispaure.logistics.video.' + ACTIVITY, '--ez', 'video_tail',
                str(video_tail).lower(), '--ez', 'captions', str(captions).lower(),
                '--ez', 'startup_control', str(startup_control).lower())
            deadline = time.monotonic() + 100
            captures = {}
            expected = {'baseline', 'backseek'}
            if video_tail:
                expected.update(('saved-tail', 'natural-tail'))
            else:
                expected.add('replay')
            while time.monotonic() < deadline:
                if captions:
                    sample = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as',
                        BUNDLE, 'cat', 'cache/caption-request.json'], env=env, capture_output=True, timeout=15)
                    try:
                        request = json.loads(sample.stdout)
                    except (ValueError, UnicodeDecodeError):
                        request = None
                    if request is not None:
                        kind, run_id = request['kind'], request['run']
                        if kind not in expected or not run_id.isdecimal():
                            raise ValueError('Unknown Android caption evidence request')
                    if request is not None and (run_id, kind) not in captures:
                        screenshot = subprocess.check_output([str(emulator.adb), '-s', serial,
                            'exec-out', 'screencap', '-p'], env=env, timeout=15)
                        image = Image.open(BytesIO(screenshot)).convert('RGB')
                        w, h = image.size
                        marker = image.crop((0, 0, w // 3, h // 4)).get_flattened_data()
                        showing_player = sum(r > 245 and 10 < g < 40 and 220 < b < 245
                                             for r, g, b in marker) > 30
                        if showing_player:
                            pixels = image.crop((w // 10, h // 3, w * 9 // 10, h * 4 // 5)).get_flattened_data()
                            yellow = sum(r > 210 and g > 210 and b < 70 for r, g, b in pixels)
                            blue = sum(25 < b < 130 and b > g + 12 and g > r + 5 for r, g, b in pixels)
                            (output / (kind + '-latest.png')).write_bytes(screenshot)
                            if yellow >= 10 and blue >= 100:
                                captures[(run_id, kind)] = dict(clock=request['clock'], yellow=yellow, blue=blue)
                                (output / (kind + '.png')).write_bytes(screenshot)
                                emulator.invoke('-s', serial, 'shell', 'run-as', BUNDLE, 'touch',
                                                f'cache/caption-{run_id}-{kind}.done')
                value = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', BUNDLE,
                    'cat', 'cache/audio-tail-result.json'], env=env, capture_output=True, timeout=15)
                try:
                    result = json.loads(value.stdout)
                except (ValueError, UnicodeDecodeError):
                    time.sleep(.3)
                    continue
                (output / 'android-result.json').write_text(json.dumps(result, indent=2))
                pixels = {kind: value for (run_id, kind), value in captures.items() if run_id == result['run']}
                if captions:
                    (output / 'caption-pixels.json').write_text(json.dumps(pixels, indent=2))
                if not result['success']:
                    raise RuntimeError(result['error'])
                if captions and set(pixels) != expected:
                    raise AssertionError('Native captions were not proven wherever the video was active')
                print(f'Android native audio-tail checks passed. Report: {output / "android-result.json"}', flush=True)
                break
            else:
                raise TimeoutError('Android native audio-tail checks timed out')
        finally:
            try:
                if record is not None:
                    serial = record['serial']
                    try:
                        (output / 'android-logcat.txt').write_text(emulator.invoke('-s', serial, 'logcat', '-d'))
                    finally:
                        emulator.invoke('-s', serial, 'uninstall', BUNDLE)
                        uninstalled = True
            finally:
                emulator.cleanup()
                for name in ('removed-lease.json', 'emulator.log'):
                    evidence = emulator.workspace / name
                    if evidence.is_file():
                        shutil.copy2(evidence, output / name)
                (output / 'android-cleanup.json').write_text(json.dumps(dict(
                    uninstalled=uninstalled, removed=not emulator.marker.exists())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', help='An installed Build Manager Android image')
    parser.add_argument('--model', help='Override the configured emulator hardware profile')
    parser.add_argument('--video-tail', action='store_true', help='Give video an extra nine seconds after both audio tracks end')
    parser.add_argument('--captions', action='store_true', help='Check an embedded cue through and beyond the A/V tail')
    parser.add_argument('--startup-control', action='store_true', help='Measure ordinary video startup before the forward restore')
    args = parser.parse_args()
    run(args.output.resolve(), args.image, args.model, video_tail=args.video_tail,
        captions=args.captions, startup_control=args.startup_control)


if __name__ == '__main__':
    main()
