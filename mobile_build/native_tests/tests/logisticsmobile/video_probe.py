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
        for path in sorted(root.iterdir()):
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
            position = owner.native.position()[0]
            assert position >= 0
            await owner.close()
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
