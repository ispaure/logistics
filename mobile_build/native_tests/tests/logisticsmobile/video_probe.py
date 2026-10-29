"""Focused in-app video checks, run only on owned test devices/simulators."""
import asyncio
from io import BytesIO
import json
from pathlib import Path
import traceback

from mobile.app import LogisticsMobile


async def until(condition, timeout=20):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if condition():
            return
        await asyncio.sleep(.1)
    raise AssertionError('Native video condition timed out')


def android_player(owner):
    field = owner.native.native.getClass().getDeclaredField('player')
    field.setAccessible(True)
    return field.get(owner.native.native)


def screen_awake(owner, android):
    """Observe the real OS display-idle request without changing device settings."""
    if android:
        native = owner.native.native
        field = native.getClass().getDeclaredField('root')
        field.setAccessible(True)
        root = field.get(native)
        return lambda: bool(root.getKeepScreenOn())
    from rubicon.objc import ObjCClass
    from mobile.screen_privacy import native_value
    application = ObjCClass('UIApplication').sharedApplication
    return lambda: bool(native_value(application, 'isIdleTimerDisabled'))


def start_playback(owner):
    """Exercise the same explicit Play admission as the native controls."""
    owner.native.play()


async def android_frame(owner):
    from java import jclass, dynamic_proxy
    PixelCopy = jclass('android.view.PixelCopy')
    Bitmap = jclass('android.graphics.Bitmap')
    field = owner.native.native.getClass().getDeclaredField('video')
    field.setAccessible(True)
    pending = [field.get(owner.native.native)]
    surface = None
    while pending:
        view = pending.pop(0)
        if 'SurfaceView' in str(view.getClass().getName()) and 'subtitles' not in str(view.getResources().getResourceEntryName(view.getId())):
            surface = view
            break
        if hasattr(view, 'getChildCount'):
            pending.extend(view.getChildAt(index) for index in range(view.getChildCount()))
    assert surface is not None, 'VLC did not attach a video surface'
    bitmap = Bitmap.createBitmap(128, 72, Bitmap.Config.ARGB_8888)
    result = []
    class Copied(dynamic_proxy(PixelCopy.OnPixelCopyFinishedListener)):
        def onPixelCopyFinished(self, code):
            result.append(int(code))
    callback = Copied()
    PixelCopy.request(surface, bitmap, callback, jclass('android.os.Handler')(jclass('android.os.Looper').getMainLooper()))
    await until(lambda: result)
    assert result == [0], result
    colors = {int(bitmap.getPixel(x, y)) & 0xffffff for x in range(8, 120, 12) for y in range(8, 64, 12)}
    bitmap.recycle()
    assert len(colors) > 5, ('No decoded test-pattern frame', colors)
    return len(colors)


async def android_controls(owner):
    """Inspect native Android button geometry through rotations before decoding."""
    from java import jclass
    from .rotation_checks import rotate
    native = owner.native.native
    def field(name):
        value = native.getClass().getDeclaredField(name)
        value.setAccessible(True)
        return value.get(native)
    root, controls, scroll = field('root'), field('controls'), field('controlsScroll')
    density = owner.app._impl.native.getResources().getDisplayMetrics().density
    samples = []
    out = Path(owner.app.paths.cache) / 'video-ui'
    out.mkdir(exist_ok=True)
    for orientation in ('portrait', 'landscape-left', 'landscape-right', 'portrait'):
        await rotate(owner.app, orientation)
        await asyncio.sleep(.3)
        def screenshot():
            Bitmap = jclass('android.graphics.Bitmap')
            bitmap = Bitmap.createBitmap(root.getWidth(), root.getHeight(), Bitmap.Config.ARGB_8888)
            root.draw(jclass('android.graphics.Canvas')(bitmap))
            stream = jclass('java.io.ByteArrayOutputStream')()
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)
            (out / (str(len(samples)) + '-' + orientation + '.png')).write_bytes(bytes(stream.toByteArray()))
            bitmap.recycle()
        screenshot()
        pending, rows = [controls], []
        while pending:
            view = pending.pop(0)
            if isinstance(view, jclass('android.widget.Button')):
                label = str(view.getContentDescription())
                assert view.getWidth() / density >= 47.5 and view.getHeight() / density >= 47.5, label
                view.requestRectangleOnScreen(jclass('android.graphics.Rect')(0, 0, view.getWidth(), view.getHeight()), True)
                await asyncio.sleep(.05)
                location = jclass('android.graphics.Rect')()
                assert view.getGlobalVisibleRect(location), (label, 'not visible',
                    'scroll', scroll.getWidth(), scroll.getHeight(), scroll.getScrollY(),
                    'controls', controls.getWidth(), controls.getHeight(),
                    'parent', view.getParent().getLeft(), view.getParent().getTop(),
                    view.getParent().getWidth(), view.getParent().getHeight(),
                    'group', view.getParent().getParent().getWidth(),
                    'params', view.getParent().getLayoutParams().width, view.getParent().getLayoutParams().weight,
                    'button', view.getLeft(), view.getTop(), view.getWidth(), view.getHeight())
                assert location.width() >= view.getWidth() and location.height() >= view.getHeight(), (label, 'clipped')
                rows.append(dict(label=label, width=view.getWidth() / density, height=view.getHeight() / density))
            if hasattr(view, 'getChildCount'):
                pending.extend(view.getChildAt(i) for i in range(view.getChildCount()))
        scroll.scrollTo(0, 0)
        screenshot()
        samples.append(dict(orientation=orientation, width=root.getWidth() / density, buttons=rows))
    (out / 'android-controls.json').write_text(json.dumps(samples, indent=2))
    return samples


