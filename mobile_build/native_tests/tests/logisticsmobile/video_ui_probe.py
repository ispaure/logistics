"""Native video button dispatch, safe frames and orientation checks on owned iOS QA apps."""
import asyncio
import json
from pathlib import Path
import traceback

from mobile.app import LogisticsMobile
from mobile.screen_privacy import native_value
from .rotation_checks import rotate, pose_snapshot
from .video_probe import until, fullscreen_controls


def buttons(view):
    from rubicon.objc import ObjCClass
    if view.isKindOfClass(ObjCClass('UIButton')):
        yield view
    for child in native_value(view, 'subviews'):
        yield from buttons(child)


def frame(view, root):
    rect = view.convertRect(native_value(view, 'bounds'), toView=root)
    return [float(rect.origin.x), float(rect.origin.y), float(rect.size.width), float(rect.size.height)]


def player_clock(player):
    clock = native_value(player, 'time')
    value = native_value(clock, 'value') if clock is not None else None
    if value is None:
        return -1
    return int(value) if isinstance(value, (int, float)) else int(native_value(value, 'longLongValue'))


async def record(app, native, output, name):
    from rubicon.objc import Block, ObjCClass, CGPoint, objc_id
    from toga_iOS.libs import UIGraphicsImageRenderer
    from toga_iOS.images import nsdata_to_bytes

    view = native_value(native, 'view')
    window = native_value(view, 'window')
    bounds = native_value(window, 'bounds')
    renderer = UIGraphicsImageRenderer.alloc().initWithSize(bounds.size)
    def draw(context):
        window.drawViewHierarchyInRect(bounds, afterScreenUpdates=True)
    (output / (name + '.png')).write_bytes(nsdata_to_bytes(renderer.PNGDataWithActions(Block(draw, None, objc_id))))
    rows = []
    folds = []
    if hasattr(view, 'reservedRegionsOfKind'):
        kind = ObjCClass('UIViewReservedRegionKind').divisionRegionKind()
        for region in view.reservedRegionsOfKind(kind, options=0):
            r = native_value(region, 'frame')
            folds.append([float(r.origin.x), float(r.origin.y), float(r.size.width), float(r.size.height)])
    for button in buttons(native.controls):
        native.controlsScroll.scrollRectToVisible(button.convertRect(native_value(button, 'bounds'), toView=native.controlsScroll), animated=False)
        await asyncio.sleep(.05)
        x, y, width, height = frame(button, view)
        label = str(native_value(button, 'accessibilityLabel'))
        assert width >= 47.5 and height >= 47.5, (label, width, height)
        cx, cy, cw, ch = frame(native.controlsScroll, view)
        assert cx - 1 <= x and x + width <= cx + cw + 1, (label, 'clipped horizontally')
        assert cy - 1 <= y and y + height <= cy + ch + 1, (label, 'clipped vertically')
        for fx, fy, fw, fh in folds:
            assert x + width <= fx or fx + fw <= x or y + height <= fy or fy + fh <= y, (label, 'overlaps fold')
        point = CGPoint(x + width / 2, y + height / 2)
        hit = view.hitTest(point, withEvent=None)
        assert hit == button or hit.isDescendantOfView(button), (label, 'button is not hittable')
        rows.append(dict(label=label, frame=[x, y, width, height]))
    return dict(name=name, pose=pose_snapshot(app), buttons=rows, folds=folds,
                movie=frame(native.movie, view), controls=frame(native.controlsScroll, view))


