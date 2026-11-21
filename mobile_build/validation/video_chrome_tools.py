"""Compile current iOS video chrome and test it on a disposable simulator.

Uses an explicit existing VLCKit simulator framework; outputs and the simulator
are removed through build_manager even when the probe fails. No personal app or
simulator is modified. Results cover UIKit/decoder behavior, not physical touch.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from hashlib import sha256
from pathlib import Path
import plistlib
import shutil
import subprocess
import time
from threading import Thread
from uuid import uuid4

from build_manager.apple_simulators import AppleSimulators
from mobile_build.build_support.video_build import install_remux_headers
from logistics_build.build_retention import scratch

ROOT = Path(__file__).resolve().parents[2]


def run(framework, output, model, orientation='portrait', hdr=False, resume=0, fold=False, *,
        movie=None, url=None, duration=30000, unknown_duration=False, pause_transitions=False,
        pip_controls=False, pip_subtitles=False, embedded_subtitles=False, external_display=False,
        airplay_controls=False, audio_switch=False, seek_recovery=False, audio_tail=False,
        video_tail=False, subtitle_tail=False, background_audio=False, runtime_version=None,
        inline_subtitles=False):
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
        fixture_movie = app / ('fixture.mkv' if audio_tail or video_tail or subtitle_tail or inline_subtitles else 'fixture.mp4')
        source = workspace / 'main.m'
        controller = ROOT / 'Python/features/video/mobile/ios/VideoPlayer.m'
        fixture = ROOT / 'mobile_build/validation/fixtures' / ('video_background_audio_checks.m' if background_audio else 'video_duration_tail_checks.m' if subtitle_tail else 'video_video_tail_checks.m' if video_tail else 'video_audio_tail_checks.m' if audio_tail else 'video_seek_recovery_checks.m' if seek_recovery else 'video_audio_switch_checks.m' if audio_switch else 'video_airplay_checks.m' if airplay_controls else 'video_chrome_checks.m')
        geometry = ('#define LG_VIDEO_FOLD_QA 1\n' +
                    (ROOT / 'mobile_build/validation/fixtures/video_fold_geometry.m').read_text()) if fold else ''
        source.write_text('#import ' + json.dumps(str(controller)) + '\n' + geometry + fixture.read_text())
        if airplay_controls:
            install_remux_headers(workspace)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'], text=True).strip()
        command = ['xcrun', 'clang', '-fobjc-arc', '-fmodules', '-fmodules-cache-path=' + str(workspace / 'modules'),
                   '-I', str(fixture.parent), '-I', str(framework / 'Headers'), '-I', str(workspace / 'VideoFFmpeg'), '-target', 'arm64-apple-ios17.0-simulator', '-isysroot', sdk, '-I', str(ROOT / 'Python/mobile/ios'), '-F', str(framework.parent),
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
        if background_audio:
            (app / 'captions.srt').write_text('1\n00:00:00,000 --> 00:00:29,000\nLOCAL VIDEO CAPTION\n')
        if movie is not None:
            shutil.copyfile(movie, fixture_movie)
        else:
            audio = ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-c:a', 'aac'] if airplay_controls or background_audio else []
            if subtitle_tail:
                audio = ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=3', '-c:a', 'aac']
            if video_tail:
                audio = ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=3',
                         '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000:duration=3',
                         '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:a', 'eac3', '-ac', '6',
                         '-metadata:s:a:0', 'language=eng', '-metadata:s:a:1', 'language=jpn']
            if audio_tail:
                audio = ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=10',
                         '-map', '0:v', '-map', '1:a', '-c:a', 'aac']
            if audio_switch:
                audio = ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
                         '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000',
                         '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:a', 'aac',
                         '-metadata:s:a:0', 'language=eng', '-metadata:s:a:1', 'language=fra']
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=128x72:rate=12:duration=3' if audio_tail else
                            'color=c=0x102040:size=640x360:rate=24' if pip_subtitles or inline_subtitles else 'testsrc2=size=128x72:rate=12', *audio, '-t', '3' if subtitle_tail else '10' if audio_tail or video_tail else '30',
                            '-threads', '1', *codec, str(fixture_movie)], check=True)
        if subtitle_tail:
            captions = workspace / 'long.srt'
            captions.write_text('1\n00:00:01,000 --> 00:00:20,000\nLONG CAPTION MUST NOT EXTEND PLAYBACK\n')
            muxed = workspace / 'long-caption.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(fixture_movie), '-i', str(captions),
                '-map', '0', '-map', '1', '-c', 'copy', str(muxed)], check=True)
            shutil.move(muxed, fixture_movie)
        if inline_subtitles:
            captions = workspace / 'inline.srt'
            captions.write_text('1\n00:00:00,400 --> 00:00:25,000\n<font color="#ff28cb">Subtitle check\nSecond line</font>\n')
            muxed = workspace / 'inline.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(fixture_movie), '-i', str(captions),
                '-map', '0:v', '-map', '1:s', '-c', 'copy', '-disposition:s:0', 'default', str(muxed)], check=True)
            shutil.move(muxed, fixture_movie)
        if embedded_subtitles or background_audio:
            muxed = workspace / 'captioned.mp4'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(fixture_movie),
                '-i', str(app / 'captions.srt'), '-c:v', 'copy', '-c:s', 'mov_text',
                '-disposition:s:0', 'default', str(muxed)], check=True)
            shutil.move(muxed, fixture_movie)
        if airplay_controls:
            reverse_captions = workspace / 'reverse.srt'
            reverse_captions.write_text('1\n00:00:06,000 --> 00:00:09,000\nVIDEO TAIL CAPTION\n\n2\n00:00:17,000 --> 00:00:40,000\nLONG SUBTITLE TAIL\n')
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=12:duration=18',
                '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=3', '-i', str(reverse_captions),
                '-map', '0:v', '-map', '1:a', '-map', '2:s', '-c:v', 'libx265', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p10le',
                '-g', '24', '-bf', '2', '-x265-params', 'pools=1:frame-threads=1:log-level=error',
                '-c:a', 'eac3', '-ac', '6', '-c:s', 'copy', str(app / 'reverse.mkv')], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(app / 'reverse.mkv'),
                '-map', '0', '-c:v', 'copy', '-c:a', 'libopus', '-ac', '2', '-c:s', 'copy',
                str(app / 'reverse-opus.mkv')], check=True)
            tail_captions = workspace / 'tail.srt'
            tail_captions.write_text('1\n00:01:00,000 --> 00:01:05,000\nAUDIO TAIL CAPTION\n\n2\n00:01:29,000 --> 00:01:50,000\nLONG SUBTITLE TAIL\n')
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=12:duration=3',
                '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=90', '-i', str(tail_captions),
                '-map', '0:v', '-map', '1:a', '-map', '2:s', '-c:s', 'copy', '-c:v', 'libx265', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p10le',
                '-g', '24', '-bf', '2', '-x265-params', 'pools=1:frame-threads=1:log-level=error',
                '-c:a', 'aac' if os.environ.get('LG_TAIL_AAC') else 'eac3',
                '-ac', '2' if os.environ.get('LG_TAIL_AAC') else '6', str(app / 'tail.mkv')], check=True)
            captions = workspace / 'airplay.srt'
            captions.write_text('1\n00:00:00,000 --> 00:00:05,000\nFIRST AIRPLAY CAPTION\n\n'
                                '2\n00:00:11,900 --> 00:00:13,500\n<i>CROSSING AIRPLAY CAPTION</i>\n')
            ass = workspace / 'airplay.ass'
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(captions), str(ass)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:size=160x90:rate=24000/1001',
                '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-i', str(captions), '-i', str(ass),
                '-map', '0:v', '-map', '1:a', '-map', '2:s', '-map', '3:s', '-t', '19', '-c:v', 'libx265',
                '-preset', 'ultrafast', '-pix_fmt', 'yuv420p10le', '-g', '48', '-bf', '2',
                '-x265-params', 'pools=1:frame-threads=1:log-level=error:hdr10=1:colorprim=9:transfer=16:colormatrix=9',
                '-c:a', 'libopus', '-ac', '6', '-c:s', 'copy', '-metadata:s:s:0', 'language=eng',
                '-metadata:s:s:1', 'language=fra', str(app / 'airplay.mkv')], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=24000/1001',
                '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-i', str(captions), '-i', str(ass),
                '-map', '0:v', '-map', '1:a', '-map', '2:s', '-map', '3:s', '-t', '19',
                '-c:v', 'libx264', '-preset', 'fast', '-g', '48', '-bf', '2', '-pix_fmt', 'yuv420p',
                '-c:a', 'libopus', '-ac', '6', '-c:s', 'copy', '-metadata:s:s:0', 'language=eng',
                '-metadata:s:s:1', 'language=fra', str(app / 'captions.mkv')], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(app / 'captions.mkv'),
                '-map', '0:v', '-map', '0:a', '-map', '0:s', '-c:v', 'copy',
                '-c:a', 'aac', '-c:s', 'mov_text', str(app / 'captions.mp4')], check=True)
        metadata = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_streams', '-of', 'json', str(fixture_movie)], text=True)
        (output / 'fixture.json').write_text(metadata)
        if hdr:
            stream = json.loads(metadata)['streams'][0]
            assert (stream['pix_fmt'], stream['color_transfer'], stream['color_primaries']) == (
                'yuv420p10le', 'smpte2084', 'bt2020'), 'HDR fixture lost its depth or color tags'
        (app / 'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier=bundle,
            CFBundleName='Video Chrome QA', QAOrientation=orientation, QAHDR=hdr, QAResume=resume, QAFold=fold,
            QAURL=url or '', QADuration=duration, QAUnknownDuration=unknown_duration, QAStreamProbe=bool(url), QAPauseTransitions=pause_transitions, QAPipControls=pip_controls, QAPipSubtitles=pip_subtitles, QAPipEmbedded=embedded_subtitles, QAExternalDisplay=external_display, QAInlineSubtitles=inline_subtitles, UIBackgroundModes=['audio'],
            NSAppTransportSecurity=dict(NSAllowsLocalNetworking=True),
            CFBundleExecutable='VideoChromeQA', CFBundleVersion='1',
            CFBundleShortVersionString='1.0', CFBundlePackageType='APPL', MinimumOSVersion='17.0',
            UIDeviceFamily=[1, 2], UILaunchScreen={},
            UIApplicationSceneManifest=dict(UIApplicationSupportsMultipleScenes=False, UISceneConfigurations={
                'UIWindowSceneSessionRoleApplication': [dict(UISceneConfigurationName='QA', UISceneDelegateClassName='LGVideoBackgroundAudioChecks' if background_audio else 'LGVideoDurationTailChecks' if subtitle_tail else 'LGVideoVideoTailChecks' if video_tail else 'LGVideoAudioTailChecks' if audio_tail else 'LGVideoSeekRecoveryChecks' if seek_recovery else 'LGVideoAudioSwitchChecks' if audio_switch else 'LGVideoAirPlayChecks' if airplay_controls else 'LGVideoChromeChecks')]}),
            UISupportedInterfaceOrientations=['UIInterfaceOrientationPortrait', 'UIInterfaceOrientationLandscapeLeft',
                                              'UIInterfaceOrientationLandscapeRight'])))
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True, capture_output=True)
        hls_server = None
        try:
            runtimes = json.loads(client.invoke('list', 'runtimes', '--json'))['runtimes']
            supported = sorted((r for r in runtimes if r.get('isAvailable') and r['name'].startswith('iOS')
                                and (runtime_version is None or r['version'] == runtime_version)),
                               key=lambda r: tuple(map(int, r['version'].split('.'))), reverse=True)
            target = next(((r['identifier'], row['identifier'])
                for r in supported for row in r['supportedDeviceTypes']
                if model in row['name'] and (model != 'iPhone' or 'Duo' not in row['name'])), None)
            if target is None:
                raise ValueError(f'No installed iOS runtime for {model} ({runtime_version or "latest"})')
            runtime, identifier = target
            device = client.create(name, identifier, runtime)
            (output / 'lease.json').write_text(json.dumps(dict(device=device, name=name, runtime=runtime, model=identifier)))
            client.boot(device, name=name)
            client.invoke('install', device, str(app), timeout=120)
            client.invoke('launch', device, bundle)
            cache = Path(client.invoke('get_app_container', device, bundle, 'data')) / 'Documents/result.json'
            deadline = time.monotonic() + (100 if url or pip_subtitles else 50)
            background_count = 0
            foreground_count = 0
            while time.monotonic() < deadline:
                if airplay_controls and hls_server is None and cache.with_name('hls-fixtures.json').exists():
                    hls_server = serve_airplay_fixtures(cache.parent)
                    shutil.copyfile(cache.with_name('hls-fixtures.json'), output / 'hls-fixtures.json')
                    shutil.copytree(cache.with_name('hls'), output / 'hls')
                    verify_airplay_fragments(output)
                if pip_subtitles and not background_count and cache.with_name('pip-ready.json').exists():
                    client.invoke('launch', device, 'com.apple.Preferences')
                    background_count += 1
                    time.sleep(1)
                    client.invoke('io', device, 'screenshot', str(output / 'pip-background.png'))
                    cache.with_name('pip-background-ready').touch()
                background_marker = 'background-ready' if not background_count else f'background-ready-{background_count}'
                foreground_marker = 'foreground-ready' if not foreground_count else f'foreground-ready-{foreground_count}'
                if background_audio and cache.with_name(background_marker).exists():
                    client.invoke('launch', device, 'com.apple.Preferences')
                    background_count += 1
                if background_audio and cache.with_name(foreground_marker).exists():
                    client.invoke('launch', device, bundle)
                    foreground_count += 1
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
            if hls_server is not None:
                hls_server.shutdown()
                hls_server.server_close()
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


def verify_airplay_fragments(output):
    """Decode each native fragment alone, as a receiver does after a seek."""
    checked = []
    for fragment in sorted((output / 'hls').glob('*/*/segment-*.m4s')):
        data = (fragment.parent / 'init.mp4').read_bytes() + fragment.read_bytes()
        result = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-i', 'pipe:0',
                                 '-f', 'null', '-'], input=data, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f'Native fragment failed to decode: {fragment.relative_to(output)}: {result.stderr.decode()}')
        checked.append(str(fragment.relative_to(output)))
    (output / 'fragment-decode.json').write_text(json.dumps(dict(success=True, fragments=checked), indent=2))


def serve_airplay_fixtures(documents):
    """Serve production playlists and native fragments to real simulator AVKit."""
    from features.video.mobile.mkv import master_playlist, playlist, webvtt_segment

    fixtures = json.loads((documents / 'hls-fixtures.json').read_text())
    for name, metadata in fixtures.items():
        root = documents / 'hls' / name
        audio = {f'audio-{track["id"]}': track for track in metadata['audio']}
        subtitles = {f'text-{track["id"]}': track for track in metadata['text']}
        boundaries = metadata['boundaries']
        (root / 'index.m3u8').write_bytes(master_playlist(audio, subtitles, metadata['defaultAudio'], 2_000_000, metadata['video']))
        for route in ('video', *audio):
            (root / route / 'index.m3u8').write_bytes(playlist(boundaries, 'm4s', initialization=True, end_ms=audio.get(route, {}).get('end_ms')))
        for route in subtitles:
            (root / route / 'index.m3u8').write_bytes(playlist(boundaries, 'vtt'))
            for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
                cues = json.loads((root / route / f'segment-{index}.json').read_text())
                (root / route / f'segment-{index}.vtt').write_bytes(webvtt_segment(
                    cues, start, end, timestamp_offset=metadata['subtitleTimestampOffset'], playable_end=boundaries[-1]))
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(documents / 'hls')))
    Thread(target=server.serve_forever, daemon=True).start()
    (documents / 'hls-urls.json').write_text(json.dumps([
        f'http://127.0.0.1:{server.server_port}/{name}/index.m3u8' for name in fixtures]))
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--framework', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model', choices=('iPhone Duo', 'iPhone', 'iPad'), default='iPhone Duo')
    parser.add_argument('--runtime', help='Use this installed iOS version instead of the newest compatible one.')
    parser.add_argument('--orientation', choices=('portrait', 'landscape'), default='portrait')
    parser.add_argument('--hdr', action='store_true', help='Decode 10-bit BT.2020 PQ HEVC and inspect the native HDR layer.')
    parser.add_argument('--pip-subtitles', action='store_true', help='Exercise composited subtitles, real PiP/background, track-off/on and skip callbacks.')
    parser.add_argument('--pip-controls', action='store_true', help='Check live PiP delegate skips, boundaries and lock; no system PiP window.')
    parser.add_argument('--subtitle-tail', action='store_true', help='Check a subtitle cue cannot extend playable A/V duration')
    parser.add_argument('--video-tail', action='store_true', help='Check video-only tails and language selection')
    parser.add_argument('--audio-tail', action='store_true', help='Play/reopen beyond video EOS with a longer real audio track, then return to video.')
    parser.add_argument('--seek-recovery', action='store_true', help='Recover real failed/stopped inputs at a new timeline target without autoplay.')
    parser.add_argument('--audio-switch', action='store_true', help='Check live two-language audio switches, paused intent and cancellation.')
    parser.add_argument('--background-audio', action='store_true', help='Check ordinary local background audio and protected-data lifecycle policy.')
    parser.add_argument('--airplay-controls', action='store_true', help='Check local mute recovery and simulated receiver loading, seeks and route layout.')
    parser.add_argument('--external-display', action='store_true', help='Exercise the live drawable handoff into a synthetic external viewport.')
    parser.add_argument('--inline-subtitles', action='store_true',
                        help='Check embedded SRT geometry through the inline control fade, with optional split panes.')
    parser.add_argument('--pause-transitions', action='store_true', help='Run native Play/Pause/Resume checks in both HDR modes without chrome timing checks.')
    parser.add_argument('--resume', type=int, default=0,
                        help='Resume position in milliseconds. With --audio-tail, check saved-position EOF and Replay.')
    parser.add_argument('--fold', action='store_true', help='Exercise a synthetic horizontal division and lower control deck.')
    parser.add_argument("--embedded-subtitles", action="store_true", help="Test a muxed subtitle track with --pip-subtitles")
    args = parser.parse_args()
    if args.embedded_subtitles and not args.pip_subtitles:
        parser.error("--embedded-subtitles requires --pip-subtitles")
    run(args.framework.resolve(), args.output.resolve(), args.model, args.orientation, args.hdr,
        args.resume, args.fold, pause_transitions=args.pause_transitions, pip_controls=args.pip_controls,
        pip_subtitles=args.pip_subtitles, embedded_subtitles=args.embedded_subtitles,
        external_display=args.external_display, airplay_controls=args.airplay_controls,
        audio_switch=args.audio_switch, seek_recovery=args.seek_recovery, audio_tail=args.audio_tail,
        video_tail=args.video_tail, subtitle_tail=args.subtitle_tail, background_audio=args.background_audio,
        runtime_version=args.runtime, inline_subtitles=args.inline_subtitles)


if __name__ == '__main__':
    main()