async def fullscreen_controls(owner, android):
    """Exercise native controls and observed system chrome, not Python mocks."""
    native = owner.native.native
    awake = screen_awake(owner, android)
    await until(awake)
    from mobile.screen_privacy import native_value
    if android:
        from java import jclass

        def field(name):
            value = native.getClass().getDeclaredField(name)
            value.setAccessible(True)
            return value.get(native)

        controls, root = field('controls'), field('root')
        decor = owner.app._impl.native.getWindow().getDecorView()
        # The surface tap target sits above VLC and below the controls.
        tap = lambda: root.getChildAt(1).performClick()
        toggle = lambda: field('fullscreenButton').performClick()
        visible = lambda: controls.getVisibility() == 0
        Insets = jclass('android.view.WindowInsets')
        modern = jclass('android.os.Build$VERSION').SDK_INT >= 30
        bars = lambda: (int(decor.getRootWindowInsets().isVisible(Insets.Type.statusBars()))
                        | int(decor.getRootWindowInsets().isVisible(Insets.Type.navigationBars())) << 1
                        if modern else int(decor.getSystemUiVisibility()) & 6)
        hidden_bars = lambda: bars() == (0 if modern else 6)
    else:
        visible = lambda: not native_value(native.controls, 'isHidden')
        tap = lambda: native.tapVideo(None)
        toggle = lambda: native.toggleFullscreen(None)
        view = native_value(native, 'view')
        window = native_value(view, 'window')
        scene = native_value(window, 'windowScene')
        status_manager = native_value(scene, 'statusBarManager')
        bars = lambda: bool(native_value(status_manager, 'isStatusBarHidden'))
        hidden_bars = bars
    previous = bars()
    toggle()
    await until(lambda: not visible() and hidden_bars())
    if android:
        assert root.getHeight() == decor.getHeight(), 'Fullscreen root does not fill the window'
        assert field('video').getHeight() == root.getHeight(), 'Controls shrink the video'
    else:
        movie_bounds = native_value(native.movie, 'bounds')
        view_bounds = native_value(view, 'bounds')
        assert abs(movie_bounds.size.height - view_bounds.size.height) < 1
        assert abs(movie_bounds.size.width - view_bounds.size.width) < 1
    tap()
    await until(visible)
    await until(lambda: not visible() and hidden_bars(), timeout=5)
    native.pause()
    await until(lambda: not awake())
    await until(visible)
    await asyncio.sleep(3.2)
    assert visible(), 'Paused controls automatically disappeared'
    toggle()
    await until(lambda: visible() and bars() == previous)
    toggle()
    if android:
        await until(lambda: not visible() and hidden_bars())
    else:
        await until(visible)
    start_playback(owner)
    await until(awake)
    await until(lambda: not visible() and hidden_bars(), timeout=5)
    # Caller closes while immersive, then observes restoration through saved host objects.
    return (dict(tap_reveal=True, auto_hide=True, pause_visible=True, bars_restored=True,
                 playing_keeps_screen_awake=True, pause_releases_screen=True),
            lambda: bars() == previous and not awake())


