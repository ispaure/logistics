"""Observe uninterrupted native AVI playback and bounded stalls over minutes.

An owned-device runner supplies the existing read-only fixture capability URLs.
No source movie is copied into the application or modified by this probe.
"""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from ctypes import c_bool
import json
from pathlib import Path
import time
import traceback
from urllib.request import urlopen

from mobile.screen_privacy import native_value
from .video_buffer_probe import VideoBufferProbe
from .video_probe import until
from .video_ui_probe import player_clock


async def exercise(app):
    output = Path(app.paths.cache) / 'video-timeline'
    output.mkdir(exist_ok=True)
    config = json.loads(Path(__file__).with_name('video-stall-fixture.json').read_text())
    report = dict(success=False, samples=[], jumps=[])
    native = container = None
    callbacks = []
    def save():
        (output / 'progress.json').write_text(json.dumps(report))
    def control(action):
        with urlopen(config['control'] + '/' + action, timeout=5) as response:
            return json.load(response)
    try:
        startup = getattr(app, 'startup_task', None)
        if startup is not None:
            await asyncio.shield(startup)
        from rubicon.objc import ObjCClass, Block
        native = ObjCClass(config.get('controller', 'LGVideoController')).alloc().init()
        native.videoURL = config['video']
        native.startMilliseconds = 0
        native.subtitleJSON = '[]'
        callbacks = [Block(lambda external: True, c_bool, c_bool), Block(lambda: True, c_bool)]
        native.allowed, native.requestPlay = callbacks
        container = ObjCClass(config.get('navigation', 'LGVideoNavigationController')).alloc().initWithRootViewController(native)
        container.modalPresentationStyle = 0
        app.main_window._impl.native.rootViewController.presentViewController(container, animated=False, completion=None)
        await until(lambda: native_value(native_value(native, 'view'), 'window') is not None)
        native.player.audio.muted = True
        native.startByUser()
        await until(lambda: native_value(native.player, 'isPlaying') and player_clock(native.player) > 250)
        native.fullscreen = True
        native.setControlsShown(False)
        started = time.monotonic()
        phase = 'uninterrupted'
        captured = set()
        prior = None
        for _ in range(int(config.get('duration', 235) * 4)):
            row = dict(wall=time.monotonic()-started, phase=phase,
                clock=player_clock(native.player), position=int(native.positionMilliseconds()), state=int(native_value(native.player, 'state')),
                **json.loads(str(native.playbackDiagnosticJSON())))
            if prior is not None:
                jump = row['clock'] - prior['clock'] - 1000*(row['wall']-prior['wall'])
                if jump > 3000:
                    report['jumps'].append(dict(before=prior,after=row,excess_ms=jump))
            report['samples'].append(row)
            for target in config.get('snapshots_at', []):
                if target not in captured and row['clock'] >= target * 1000:
                    native.player.saveVideoSnapshotAt(str(output / ('frame-' + str(target) + '.png')), withWidth=720, andHeight=512)
                    captured.add(target)
            prior = row
            if len(report['samples']) % 20 == 0:
                save()
            await asyncio.sleep(.25)
        report['last_clock_ms'] = player_clock(native.player)
        report['uninterrupted_forward_jump'] = bool(report['jumps'])
        for target in config.get('seek_targets', []):
            native.seekToMilliseconds(int(target * 1000))
            for _ in range(24):
                report['samples'].append(dict(wall=time.monotonic()-started,
                    phase='seek-' + str(target), clock=player_clock(native.player),
                    position=int(native.positionMilliseconds()),
                    **json.loads(str(native.playbackDiagnosticJSON()))))
                await asyncio.sleep(.25)
            native.player.saveVideoSnapshotAt(str(output / ('seek-' + str(target) + '.png')), withWidth=720, andHeight=512)
            await asyncio.sleep(.3)
            save()
        if config.get('stall_at') is not None:
            native.seekToMilliseconds(int(config['stall_at'] * 1000))
            await asyncio.sleep(3)
            await asyncio.to_thread(control, 'arm')
            await until(lambda: native_value(native.player, 'isPlaying'))
            for _ in range(60):
                if (await asyncio.to_thread(control, 'state'))['entered']:
                    break
                await asyncio.sleep(.1)
            else:
                raise AssertionError('Fixture did not enter the slow read')
            native.setNetworkWaiting(True)
            await until(lambda: bool(native.networkResumePending), timeout=25)
            held = int(native.positionMilliseconds())
            report['held_position'] = held
            await asyncio.sleep(2)
            await asyncio.to_thread(control, 'release')
            native.setNetworkWaiting(False)
            for _ in range(48):
                report['samples'].append(dict(wall=time.monotonic()-started,
                    phase='recovery', clock=player_clock(native.player),
                    position=int(native.positionMilliseconds()),
                    **json.loads(str(native.playbackDiagnosticJSON()))))
                await asyncio.sleep(.25)
            save()
            clock = player_clock(native.player)
            assert held <= clock < held + 16000, ('Recovery jumped away from held position', held, clock)
        report['success'] = not report['jumps'] and report['last_clock_ms'] >= config.get('minimum_clock_ms', 225000)
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        await asyncio.to_thread(control, 'release')
        if native is not None:
            done = app.loop.create_future()
            completion = Block(lambda: app.loop.call_soon_threadsafe(done.set_result, None), None)
            native.retireWithCompletion(completion)
            await asyncio.wait_for(done, 10)
            container.dismissViewControllerAnimated(False, completion=None)
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('VIDEO_TIMELINE_RESULT=' + json.dumps({k:v for k,v in report.items() if k != 'samples'}), flush=True)


class VideoTimelineProbe(VideoBufferProbe):
    def on_running(self):
        if getattr(self, '_video_probe_task', None) is None:
            self._video_probe_task = self.loop.create_task(exercise(self))


def main():
    return VideoTimelineProbe('Logistics Video QA', 'io.github.ispaure.logisticsmobile')
