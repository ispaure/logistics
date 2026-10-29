"""Real native rclone/WebDAV/crypt video acceptance on disposable devices."""
import asyncio
import base64
from io import BytesIO
import json
from pathlib import Path
import traceback
from zipfile import ZipFile

from mobile.app import LogisticsMobile
from .video_probe import until, android_frame, android_player, start_playback
from .video_webdav import VideoWebDAV

PASSWORD = 'synthetic-session-password'


async def exercise(app):
    rows = []
    report = dict(success=False, cases=rows,
        scope='Native decoder and real rclone WebDAV/crypt ranges on synthetic loopback fixtures; no live account, receiver or physical lock acceptance')
    server = None
    try:
        startup = getattr(app, 'startup_task', None)
        if startup is not None:
            await asyncio.shield(startup)
        server = VideoWebDAV(Path(__file__).with_name('video-cloud-fixtures'))
        app.show_cloud(present=False)
        if getattr(app, 'cloud_restore_task', None):
            await app.cloud_restore_task
        package = BytesIO()
        with ZipFile(package, 'w') as archive:
            archive.writestr('Cloud.txt', f'[Cloud]\ntype=webdav\nurl={server.url}\nvendor=other\n')
            archive.writestr('Secret.txt', '[Secret]\ntype=crypt\nremote=Cloud:encrypted\n'
                'password=E7Tt68UUDf297fEq6fQq6vjnnyj003Lrpf5FuniO2qlBJqGXXm5tIg\n')
        names = await asyncio.to_thread(app.cloud_client.request, 'import',
            package=base64.b64encode(package.getvalue()).decode(), password=PASSWORD,
            package_name='CloudVideoFixture.zip', session_only=True)
        app.set_loaded_remote_names(names)
        import os
        report['ssl_cert_file'] = os.environ.get('SSL_CERT_FILE', '')
        report['ssl_cert_readable'] = bool(report['ssl_cert_file'] and Path(report['ssl_cert_file']).is_file())
        report['remote_listing_count'] = len(await asyncio.to_thread(app.cloud_client.entries, 'Cloud', 'plain'))
        app.cloud_crypt_remotes = set(await asyncio.to_thread(app.cloud_client.crypt_remotes))
        from features.rclone.mobile.service import native_service
        from features.rclone.remote_access import NativeRemoteLocation
        from services.documents.mobile_storage import open_provider_document
        from features.video.playback import SubtitleContent
        android = type(app._impl).__module__.startswith('toga_android.')
        report['platform'] = 'android' if android else 'ios'

        async def open_movie(remote, path):
            resource = await asyncio.to_thread(native_service(app.cloud_client).remotes.open, NativeRemoteLocation(remote))
            try:
                assert await open_provider_document(app, resource, path)
            finally:
                resource.close()
            owner = app.video_player
            assert owner.content.remote and owner.content.restricted
            assert not owner.allowed(external=True)
            return owner

        async def play(owner, seek=None):
            player = android_player(owner) if android else owner.native.native.player
            if seek is not None:
                if android:
                    player.setTime(seek)
                else:
                    duration = 12000 if owner.content.path.endswith('long.mp4') else 6000
                    owner.native.native.seek.value = seek / duration
                    owner.native.native.seekChanged(owner.native.native.seek)
            start_playback(owner)
            try:
                await until(lambda: owner.native.position()[0] > (seek + 200 if seek is not None else 500), timeout=30)
            except AssertionError:
                if not android:
                    from mobile.screen_privacy import native_value
                    controller = owner.native.native
                    report['ios_playback_state'] = dict(playing=bool(native_value(player, 'isPlaying')),
                        state=str(native_value(player, 'state')), can_play=bool(controller.canPlay(False)),
                        pending_resume=int(controller.startMilliseconds), status=str(controller.message.text),
                        native_position=float(player.position), target=seek)
                raise
            if android:
                assert player.getAudioTracksCount() >= 1
                colors = await android_frame(owner)
            else:
                from mobile.screen_privacy import native_value
                assert len(player.audioTracks) >= 1
                assert native_value(player, 'hasVideoOut')
                frames = Path(app.paths.cache) / 'video-cloud-frames'
                frames.mkdir(exist_ok=True)
                frame = frames / (owner.content.path.replace('/', '_') + f'-{seek or 0}.png')
                player.saveVideoSnapshotAt(str(frame), withWidth=128, andHeight=72)
                await until(lambda: frame.is_file() and frame.stat().st_size > 0)
                colors = None
            player.pause()
            from mobile.screen_privacy import native_value
            await until(lambda: not (player.isPlaying() if android else native_value(player, 'isPlaying')))
            return player, colors

        fixtures = sorted(Path(__file__).with_name('video-cloud-fixtures').joinpath('remote/plain').glob('*'))
        for remote, folder in [('Cloud', 'plain/'), ('Secret', '')]:
            for path in fixtures:
                if path.suffix not in {'.mp4', '.mkv', '.avi'} or path.name == 'long.mp4':
                    continue
                owner = await open_movie(remote, folder + path.name)
                player, colors = await play(owner)
                before = owner.native.position()[0]
                await play(owner, seek=1000)
                await asyncio.to_thread(owner.progress.save, 1234)
                assert await asyncio.to_thread(owner.progress.load) == 1234
                assert owner.progress.remote
                if path.stem == 'h264-aac':
                    assert owner.subtitles, 'Matching remote subtitles were not admitted'
                    subtitle = SubtitleContent(owner.content.provider, folder + 'h264-aac.srt')
                    try:
                        def read():
                            with subtitle.open() as stream:
                                return stream.read(4096)
                        assert b'Cloud fixture caption' in await asyncio.to_thread(read)
                    finally:
                        subtitle.close()
                await owner.close()
                rows.append(dict(remote=remote, name=path.name, played=True, seek=True,
                    audio_tracks=True, rendered_colors=colors, memory_resume=True, external_denied=True,
                    initial_position=before))
                print('CLOUD_VIDEO_CASE=' + remote + ':' + path.name, flush=True)

            owner = await open_movie(remote, folder + 'long.mp4')
            await play(owner)
            player, _ = await play(owner, seek=8000)
            app.screen_privacy.conceal()
            assert owner.hidden and not owner.allowed()
            app.screen_privacy.reveal()
            assert owner.hidden
            app.screen_privacy.lock_password.value = PASSWORD
            await app.screen_privacy.unlock()
            assert not owner.hidden
            if android:
                assert not player.isPlaying()
            else:
                from mobile.screen_privacy import native_value
                assert not native_value(player, 'isPlaying')
            await owner.close()
            rows.append(dict(remote=remote, name='long.mp4', seek_8_seconds=True,
                password_resume=True, unlock_does_not_autoplay=True))

        # Use the real Cloud-browser dispatch path, not only provider entry.
        app.show_cloud()
        app.cloud_remote.value = 'Secret'
        app.cloud_location.value = ''
        assert await app.browse_cloud(preserve_path=True), app.cloud_status.value
        browser = app.remote_browser
        entry = next(entry for entry in browser.entries if entry.payload['path'] == 'long.mp4')
        await browser.activate_entry(entry)
        owner = app.video_player
        assert owner is not None and owner.content.remote
        await play(owner)
        app.cloud_client.lock()
        owner.retire_stale()
        assert owner.closed and not owner.allowed()
        await asyncio.shield(owner.retirement)
        assert app.video_player is None
        rows.append(dict(name='Cloud browser activation and credential revocation', retired=True))
        assert not list(app.private_root.rglob('*.mp4'))
        assert not list(app.private_root.rglob('*.mkv'))
        assert not list(app.private_root.rglob('*.avi'))
        assert server.metrics['ranges'] > 0 and server.metrics['encrypted_ranges'] > 0
        report['network'] = server.metrics
        report['no_plaintext_video_staging'] = True
        report['success'] = True
    except Exception:
        owner = getattr(app, 'video_player', None)
        if owner is not None and owner.native is not None:
            report['player_diagnostics'] = dict(position=owner.native.position(), allowed=owner.allowed(),
                hidden=owner.hidden, host_active=app.active_host, path=owner.content.path)
        report['error'] = traceback.format_exc()
        traceback.print_exc()
    finally:
        owner = getattr(app, 'video_player', None)
        if owner is not None:
            await owner.close()
        if server is not None:
            report['network'] = dict(server.metrics)
            await asyncio.to_thread(server.close)
        result = Path(app.paths.cache) / 'video-probe-result.json'
        result.write_text(json.dumps(report, indent=2))
        print('CLOUD_VIDEO_RESULT=' + json.dumps(report), flush=True)


class CloudVideoProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'cloud-video-probe-private'
        super().startup()

    def on_running(self):
        if getattr(self, '_cloud_video_probe_task', None) is None:
            self._cloud_video_probe_task = self.loop.create_task(exercise(self))


def main():
    return CloudVideoProbe('Logistics Cloud Video QA', 'io.github.ispaure.logisticsmobile')
