"""Native video button dispatch, safe frames and orientation checks on owned iOS QA apps."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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
    if view.isKindOfClass(ObjCClass('UIControl')):
        yield view
    for child in native_value(view, 'subviews'):
        yield from buttons(child)


def dispatch(item):
    item.target.performSelector(item.action, withObject=item)


def presented_menu(native):
    return (native_value(native, 'presentedViewController') or
            native_value(native_value(native, 'navigationController'), 'presentedViewController'))


async def dismiss_menu(native):
    from rubicon.objc import Block
    loop = asyncio.get_running_loop()
    done = loop.create_future()
    completion = Block(lambda: loop.call_soon(done.set_result, None), None)
    # With a navigation container, dismiss the presented sheet itself. Asking
    # its child player to dismiss can dismiss the entire modal player instead.
    menu = presented_menu(native)
    await until(lambda: not native_value(menu, 'isBeingPresented') and
                native_value(menu, 'transitionCoordinator') is None)
    menu.dismissViewControllerAnimated(False, completion=completion)
    await asyncio.wait_for(done, 5)
    await until(lambda: presented_menu(native) is None)


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
    diagnostics = [dict(kind=str(button.objc_class.name),
                        label=str(native_value(button, 'accessibilityLabel') or ''),
                        identifier=str(native_value(button, 'accessibilityIdentifier') or ''),
                        hidden=bool(native_value(button, 'isHidden')), alpha=float(native_value(button, 'alpha')),
                        frame=frame(button, window)) for button in buttons(window)]
    (output / (name + '-native.json')).write_text(json.dumps(diagnostics, indent=2))
    folds = []
    if hasattr(view, 'reservedRegionsOfKind'):
        kind = ObjCClass('UIViewReservedRegionKind').divisionRegionKind()
        for region in view.reservedRegionsOfKind(kind, options=0):
            r = native_value(region, 'frame')
            folds.append([float(r.origin.x), float(r.origin.y), float(r.size.width), float(r.size.height)])
    items = list(native.mediaItems)
    assert all(item.customView is None for item in items), 'Media actions use custom views'
    found = set()
    for item in items:
        label = str(item.accessibilityLabel)
        # QA-only inspection: UIKit's bar control views do not copy the item's
        # accessibility metadata. Production uses only public native bar APIs.
        button = item.valueForKey('view')
        if button is None or native_value(button, 'window') != window or native_value(button, 'isHidden'):
            continue
        x, y, width, height = frame(button, window)
        if width < 1 or height < 1:
            continue
        assert width >= 36 and height >= 36, (label, 'collapsed native item', width, height)
        point = CGPoint(x + width / 2, y + height / 2)
        hit = window.hitTest(point, withEvent=None)
        assert hit == button or hit.isDescendantOfView(button), (label, 'native action is not hittable')
        rows.append(dict(label=label, frame=[x, y, width, height]))
        found.add(label)
    assert 'Done' in found and ('Play' in found or 'Pause' in found), ('Primary native actions missing', rows)
    bar = native_value(native_value(native, 'navigationController'), 'navigationBar')
    bar_frame = frame(bar, window)
    traits = native_value(native, 'traitCollection')
    edge = int(traits.verticalBarEdge) if hasattr(traits, 'verticalBarEdge') else 0
    coordinates = [row['frame'][0 if edge else 1] for row in rows]
    assert max(coordinates) - min(coordinates) <= 5, ('Native bar did not adopt its axis', edge, rows)
    view.layoutIfNeeded()
    bx, by, bw, bh = frame(native.bufferOverlay, view)
    assert bw > 0 and bh > 0, 'Buffering indicator has no layout'
    for fx, fy, fw, fh in folds:
        assert bx + bw <= fx or fx + fw <= bx or by + bh <= fy or fy + fh <= by, 'Buffering indicator overlaps fold'
    # The full surface and VLC's rendering child must survive rotation and
    # controls changes without retaining an earlier portrait/landscape size.
    movie = frame(native.movie, view)
    expected = [0, 0, float(native_value(view, 'bounds').size.width), float(native_value(view, 'bounds').size.height)]
    assert all(abs(a - b) < 1 for a, b in zip(movie, expected)), ('Movie does not fill player', movie, expected)
    for surface in native_value(native.movie, 'subviews'):
        rect = frame(surface, native.movie)
        assert all(abs(a - b) < 1 for a, b in zip(rect, expected)), ('VLC retained stale bounds', rect, expected)
    native.setControlsShown(False)
    view.layoutIfNeeded()
    assert frame(native.movie, view) == movie, 'Hiding controls moved/resized video'
    native.setControlsShown(True)
    view.layoutIfNeeded()
    assert frame(native.movie, view) == movie, 'Showing controls moved/resized video'
    controls = frame(native.controlsScroll, window)
    if not native.tabletop and not folds:
        # A side rail must not leave its former bottom inset below the timeline.
        physical_bottom = float(bounds.origin.y + bounds.size.height - window.safeAreaInsets.bottom)
        assert abs(controls[1] + controls[3] - physical_bottom) < 2, (
            'Timeline retains extra bottom safe-area space', controls, physical_bottom)
    return dict(name=name, pose=pose_snapshot(app), buttons=rows, folds=folds,
                movie=frame(native.movie, view), controls=frame(native.controlsScroll, view),
                buffering_frame=[bx, by, bw, bh], bar_frame=bar_frame, bar_edge=edge)


async def exercise(app):
    output = Path(app.paths.cache) / 'video-ui'
    output.mkdir(exist_ok=True)
    report = dict(success=False, cases=[], scope='native iOS video controls; simulated poses, no physical touch acceptance')
    try:
        startup = getattr(app, 'startup_task', None)
        if startup is not None:
            await asyncio.shield(startup)
        from features.images.mobile.decoding import decode_page
        from features.images.validation import image_dimensions
        from toga.platform import get_factory
        fixtures = Path(__file__).with_name('image-orientation-fixtures')
        oriented = output / 'orientation'
        oriented.mkdir(exist_ok=True)
        expected = json.loads((fixtures / 'manifest.json').read_text())
        for case in expected:
            data = (fixtures / (case['name'] + '.source')).read_bytes()
            size = image_dimensions(data)
            image = decode_page(data, size, size, get_factory().Image.__module__)
            assert tuple(image.size) == tuple(case['size']), (case['name'], image.size, case['size'])
            image.save(oriented / (case['name'] + '.png'))
        (oriented / 'manifest.json').write_text(json.dumps(expected))
        report['orientation_cases'] = len(expected)
        from commonUtils.runtime.resources.local import LocalFiles
        from features.video.mobile.player import open_video
        root = app.private_root / 'video-ui-fixtures'
        root.mkdir(parents=True, exist_ok=True)
        root.joinpath('movie.mkv').write_bytes(Path(__file__).with_name('video-fixtures').joinpath('tracks.mkv').read_bytes())
        assert await open_video(app, LocalFiles(root), 'movie.mkv')
        owner = app.video_player
        native = owner.native.native
        recent = next(session for session, _ in app.recent_items()
                      if session.kind == 'video' and session.title == 'movie.mkv')
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
            report['active_case'] = row
            row['before_play'] = dict(playing=bool(native_value(native.player, 'isPlaying')),
                allowed=owner.allowed(), audio=owner.audio_output.permitted(), position=owner.native.position()[0])
            indexed = {str(item.accessibilityLabel): item for item in native.mediaItems}
            dispatch(native.playButton)
            try:
                await until(lambda: 500 < player_clock(native.player) < 3000 and native_value(native.player, 'isPlaying'))
            except AssertionError:
                row['after_play'] = dict(playing=bool(native_value(native.player, 'isPlaying')),
                    allowed=owner.allowed(), audio=owner.audio_output.permitted(), position=owner.native.position()[0],
                    manual=bool(native.manualResumeRequired), pending=bool(native.pausePending),
                    native_allowed=bool(native.canPlay(False)), state=str(native_value(native.player, 'state')))
                report['cases'].append(row)
                raise
            dispatch(native.playButton)
            await until(lambda: not native_value(native.player, 'isPlaying'))
            position = owner.native.position()[0]
            row['seek_admission'] = dict(before_back=bool(native.canPlay(False)))
            dispatch(indexed['Back 10 seconds'])
            await until(lambda: owner.native.position()[0] <= max(250, position - 8500))
            row['seek_admission']['before_forward'] = bool(native.canPlay(False))
            dispatch(indexed['Forward 10 seconds'])
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
            dispatch(native.playButton)
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
            dispatch(indexed['Audio tracks'])
            await until(lambda: presented_menu(native) is not None)
            menu = presented_menu(native)
            labels = [str(action.title) for action in menu.actions]
            assert len(native.player.audioTracks) == 2, 'Multiple audio tracks were lost'
            assert any('English' in label for label in labels), labels
            assert any('French' in label for label in labels), labels
            row['audio_menu'] = labels
            await dismiss_menu(native)
            second = native.player.audioTracks[1]
            second.selectedExclusively = True
            await until(lambda: bool(native_value(second, 'isSelected')))
            row['before_subtitles'] = dict(native_allowed=bool(native.canPlay(False)),
                allowed=owner.allowed(), window=bool(native_value(native_value(native, 'view'), 'window')),
                container_window=bool(native_value(native_value(owner.native.container, 'view'), 'window')),
                target=str(indexed['Subtitles'].target), action=str(indexed['Subtitles'].action),
                state=str(native_value(native.player, 'state')), retired=bool(native.retired),
                presented=str(native_value(native, 'presentedViewController')))
            native.subtitleTracks(indexed['Subtitles'])
            await until(lambda: presented_menu(native) is not None)
            menu = presented_menu(native)
            row['subtitle_menu'] = [str(action.title) for action in menu.actions]
            assert 'Subtitles off' in row['subtitle_menu'] and len(native.player.textTracks) == 1
            await dismiss_menu(native)
            native.toggleFullscreen(None)
            assert not native_value(native.controls, 'isHidden'), 'Fullscreen entry hides paused controls'
            native.setControlsShown(False)
            # VLC rendering subviews must never steal the root tap target.
            from rubicon.objc import CGPoint
            surface = native_value(native, 'view')
            hit = surface.hitTest(CGPoint(10, 10), withEvent=None)
            assert not hit.isDescendantOfView(native.movie), 'VLC consumes surface touches'
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
                for orientation in ('portrait', 'landscape-left', 'landscape-right', 'portrait-upside-down'):
                    try:
                        await rotate(app, orientation, settle=1)
                    except AssertionError as error:
                        if orientation != 'portrait-upside-down' or 'UISceneErrorDomain Code=101' not in str(error):
                            raise
                        report.setdefault('unsupported_orientations', []).append(dict(
                            pose=pose, orientation=orientation, error=str(error),
                            child_mask=int(native_value(native, 'supportedInterfaceOrientations')),
                            container_mask=int(native_value(owner.native.container, 'supportedInterfaceOrientations'))))
                        continue
                    native.setControlsShown(True)
                    row = await record(app, native, output, pose + '-' + orientation)
                    row['device_state'] = json.loads(cache.joinpath('video-ui-pose-done.json').read_text())['state']
                    report['cases'].append(row)
        native.seekToMilliseconds(0)
        native.togglePlay(None)
        await until(lambda: native_value(native.player, 'isPlaying') and player_clock(native.player) > 500)
        # Decoder percentages can describe background prefetch. They must not
        # create a buffering HUD while rendered video is progressing.
        native.mediaPlayerBufferingChanged(.42)
        await asyncio.sleep(.3)
        assert native_value(native.bufferOverlay, 'isHidden')
        assert native_value(native.bufferLabel, 'isHidden')
        state, restored = await fullscreen_controls(owner, False)
        if '--pose-transitions' in arguments:
            window = native_value(native_value(native, 'view'), 'window')
            x, y, w, h = frame(native.movie, window)
            cache.joinpath('video-ui-pose-request.json').write_text(json.dumps(
                dict(sequence=1000, tap=[x + w / 2, y + h / 2])))
            await until(lambda: not native_value(native.controls, 'isHidden'), timeout=90)
            state['simulator_touch_reveal'] = True
        native.audioTracks(indexed['Audio tracks'])
        await until(lambda: presented_menu(native) is not None)
        await asyncio.sleep(3.3)
        assert not native_value(native.controls, 'isHidden'), 'Controls hid under track selector'
        await dismiss_menu(native)
        await until(lambda: native_value(native.controls, 'isHidden'), timeout=4.5)
        state['track_menu_resumes_auto_hide'] = True
        state['prefetch_hud_suppressed'] = True
        dispatch(indexed['Done'])
        await until(lambda: owner.closed)
        await until(restored)
        report['fullscreen'] = state
        await app.recent_opener(recent)()
        reopened = app.video_player
        assert reopened is not None and reopened is not owner and not reopened.closed
        await until(lambda: native_value(reopened.native.native.player, 'isPlaying'))
        assert reopened.native.position()[0] > 0, 'Recent video lost its saved resume position'
        assert len([entry for entry in app.recent_documents.sessions() if entry.identity == recent.identity]) == 1
        await reopened.close()
        report['recent_video_reopened_playing'] = True
        # The same owned native QA run verifies the reported iOS notebook issue.
        from services.documents.mobile_notebooks import open_notebook
        from .web_checks import wait_for_text
        from .notebook_pointer_checks import exercise_page_selection
        app.set_feature_enabled('notebooks', True, refresh=False)
        assert await open_notebook(app, name='Palm selection QA')
        await wait_for_text(app.notebook_panel.web, 'Palm selection QA')
        report['notebook_selection'] = await exercise_page_selection(app.notebook_panel)
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        owner = getattr(app, 'video_player', None)
        if owner is not None and owner.native is not None:
            report['presentation_failure'] = dict(
                child=str(native_value(owner.native.native, 'presentedViewController')),
                container=str(native_value(owner.native.container, 'presentedViewController')),
                child_orientations=int(native_value(owner.native.native, 'supportedInterfaceOrientations')),
                container_orientations=int(native_value(owner.native.container, 'supportedInterfaceOrientations')))
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