async def exercise(app):
    rows = []
    report = dict(success=False, cases=rows, scope='focused native video; no receiver or physical lock acceptance')
    try:
        startup = getattr(app, 'startup_task', None)
        if startup is not None:
            await asyncio.shield(startup)
        from commonUtils.runtime.resources.local import LocalFiles
        from features.video.mobile.player import open_video
        root = app.private_root / 'video-fixtures'
        root.mkdir(parents=True, exist_ok=True)
        bundled = Path(__file__).with_name('video-fixtures')
        for source in sorted(bundled.glob('*')):
            (root / source.name).write_bytes(source.read_bytes())
        assert len(list(root.glob('*.mp4'))) == 4
        assert len(list(root.glob('*.mkv'))) == 7
        assert len(list(root.glob('*.avi'))) == 2
        android = type(app._impl).__module__.startswith('toga_android.')
        fullscreen_checked = False
        for path in sorted(root.iterdir()):
            closed_chrome = None
            assert await open_video(app, LocalFiles(root), path.name)
            owner = app.video_player
            if android:
                if not fullscreen_checked:
                    rows.append(dict(name='android-controls', samples=await android_controls(owner)))
                player = android_player(owner)
                start_playback(owner)
                states = []
                def decoded():
                    state = dict(time=int(player.getTime()), length=int(player.getLength()),
                        playing=bool(player.isPlaying()), allowed=owner.allowed(),
                        audio=owner.audio_output.permitted(), protected=owner.restricted)
                    if not states or states[-1] != state:
                        states.append(state)
                        del states[:-20]
                    return state['time'] > 500 and state['length'] > 1000
                try:
                    await until(decoded, timeout=30)
                except AssertionError:
                    report['decoder_startup'] = states
                    raise
                assert player.getAudioTracksCount() >= 1
                colors = await android_frame(owner)
                player.pause()
                player.setTime(1000)
            else:
                player = owner.native.native.player
                start_playback(owner)
                await until(lambda: owner.native.position()[0] > 500)
                assert len(player.audioTracks) >= 1
                from mobile.screen_privacy import native_value
                assert native_value(player, 'hasVideoOut')
                colors = None
                player.pause()
            if not fullscreen_checked:
                # Longer focused fixtures leave time to observe the real timer.
                owner.native.native.pause()
                start_playback(owner)
                await until(lambda: owner.native.position()[0] > 500)
                result, closed_chrome = await fullscreen_controls(owner, android)
                rows.append(dict(name='fullscreen', **result))
                fullscreen_checked = True
            position = owner.native.position()[0]
            assert position >= 0
            # Do not keep an extra bridge reference alive past native teardown:
            # the player's last release must belong to its disposal worker.
            player = None
            awake = screen_awake(owner, android)
            await owner.close()
            await until(lambda: not awake())
            if closed_chrome is not None:
                await until(closed_chrome)
                rows[-1]['close_restored_bars'] = True
            rows.append(dict(name=path.name, played=True, rendered_colors=colors, position=position))
            print('VIDEO_PROBE_CASE=' + path.name, flush=True)
        # Reuse the shipped synthetic crypt fixture; never touch user remotes.
        fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
        app.show_cloud(present=False)
        if getattr(app, 'cloud_restore_task', None):
            await app.cloud_restore_task
        app.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password',
                                 package_name='VideoFixture.zip', session_only=True)
        from features.rclone.localcrypt.mobile.resources import encrypted_storage
        provider = encrypted_storage(app.private_root / 'video-crypt', app.cloud_client, 'Secret')
        provider.create_file('private.mkv', BytesIO((root / 'h264-aac.mkv').read_bytes()))
        assert await open_video(app, provider, 'private.mkv')
        owner = app.video_player
        assert owner.content.restricted
        assert not owner.allowed(external=True)
        if android:
            player = android_player(owner)
            start_playback(owner)
        else:
            player = owner.native.native.player
            start_playback(owner)
        await until(lambda: owner.native.position()[0] > 500)
        await asyncio.to_thread(owner.progress.save, 1234)
        assert await asyncio.to_thread(owner.progress.load) == 1234
        app.screen_privacy.conceal()
        assert owner.hidden and not owner.allowed()
        app.screen_privacy.reveal()
        assert owner.hidden
        app.screen_privacy.lock_password.value = 'synthetic-session-password'
        await app.screen_privacy.unlock()
        assert not owner.hidden
        if android:
            assert not player.isPlaying()
        else:
            from mobile.screen_privacy import native_value
            assert not native_value(player, 'isPlaying')
        player = None
        await owner.close()
        rows.append(dict(name='LocalCrypt', encrypted_resume=True, password_resume=True, external_denied=True))
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        traceback.print_exc()
    finally:
        owner = getattr(app, 'video_player', None)
        if owner is not None:
            await owner.close()
        result = Path(app.paths.cache) / 'video-probe-result.json'
        result.write_text(json.dumps(report, indent=2))
        print('VIDEO_PROBE_RESULT=' + json.dumps(report), flush=True)


class VideoProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'video-probe-private'
        super().startup()

    def on_running(self):
        if getattr(self, '_video_probe_task', None) is None:
            self._video_probe_task = self.loop.create_task(exercise(self))


def main():
    return VideoProbe('Logistics Video QA', 'io.github.ispaure.logisticsmobile')
