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


def start_playback(owner):
    """Exercise the same explicit Play admission as the native controls."""
    if type(owner.app._impl).__module__.startswith('toga_android.'):
        native = owner.native.native
        field = native.getClass().getDeclaredField('play')
        field.setAccessible(True)
        field.get(native).performClick()
    else:
        owner.native.native.togglePlay(None)


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


async def fullscreen_controls(owner, android):
    """Exercise native controls and observed system chrome, not Python mocks."""
    native = owner.native.native
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
        status_manager = native.view.window.windowScene.statusBarManager
        bars = lambda: bool(native_value(status_manager, 'isStatusBarHidden'))
        hidden_bars = bars
    previous = bars()
    toggle()
    await until(lambda: not visible() and hidden_bars())
    if android:
        assert root.getHeight() == decor.getHeight(), 'Fullscreen root does not fill the window'
        assert field('video').getHeight() == root.getHeight(), 'Controls shrink the video'
    else:
        assert abs(native.movie.bounds.size.height - native.view.bounds.size.height) < 1
        assert abs(native.movie.bounds.size.width - native.view.bounds.size.width) < 1
    tap()
    await until(visible)
    await until(lambda: not visible() and hidden_bars(), timeout=5)
    native.pause()
    await until(visible)
    await asyncio.sleep(3.2)
    assert visible(), 'Paused controls automatically disappeared'
    toggle()
    await until(lambda: visible() and bars() == previous)
    toggle()
    await until(lambda: not visible() and hidden_bars())
    # Caller closes while immersive, then observes restoration through saved host objects.
    return (dict(tap_reveal=True, auto_hide=True, pause_visible=True, bars_restored=True),
            lambda: bars() == previous)


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
        assert len(list(root.glob('*.mkv'))) == 4
        android = type(app._impl).__module__.startswith('toga_android.')
        fullscreen_checked = False
        for path in sorted(root.iterdir()):
            closed_chrome = None
            assert await open_video(app, LocalFiles(root), path.name)
            owner = app.video_player
            if android:
                player = android_player(owner)
                start_playback(owner)
                await until(lambda: player.getTime() > 500 and player.getLength() > 1000)
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
            await owner.close()
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
