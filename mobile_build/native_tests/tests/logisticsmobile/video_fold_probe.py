"""Real native controls and chapters with a QA-only reserved-division fixture."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from ctypes import c_bool
import json
from pathlib import Path
import traceback

from mobile.screen_privacy import native_value
from .video_buffer_probe import VideoBufferProbe
from .video_probe import until
from .video_ui_probe import frame, player_clock, dismiss_menu, presented_menu


async def exercise(app):
    output = Path(app.paths.cache) / 'video-fold'
    output.mkdir(exist_ok=True)
    config = json.loads(Path(__file__).with_name('video-stall-fixture.json').read_text())
    report = dict(success=False, scope='QA reserved division; not physical posture acceptance')
    native = container = None
    callbacks = []
    try:
        startup = getattr(app, 'startup_task', None)
        if startup is not None: await asyncio.shield(startup)
        from rubicon.objc import ObjCClass, Block, CGPoint, objc_id
        from toga_iOS.libs import UIGraphicsImageRenderer
        from toga_iOS.images import nsdata_to_bytes
        native = ObjCClass('LGVideoPoseQAController').alloc().init()
        native.videoURL, native.startMilliseconds, native.subtitleJSON = config['video'], 0, '[]'
        callbacks = [Block(lambda external: True, c_bool, c_bool), Block(lambda: True, c_bool)]
        native.allowed, native.requestPlay = callbacks
        container = ObjCClass(config['navigation']).alloc().initWithRootViewController(native)
        container.modalPresentationStyle = 0
        app.main_window._impl.native.rootViewController.presentViewController(container, animated=False, completion=None)
        await until(lambda: native_value(native_value(native, 'view'), 'window') is not None)
        native.player.audio.muted = True
        native.startByUser()
        await until(lambda: native_value(native.player, 'isPlaying') and player_clock(native.player) > 300)
        view = native_value(native, 'view')
        window = native_value(view, 'window')
        def capture(name):
            renderer = UIGraphicsImageRenderer.alloc().initWithSize(native_value(window, 'bounds').size)
            def draw(context): window.drawViewHierarchyInRect(native_value(window, 'bounds'), afterScreenUpdates=True)
            (output / (name + '.png')).write_bytes(nsdata_to_bytes(renderer.PNGDataWithActions(Block(draw, None, objc_id))))
        native.applyTestFold(True)
        await asyncio.sleep(.5)
        view.layoutIfNeeded()
        report['movie'] = frame(native.movie, view)
        report['controls'] = frame(native.controlsScroll, view)
        midpoint = float(native_value(view, 'bounds').size.height) / 2
        report['hinge_partial'] = bool(native.hingePartiallyOpen)
        report['test_view'] = str(view.objc_class.name)
        assert native.tabletop
        assert report['movie'][1] + report['movie'][3] <= midpoint - 5
        assert report['controls'][1] >= midpoint + 6
        assert abs(report['controls'][0] + report['controls'][2]/2 - report['movie'][2]/2) < 1, 'Deck is not centered across the lower panel'
        report['buttons'] = []
        for row in (native.tabletopTransport, native.tabletopUtilities):
            for button in native_value(row, 'arrangedSubviews'):
                x,y,w,h = frame(button, window)
                assert min(w,h) >= 44, ('Small touch target', w,h)
                hit = window.hitTest(CGPoint(x+w/2,y+h/2),withEvent=None)
                assert hit == button or hit.isDescendantOfView(button), 'Deck action is not hittable'
                report['buttons'].append(dict(label=str(button.accessibilityLabel),frame=[x,y,w,h]))
        play_frame = frame(native.tabletopPlay,view)
        assert abs(play_frame[0] + play_frame[2]/2 - report['movie'][2]/2) < 1, 'Play button is not centered on the lower panel'
        native.setControlsShown(False)
        assert native.controlsVisible, 'Fold deck should remain available'
        capture('tabletop-playing')
        native.pause()
        await until(lambda: not native_value(native.player, 'isPlaying'))
        chapters = native.player.chapterDescriptionsOfTitle(int(native_value(native.player,'currentTitleIndex')))
        assert len(chapters) == 2
        report['chapters'] = [str(item.name) for item in chapters]
        native.chapters(native_value(native.tabletopUtilities, 'arrangedSubviews')[2])
        await until(lambda: presented_menu(native) is not None)
        report['chapter_menu'] = [str(action.title) for action in native_value(presented_menu(native),'actions')]
        assert any('Second scene' in title for title in report['chapter_menu'])
        await dismiss_menu(native)
        native.seekToMilliseconds(6000)
        assert int(native.positionMilliseconds()) == 6000
        await asyncio.sleep(.3)
        assert not native_value(native.player,'isPlaying'), 'Chapter seek overrode Pause'
        native.startByUser()
        await until(lambda: player_clock(native.player) > 6200)
        # Stale frame statistics must not produce a spinner when time advances.
        native.lastPlaybackProgress = 0
        native.observedClock = -1
        native.observedFrames = int(json.loads(str(native.playbackDiagnosticJSON()))['displayedFrames'])
        native.tick(None)
        assert not native.buffering
        report['moving_clock_suppresses_spinner'] = True
        native.applyTestFold(False)
        await asyncio.sleep(.3)
        view.layoutIfNeeded()
        assert not native.tabletop
        movie = frame(native.movie,view)
        assert abs(movie[3] - float(native_value(view,'bounds').size.height)) < 1
        capture('unfolded')
        native.seekToMilliseconds(11000)
        await until(lambda: bool(native.completed()),timeout=6)
        assert not native.playRequested
        native.startByUser()
        await until(lambda: native_value(native.player,'isPlaying') and 100 < player_clock(native.player) < 2000)
        report['completion_replays_from_start'] = True
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if native is not None:
            done = app.loop.create_future()
            callback = Block(lambda: app.loop.call_soon_threadsafe(done.set_result,None),None)
            native.retireWithCompletion(callback)
            await asyncio.wait_for(done,10)
            container.dismissViewControllerAnimated(False,completion=None)
        (output/'result.json').write_text(json.dumps(report,indent=2))
        print('VIDEO_FOLD_RESULT='+json.dumps(report),flush=True)


class VideoFoldProbe(VideoBufferProbe):
    def on_running(self):
        if getattr(self,'_video_probe_task',None) is None:
            self._video_probe_task=self.loop.create_task(exercise(self))


def main():
    return VideoFoldProbe('Logistics Video QA','io.github.ispaure.logisticsmobile')
