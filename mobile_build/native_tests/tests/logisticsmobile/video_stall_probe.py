"""Native foreground progress, command feedback and real slow-range recovery.

A runner supplies capability URLs for a read-only fixture and stall controls.
The source can live on the host; this probe never stages a decrypted movie.
"""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
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
    output = Path(app.paths.cache) / 'video-stall'
    output.mkdir(exist_ok=True)
    config = json.loads(Path(__file__).with_name('video-stall-fixture.json').read_text())
    report = dict(success=False, samples=[])
    native = container = None
    callbacks = []
    def control(action):
        with urlopen(config['control'] + '/' + action, timeout=5) as response:
            return json.load(response)
    try:
        startup = getattr(app, 'startup_task', None)
        if startup is not None:
            await asyncio.shield(startup)
        from rubicon.objc import ObjCClass, Block
        from ctypes import c_bool
        native = ObjCClass(config.get('controller', 'LGVideoController')).alloc().init()
        native.videoURL = config['video']
        native.startMilliseconds = 0
        native.subtitleJSON = '[]'
        callbacks = [Block(lambda external: True, c_bool, c_bool), Block(lambda: True, c_bool)]
        native.allowed, native.requestPlay = callbacks
        container = ObjCClass(config.get('navigation', 'LGVideoNavigationController')).alloc().initWithRootViewController(native)
        container.modalPresentationStyle = 0
        host = app.main_window._impl.native.rootViewController
        host.presentViewController(container, animated=False, completion=None)
        await until(lambda: native_value(native_value(native, 'view'), 'window') is not None)
        native.player.audio.muted = True
        native.startByUser()
        await until(lambda: native_value(native.player, 'isPlaying') and player_clock(native.player) > 250)
        native.fullscreen = True
        native.setControlsShown(False)
        # A slow read-ahead request while frames are flowing must not pause VLC
        # or display buffering. Observe the real clock and frame counters.
        native.setNetworkWaiting(True)
        before = player_clock(native.player)
        for _ in range(40):
            report['samples'].append(dict(clock=player_clock(native.player), wall=time.monotonic(),
                **json.loads(str(native.playbackDiagnosticJSON()))))
            await asyncio.sleep(.25)
        assert player_clock(native.player) > before + 8000, 'Prefetch wait interrupted buffered playback'
        assert not native.networkResumePending, 'Prefetch wait became a decoder hold'
        assert not native.buffering, 'Buffering shown while video frames were flowing'
        native.setNetworkWaiting(False)
        report['prefetch_does_not_pause'] = True
        await asyncio.to_thread(control, 'arm')
        for _ in range(60):
            if (await asyncio.to_thread(control, 'state'))['entered']:
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('Fixture did not enter the slow read')
        native.setNetworkWaiting(True)
        await until(lambda: bool(native.networkResumePending), timeout=20)
        # VLC's input thread can remain blocked inside the read while Pause
        # is pending. Check our held checkpoint and actual rendered frames.
        held = int(native.positionMilliseconds())
        frames = json.loads(str(native.playbackDiagnosticJSON()))['displayedFrames']
        await asyncio.sleep(.8)
        assert int(native.positionMilliseconds()) == held, 'Checkpoint advanced through a real range stall'
        assert json.loads(str(native.playbackDiagnosticJSON()))['displayedFrames'] == frames, 'Renderer still progressing during hold'
        assert native.buffering and not native_value(native.bufferOverlay, 'isHidden')
        await asyncio.to_thread(control, 'release')
        native.setNetworkWaiting(False)
        assert int(native.startMilliseconds) == -1, 'Refill queued an unsolicited decoder seek'
        report['recovery_samples'] = []
        for _ in range(160):
            report['recovery_samples'].append(dict(clock=player_clock(native.player),
                **json.loads(str(native.playbackDiagnosticJSON()))))
            if native_value(native.player, 'isPlaying') and player_clock(native.player) > held + 250:
                break
            await asyncio.sleep(.125)
        else:
            raise AssertionError('Real range stall did not resume')
        report['real_stall_holds_and_recovers'] = True
        # Pause/Play feedback must follow requested state immediately, including
        # while the decoder's asynchronous commands have not completed yet.
        native.togglePlay(None)
        assert str(native.playButton.accessibilityLabel) == 'Play'
        assert not native.playRequested
        await until(lambda: not native_value(native.player, 'isPlaying'))
        native.setNetworkWaiting(True)
        native.setNetworkWaiting(False)
        await asyncio.sleep(.5)
        assert not native_value(native.player, 'isPlaying'), 'Readiness overrode manual Pause'
        native.togglePlay(None)
        assert str(native.playButton.accessibilityLabel) == 'Pause'
        assert native.playRequested
        await until(lambda: native_value(native.player, 'isPlaying'))
        report['immediate_intent_feedback'] = True
        if config.get('failure_test'):
            await asyncio.to_thread(control, 'fail')
            native.setTransportFailure('Video data could not be read. Check the connection, then press Play to retry.')
            await until(lambda: bool(native.manualResumeRequired), timeout=25)
            assert not native.buffering, 'Failed input retained an endless spinner'
            assert 'retry' in str(native.message.text)
            retry_position = int(native.positionMilliseconds())
            await asyncio.to_thread(control, 'release')
            native.startByUser()
            await until(lambda: native_value(native.player,'isPlaying') and player_clock(native.player) > retry_position + 250)
            report['failed_input_explicit_retry'] = True
        report['success'] = True
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
        print('VIDEO_STALL_RESULT=' + json.dumps(report), flush=True)


class VideoStallProbe(VideoBufferProbe):
    def on_running(self):
        if getattr(self, '_video_probe_task', None) is None:
            self._video_probe_task = self.loop.create_task(exercise(self))


def main():
    return VideoStallProbe('Logistics Video QA', 'io.github.ispaure.logisticsmobile')