async def exercise(app):
    output = Path(app.paths.cache) / 'video-ui'
    output.mkdir(exist_ok=True)
    report = dict(success=False, cases=[], scope='native iOS video controls; simulated poses, no physical touch acceptance')
    try:
        startup = getattr(app, 'startup_task', None)
        if startup is not None:
            await asyncio.shield(startup)
        from commonUtils.runtime.resources.local import LocalFiles
        from features.video.mobile.player import open_video
        root = app.private_root / 'video-ui-fixtures'
        root.mkdir(parents=True, exist_ok=True)
        root.joinpath('movie.mp4').write_bytes(Path(__file__).with_name('video-fixtures').joinpath('h264-aac.mp4').read_bytes())
        assert await open_video(app, LocalFiles(root), 'movie.mp4')
        owner = app.video_player
        native = owner.native.native
        from rubicon.objc import ObjCClass
        for orientation in ('portrait', 'landscape-left', 'landscape-right', 'portrait'):
            await rotate(app, orientation)
            await asyncio.sleep(.4)
            native.pause()
            if native_value(native.player, 'isSeekable'):
                native.seekToMilliseconds(500)
                await until(lambda: owner.native.position()[0] < 2000)
            await until(lambda: not native_value(native.player, 'isPlaying'))
            native.setControlsShown(True)
            row = await record(app, native, output, str(len(report['cases'])) + '-' + orientation)
            row['before_play'] = dict(playing=bool(native_value(native.player, 'isPlaying')),
                allowed=owner.allowed(), audio=owner.audio_output.permitted(), position=owner.native.position()[0])
            indexed = {str(native_value(button, 'accessibilityLabel')): button for button in buttons(native.controls)}
            native.playButton.sendActionsForControlEvents(1 << 6)
            try:
                await until(lambda: 500 < player_clock(native.player) < 3000 and native_value(native.player, 'isPlaying'))
            except AssertionError:
                row['after_play'] = dict(playing=bool(native_value(native.player, 'isPlaying')),
                    allowed=owner.allowed(), audio=owner.audio_output.permitted(), position=owner.native.position()[0],
                    manual=bool(native.manualResumeRequired), pending=bool(native.pausePending),
                    native_allowed=bool(native.canPlay(False)), state=str(native_value(native.player, 'state')))
                report['cases'].append(row)
                raise
            native.playButton.sendActionsForControlEvents(1 << 6)
            await until(lambda: not native_value(native.player, 'isPlaying'))
            position = owner.native.position()[0]
            row['seek_admission'] = dict(before_back=bool(native.canPlay(False)))
            indexed['Back 10 seconds'].sendActionsForControlEvents(1 << 6)
            await until(lambda: owner.native.position()[0] <= max(250, position - 8500))
            row['seek_admission']['before_forward'] = bool(native.canPlay(False))
            indexed['Forward 10 seconds'].sendActionsForControlEvents(1 << 6)
            try:
                await until(lambda: owner.native.position()[0] > position + 500)
            except AssertionError:
                row['seek_failure'] = dict(before=position, after=owner.native.position()[0],
                    allowed=owner.allowed(), audio=owner.audio_output.permitted(), native_allowed=bool(native.canPlay(False)),
                    seekable=bool(native_value(native.player, 'isSeekable')),
                    state=str(native_value(native.player, 'state')))
                report['cases'].append(row)
                raise
            requested = owner.native.position()[0]
            native.playButton.sendActionsForControlEvents(1 << 6)
            def resumed():
                return native_value(native.player, 'isPlaying') and player_clock(native.player) >= requested + 250
            try:
                await until(resumed)
            except AssertionError:
                row['resume_seek_failure'] = dict(requested=requested, decoder_time=player_clock(native.player),
                    state=str(native_value(native.player, 'state')), manual=bool(native.manualResumeRequired))
                report['cases'].append(row)
                raise
            row['decoder_seek_time'] = player_clock(native.player)
            native.pause()
            await until(lambda: not native_value(native.player, 'isPlaying'))
            row['paused_seek_resumed_at_target'] = True
            indexed['Audio and subtitles'].sendActionsForControlEvents(1 << 6)
            await until(lambda: native_value(native, 'presentedViewController') is not None)
            native.dismissViewControllerAnimated(False, completion=None)
            await until(lambda: native_value(native, 'presentedViewController') is None)
            native.toggleFullscreen(None)
            await until(lambda: native_value(native.controls, 'isHidden'))
            native.tapVideo(None)
            await until(lambda: not native_value(native.controls, 'isHidden'))
            native.toggleFullscreen(None)
            row['dispatch'] = ['play', 'pause', 'forward', 'back', 'tracks', 'fullscreen', 'tap-reveal', 'exit-fullscreen']
            report['cases'].append(row)
        arguments = [str(value) for value in ObjCClass('NSProcessInfo').processInfo.arguments]
        if '--pose-transitions' in arguments:
            cache = Path(app.paths.cache)
            for sequence, pose in enumerate(('closed', 'partial', 'open')):
                native.pause()
                cache.joinpath('video-ui-pose-request.json').write_text(json.dumps(dict(sequence=sequence, pose=pose)))
                def done():
                    path = cache / 'video-ui-pose-done.json'
                    return path.exists() and json.loads(path.read_text())['sequence'] == sequence
                await until(done, timeout=90)
                await asyncio.sleep(.6)
                assert app.video_player is owner and not owner.closed, 'Folding discarded the video'
                for orientation in ('portrait', 'landscape-left', 'landscape-right'):
                    await rotate(app, orientation)
                    native.setControlsShown(True)
                    row = await record(app, native, output, pose + '-' + orientation)
                    row['device_state'] = json.loads(cache.joinpath('video-ui-pose-done.json').read_text())['state']
                    report['cases'].append(row)
        native.seekToMilliseconds(0)
        native.togglePlay(None)
        await until(lambda: native_value(native.player, 'isPlaying'))
        state, restored = await fullscreen_controls(owner, False)
        indexed['Done'].sendActionsForControlEvents(1 << 6)
        await until(lambda: owner.closed)
        await until(restored)
        report['fullscreen'] = state
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        traceback.print_exc()
    finally:
        owner = getattr(app, 'video_player', None)
        if owner is not None:
            await owner.close()
        Path(app.paths.cache).joinpath('video-probe-result.json').write_text(json.dumps(report, indent=2))


class VideoUIProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'video-ui-private'
        super().startup()

    def on_running(self):
        if getattr(self, '_video_ui_task', None) is None:
            self._video_ui_task = self.loop.create_task(exercise(self))


def main():
    return VideoUIProbe('Video Controls QA', 'io.github.ispaure.logisticsmobile')
