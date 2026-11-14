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
from mobile_build.build_support.video_build import install_remux_headers
from logistics_build.build_retention import scratch

ROOT = Path(__file__).resolve().parents[2]


def run(framework, output, model, orientation='portrait', hdr=False, resume=0, fold=False, *, movie=None, url=None, duration=30000, unknown_duration=False, pause_transitions=False, pip_controls=False, pip_subtitles=False, embedded_subtitles=False, external_display=False, airplay_controls=False):
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
        fixture = ROOT / 'mobile_build/validation/fixtures' / ('video_airplay_checks.m' if airplay_controls else 'video_chrome_checks.m')
        geometry = ('#define LG_VIDEO_FOLD_QA 1\n' +
                    (ROOT / 'mobile_build/validation/fixtures/video_fold_geometry.m').read_text()) if fold else ''
        source.write_text('#import ' + json.dumps(str(controller)) + '\n' + geometry + fixture.read_text())
        if airplay_controls:
            install_remux_headers(workspace)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'], text=True).strip()
        command = ['xcrun', 'clang', '-fobjc-arc', '-fmodules', '-fmodules-cache-path=' + str(workspace / 'modules'),
                   '-I', str(fixture.parent), '-I', str(workspace / 'VideoFFmpeg'), '-target', 'arm64-apple-ios17.0-simulator', '-isysroot', sdk, '-I', str(ROOT / 'Python/mobile/ios'), '-F', str(framework.parent),
                   '-framework', 'UIKit', '-framework', 'AVFoundation', '-framework', 'AVKit', '-framework', 'CoreImage', '-framework', 'CallKit', '-framework', 'VLCKit',
                   '-Wl,-rpath,@executable_path/Frameworks', str(source), '-o', str(app / 'VideoChromeQA')]
        result = subprocess.run(command, text=True, capture_output=True)
        (output / 'compile.log').write_text(result.stdout + result.stderr)
        result.check_returncode()
        (output / 'source.json').write_text(json.dumps(dict(model=model,
            sources={str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest()
                     for p in [*controller.parent.glob('*.m'), fixture, ROOT / 'mobile_build/validation/fixtures/video_pip_checks.m']}), indent=2))
        codec = (['-c:v', 'libx265', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p10le',
                  '-x265-params', 'pools=1:frame-threads=1:log-level=error:hdr10=1:colorprim=9:transfer=16:colormatrix=9',
                  '-color_primaries', 'bt2020', '-color_trc', 'smpte2084',
                  '-colorspace', 'bt2020nc', '-tag:v', 'hvc1'] if hdr else
                 ['-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p'])
        if pip_subtitles:
            (app / 'captions.srt').write_text('1\n00:00:00,000 --> 00:00:08,000\nFIRST PIP CAPTION\n\n2\n00:00:08,000 --> 00:00:29,000\n<font color="#ffff00">SECOND PIP CAPTION</font>\n')
        if movie is not None:
            shutil.copyfile(movie, app / 'fixture.mp4')
        else:
            audio = ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-c:a', 'aac'] if airplay_controls else []
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                            'color=c=0x102040:size=640x360:rate=24' if pip_subtitles else 'testsrc2=size=128x72:rate=12', *audio, '-t', '30',
                            '-threads', '1', *codec, str(app / 'fixture.mp4')], check=True)
        if embedded_subtitles:
            muxed = workspace / 'captioned.mp4'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(app / 'fixture.mp4'),
                '-i', str(app / 'captions.srt'), '-c:v', 'copy', '-c:s', 'mov_text',
                '-disposition:s:0', 'default', str(muxed)], check=True)
            shutil.move(muxed, app / 'fixture.mp4')
        if airplay_controls:
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:size=160x90:rate=24000/1001',
                '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '3', '-c:v', 'libx265',
                '-preset', 'ultrafast', '-pix_fmt', 'yuv420p10le', '-g', '48', '-bf', '2',
                '-x265-params', 'pools=1:frame-threads=1:log-level=error:hdr10=1:colorprim=9:transfer=16:colormatrix=9',
                '-c:a', 'libopus', '-ac', '6', str(app / 'airplay.mkv')], check=True)
        metadata = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_streams', '-of', 'json', str(app / 'fixture.mp4')], text=True)
        (output / 'fixture.json').write_text(metadata)
        if hdr:
            stream = json.loads(metadata)['streams'][0]
            assert (stream['pix_fmt'], stream['color_transfer'], stream['color_primaries']) == (
                'yuv420p10le', 'smpte2084', 'bt2020'), 'HDR fixture lost its depth or color tags'
        (app / 'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier=bundle,
            CFBundleName='Video Chrome QA', QAOrientation=orientation, QAHDR=hdr, QAResume=resume, QAFold=fold,
            QAURL=url or '', QADuration=duration, QAUnknownDuration=unknown_duration, QAStreamProbe=bool(url), QAPauseTransitions=pause_transitions, QAPipControls=pip_controls, QAPipSubtitles=pip_subtitles, QAPipEmbedded=embedded_subtitles, QAExternalDisplay=external_display, UIBackgroundModes=['audio'],
            NSAppTransportSecurity=dict(NSAllowsLocalNetworking=True),
            CFBundleExecutable='VideoChromeQA', CFBundleVersion='1',
            CFBundleShortVersionString='1.0', CFBundlePackageType='APPL', MinimumOSVersion='17.0',
            UIDeviceFamily=[1, 2], UILaunchScreen={},
            UIApplicationSceneManifest=dict(UIApplicationSupportsMultipleScenes=False, UISceneConfigurations={
                'UIWindowSceneSessionRoleApplication': [dict(UISceneConfigurationName='QA', UISceneDelegateClassName='LGVideoAirPlayChecks' if airplay_controls else 'LGVideoChromeChecks')]}),
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
            (output / 'lease.json').write_text(json.dumps(dict(device=device, name=name)))
            client.boot(device)
            client.invoke('install', device, str(app), timeout=120)
            client.invoke('launch', device, bundle)
            cache = Path(client.invoke('get_app_container', device, bundle, 'data')) / 'Documents/result.json'
            deadline = time.monotonic() + (100 if url or pip_subtitles else 50)
            backgrounded = False
            while time.monotonic() < deadline:
                if pip_subtitles and not backgrounded and cache.with_name('pip-ready.json').exists():
                    client.invoke('launch', device, 'com.apple.Preferences')
                    backgrounded = True
                    time.sleep(1)
                    client.invoke('io', device, 'screenshot', str(output / 'pip-background.png'))
                    cache.with_name('pip-background-ready').touch()
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
                    if 'cache' in locals() and cache.with_name('pip-progress.plist').exists():
                        shutil.copyfile(cache.with_name('pip-progress.plist'), output / 'pip-progress.plist')
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
    parser.add_argument('--hdr', action='store_true', help='Decode 10-bit BT.2020 PQ HEVC and inspect the native HDR layer.')
    parser.add_argument('--pip-subtitles', action='store_true', help='Exercise composited subtitles, real PiP/background, track-off/on and skip callbacks.')
    parser.add_argument('--pip-controls', action='store_true', help='Check live PiP delegate skips, boundaries and lock; no system PiP window.')
    parser.add_argument('--airplay-controls', action='store_true', help='Check local mute recovery and simulated receiver loading, seeks and route layout.')
    parser.add_argument('--external-display', action='store_true', help='Exercise the live drawable handoff into a synthetic external viewport.')
    parser.add_argument('--pause-transitions', action='store_true', help='Run native Play/Pause/Resume checks in both HDR modes without chrome timing checks.')
    parser.add_argument('--resume', type=int, default=0, help='Resume milliseconds in the 30-second fixture.')
    parser.add_argument('--fold', action='store_true', help='Exercise a synthetic horizontal division and lower control deck.')
    parser.add_argument("--embedded-subtitles", action="store_true", help="Test a muxed subtitle track with --pip-subtitles")
    args = parser.parse_args()
    if args.embedded_subtitles and not args.pip_subtitles:
        parser.error("--embedded-subtitles requires --pip-subtitles")
    run(args.framework.resolve(), args.output.resolve(), args.model, args.orientation, args.hdr, args.resume, args.fold, pause_transitions=args.pause_transitions, pip_controls=args.pip_controls, pip_subtitles=args.pip_subtitles, embedded_subtitles=args.embedded_subtitles, external_display=args.external_display, airplay_controls=args.airplay_controls)


if __name__ == '__main__':
    main()
