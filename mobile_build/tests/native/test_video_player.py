"""Mobile playback admission, privacy lifetime and generated project wiring."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
import xml.etree.ElementTree as ET

from mobile_build.build_support.video_build import configure_android, configure_ios


class VideoMobileLifetimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_favourite_uses_host_capability_and_reports_errors(self):
        owner = self.player(restricted=False)
        favourite = AsyncMock()
        owner.app.presentation = SimpleNamespace(favourite_resource=favourite)
        await owner.controls.command('favourite', '')
        favourite.assert_awaited_once_with(owner.content.provider, owner.content.path, kind='video')
        owner.native.status.assert_called_with('Added to favourites')
        favourite.side_effect = ValueError('Storage unavailable')
        await owner.controls.command('favourite', '')
        owner.native.status.assert_called_with('Storage unavailable')
        self.assertFalse(owner.closed)

    async def test_airplay_hands_off_without_reopening_the_logistics_player(self):
        owner = self.player(restricted=False)
        native = owner.native
        native.airplay_active.return_value = False
        owner.content.check = Mock()
        path = Path('/unused/movie.mkv')
        stream = Mock()
        with patch('features.video.mobile.ios.airplay_file', return_value=path), patch(
                'features.video.mobile.mkv.MKVStream', return_value=stream):
            await owner.prepare_airplay()
        self.assertIs(owner.native, native)
        native.start_airplay.assert_called_once_with(path, stream)
        native.dispose.assert_not_called()
        self.assertIs(owner.mkv_stream, stream)
        await owner.controls.command('airplayDetached', '')
        stream.close.assert_called_once_with()
        self.assertIsNone(owner.mkv_stream)

    async def test_airplay_admission_failure_keeps_local_playback(self):
        owner = self.player(restricted=False)
        owner.native.airplay_active.return_value = False
        path = Path('/unused/movie.mkv')
        with patch('features.video.mobile.ios.airplay_file', return_value=path), patch(
                'features.video.mobile.mkv.MKVStream', side_effect=ValueError('MKV unavailable')):
            await owner.prepare_airplay()
        owner.native.airplay_preparation_failed.assert_called_with('MKV unavailable')
        owner.native.start_airplay.assert_not_called()
        owner.native.pause.assert_not_called()
        self.assertFalse(owner.switching_player)

    def player(self, *, restricted=True):
        from features.video.mobile.player import MobileVideo
        app = SimpleNamespace(audio_output=Mock(), active_host=True, private_root=Path('/unused'), loop=asyncio.get_running_loop())
        from mobile.protection import for_app
        app.protection = for_app(app)
        content = SimpleNamespace(provider=SimpleNamespace(storage_id='test', private=False),
            source=SimpleNamespace(expected=(1,), check_access=Mock()), path='movie.mkv',
            restricted=restricted, check_access=Mock(), require_external=Mock(), close=Mock())
        with patch('features.video.mobile.player.VideoTransport'):
            owner = MobileVideo(app, content)
        owner.protection.register(app, lambda: getattr(getattr(app, 'screen_privacy', None), 'gates', lambda: ())())
        self.addCleanup(owner.protection.dispose)
        self.addAsyncCleanup(owner.close)
        owner.native = Mock()
        disposal = app.loop.create_future()
        disposal.set_result(None)
        owner.native.dispose.return_value = disposal
        owner.native.position.return_value = (12000, False)
        owner.progress = Mock()
        app.video_player = owner
        return owner

    async def test_newest_speed_selection_wins_slow_preference_write(self):
        import json
        from threading import Event
        from features.video.session import PlaybackSettings
        owner = self.player(restricted=False)
        entered, release = Event(), Event()
        persisted = []
        def flush(rate):
            if rate == 2.:
                entered.set()
                if not release.wait(2):
                    raise TimeoutError('Controlled preference write timed out')
            if rate is not None:
                persisted.append(rate)
        owner.controls.store.observe = Mock(side_effect=lambda values, **kwargs: (PlaybackSettings.from_dict(values), values['rate']))
        owner.progress.flush.side_effect = flush
        first = asyncio.create_task(owner.controls.command('settings', '{"rate": 2.0}'))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            newest = asyncio.create_task(owner.controls.command('settings', '{"rate": 0.5}'))
            await asyncio.sleep(0)
            release.set()
            await asyncio.wait_for(asyncio.gather(first, newest), 2)
        finally:
            release.set()
        self.assertEqual(persisted, [2., .5])
        self.assertEqual(owner.controls.settings.rate, .5)
        owner.native.configure.assert_called_once()
        self.assertEqual(json.loads(owner.native.configure.call_args.args[0])['rate'], .5)

    async def test_subtitle_attachment_rechecks_presentation_after_saving(self):
        from threading import Event
        from features.video.session import PlaybackSettings
        for transition in ('close', 'hide', 'revoke'):
            with self.subTest(transition=transition):
                owner = self.player(restricted=False)
                native = owner.native
                subtitle = Mock(path='movie.en.srt', size=100)
                entered, release = Event(), Event()

                def flush(token):
                    if token is not None:
                        entered.set()
                        if not release.wait(2):
                            raise TimeoutError('Controlled subtitle write timed out')

                owner.controls.store.observe = Mock(side_effect=lambda values, **kwargs: (PlaybackSettings.from_dict(values), object()))
                owner.progress.flush.side_effect = flush
                retirement = None
                with patch('features.video.mobile.controls.SubtitleContent', return_value=subtitle):
                    owner.controls.dispatch('subtitleAttach', subtitle.path)
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                        if transition == 'close':
                            retirement = owner.retire()
                            native.dispose.assert_called_once()
                        elif transition == 'hide':
                            owner.hidden = True
                        else:
                            owner.content.check_access.side_effect = PermissionError('Revoked')
                        owner.content.close.assert_not_called()
                    finally:
                        release.set()
                        await asyncio.wait_for(owner.controls.finish(), 2)
                        if retirement is not None:
                            await asyncio.wait_for(asyncio.shield(retirement), 2)
                native.configure.assert_not_called()
                native.add_subtitle.assert_not_called()
                owner.transport.add_subtitle.assert_called_once_with(subtitle)
                subtitle.close.assert_called_once()
                self.assertEqual(owner.subtitles, [])
                await owner.close()

    async def test_subtitle_attachment_persists_selection_and_retains_until_close(self):
        from features.video.session import PlaybackSettings
        owner = self.player(restricted=False)
        native = owner.native
        subtitle = Mock(path='movie.en.srt', size=100)
        owner.controls.store.observe = Mock(side_effect=lambda values, **kwargs: (PlaybackSettings.from_dict(values), None))
        owner.transport.add_subtitle.return_value = 'http://127.0.0.1/subtitle'
        with patch('features.video.mobile.controls.SubtitleContent', return_value=subtitle):
            await owner.controls.command('subtitleAttach', subtitle.path)
        self.assertEqual(owner.controls.settings.subtitle_file, subtitle.path)
        self.assertIsNone(owner.controls.settings.subtitle_track)
        native.configure.assert_called_once()
        native.add_subtitle.assert_called_once_with('http://127.0.0.1/subtitle')
        native.play.assert_not_called()
        subtitle.close.assert_not_called()
        self.assertEqual(owner.subtitles, [subtitle])
        await owner.close()
        subtitle.close.assert_called_once()

    async def test_discovered_sidecar_selection_configures_then_attaches(self):
        from features.video.session import PlaybackSettings
        owner = self.player(restricted=False)
        subtitle = Mock(path='Subtitles/movie.fr.srt')
        owner.subtitles = [subtitle]
        owner.transport.add_subtitle.return_value = 'http://127.0.0.1/subtitle.srt'
        owner.controls.settings = PlaybackSettings(subtitle_track=0)
        owner.controls.store.observe = Mock(
            side_effect=lambda values, **kwargs: (PlaybackSettings.from_dict(values), None))
        calls = []
        owner.native.configure.side_effect = lambda *args: calls.append('configure')
        owner.native.add_subtitle.side_effect = lambda *args: calls.append('attach')
        await owner.controls.command('subtitleSelect', 'movie.fr.srt')
        self.assertEqual(calls, ['configure', 'attach'])
        owner.transport.add_subtitle.assert_called_once_with(subtitle)
        owner.native.add_subtitle.assert_called_once_with('http://127.0.0.1/subtitle.srt')
        self.assertIsNone(owner.controls.settings.subtitle_track)
        self.assertEqual(owner.controls.settings.subtitle_file, subtitle.path)

    async def test_failed_subtitle_preference_write_releases_unpublished_resource(self):
        owner = self.player(restricted=False)
        subtitle = Mock(path='movie.en.srt', size=100)
        owner.controls.store.observe = Mock(side_effect=OSError('Cannot save settings'))
        with patch('features.video.mobile.controls.SubtitleContent', return_value=subtitle):
            await owner.controls.command('subtitleAttach', subtitle.path)
        owner.native.status.assert_called_with('Cannot save settings')
        owner.native.configure.assert_not_called()
        owner.native.add_subtitle.assert_not_called()
        owner.transport.add_subtitle.assert_called_once_with(subtitle)
        subtitle.close.assert_called_once()
        self.assertEqual(owner.subtitles, [])

    async def test_invalid_subtitle_transport_is_rejected_before_saving_selection(self):
        owner = self.player(restricted=False)
        subtitle = Mock(path='movie.en.srt', size=100)
        owner.controls.store.observe = Mock()
        owner.transport.add_subtitle.side_effect = ValueError('Subtitle changed')
        with patch('features.video.mobile.controls.SubtitleContent', return_value=subtitle):
            await owner.controls.command('subtitleAttach', subtitle.path)
        owner.transport.add_subtitle.assert_called_once_with(subtitle)
        owner.controls.store.observe.assert_not_called()
        owner.native.add_subtitle.assert_not_called()
        owner.native.status.assert_called_with('Subtitle changed')
        subtitle.close.assert_called_once()

    async def test_show_in_folder_keeps_source_alive_until_browser_has_adopted_it(self):
        from features.video.mobile.controls import native_options
        owner = self.player(restricted=False)
        owner.content.path = 'Season 1/Episode 1.mkv'
        owner.content.remote = False
        import json
        options = json.loads(native_options('{}', owner.content))
        self.assertEqual(options['video_title'], 'Episode 1.mkv')
        self.assertEqual(options['video_path'], 'Season 1/Episode 1.mkv')
        self.assertEqual(options['source_label'], 'Local file')
        async def reveal(app, location):
            self.assertIs(app, owner.app)
            self.assertEqual(location, dict(provider=owner.content.provider, key=owner.content.path))
            owner.native.pause.assert_called_once()
            owner.native.hide.assert_called_once()
            owner.content.close.assert_not_called()
            return True
        with patch('mobile.document_sources.show_folder_location', side_effect=reveal), patch(
                'services.documents.mobile_storage.document_source', return_value=(SimpleNamespace(remote=False), owner.content.path)), patch(
                'services.documents.mobile_reading.reading_capabilities', return_value=SimpleNamespace(remote=False)):
            # Exercise dispatch too: retirement must not wait on its own command.
            owner.controls.dispatch('showInFolder')
            await asyncio.sleep(0)
            jobs = list(owner.controls.jobs)
            await asyncio.wait_for(asyncio.gather(*jobs), 1)
        self.assertTrue(owner.closed)
        owner.content.close.assert_called_once()

    async def test_cloud_folder_failure_still_retires_video(self):
        owner = self.player()
        with patch('mobile.document_sources.show_folder_location', AsyncMock(side_effect=OSError('Unavailable'))) as reveal, patch(
                'services.documents.mobile_storage.document_source', return_value=(SimpleNamespace(remote='drive:'), 'Season/movie.mkv')), patch(
                'services.documents.mobile_reading.reading_capabilities', return_value=SimpleNamespace(remote=True)):
            await owner.controls.command('showInFolder', '')
        reveal.assert_awaited_once_with(owner.app, dict(remote='drive:', key='Season/movie.mkv'))
        self.assertTrue(owner.closed)
        owner.content.close.assert_called_once()

    async def test_title_badge_follows_source_storage_not_process_privacy(self):
        from features.video.mobile.controls import native_options
        import json
        owner = self.player(restricted=True)
        for remote, private, label in ((False, False, 'Local file'), (False, True, 'Local encrypted file'),
                                       (True, False, 'Cloud file'), (True, True, 'Cloud file')):
            owner.content.remote = remote
            owner.content.provider.private = private
            options = json.loads(native_options('{}', owner.content))
            self.assertEqual(options['source_label'], label)
            self.assertEqual(options['source_remote'], remote)

    async def test_session_lock_hides_surface_and_unlock_restores_without_autoplay(self):
        owner = self.player()
        owner.conceal()
        self.assertTrue(owner.hidden)
        owner.native.pause_for_background.assert_called_once()
        owner.native.hide.assert_called_once()
        owner.transport.suspend.assert_called_once()
        owner.content.check_access.side_effect = PermissionError('locked')
        owner.reveal()
        owner.native.show.assert_not_called()
        owner.content.check_access.side_effect = None
        owner.reveal()
        owner.native.show.assert_called_once()
        owner.native.play.assert_not_called()
        await asyncio.sleep(.02)
        await owner.close()
        owner.content.close.assert_called_once()

    async def test_stream_failure_uses_safe_category_and_does_not_pause_playable_data(self):
        owner = self.player()
        owner.stream_failed('read')
        owner.native.transport_failed.assert_called_once_with(
            'Video data could not be read. Check the connection, then press Play to retry.')
        owner.native.pause.assert_not_called()
        owner.hidden = True
        owner.stream_failed('access')
        self.assertEqual(owner.native.transport_failed.call_count, 1)

    async def test_data_ready_while_hidden_clears_native_wait_before_reveal(self):
        owner = self.player()
        token = object()
        owner.network_waiting(token, True)
        owner.conceal()
        owner.network_waiting(token, False)
        self.assertEqual(owner.native.network_waiting.call_count, 1)
        owner.reveal()
        owner.native.network_waiting.assert_called_with(False)
        owner.native.play.assert_not_called()
        await asyncio.sleep(.02)

    async def test_overlapping_network_reads_hold_until_all_are_ready(self):
        owner = self.player()
        first, second = object(), object()
        owner.network_waiting(first, True)
        owner.network_waiting(second, True)
        owner.network_waiting(first, False)
        owner.network_waiting(second, False)
        self.assertEqual([call.args[0] for call in owner.native.network_waiting.call_args_list],
                         [True, True, True, False])
        owner.closed = True
        owner.network_waiting(first, True)
        self.assertEqual(owner.native.network_waiting.call_count, 4)
        owner.closed = False

    async def test_native_controls_deny_pending_resume_even_if_own_gate_is_unlocked(self):
        owner = self.player()
        privacy = SimpleNamespace(inactive=True, saved_content=None, gates=lambda: ())
        owner.app.screen_privacy = privacy
        self.assertFalse(owner.allowed())
        owner.transport.resume.assert_not_called()
        privacy.inactive = False
        privacy.saved_content = object()  # A presentation widget is not authorization state.
        self.assertTrue(owner.allowed())
        owner.transport.resume.assert_not_called()
        privacy.saved_content = None
        privacy.gates = lambda: (SimpleNamespace(locked=True),)
        self.assertFalse(owner.allowed())
        privacy.gates = lambda: ()
        self.assertTrue(owner.allowed())
        self.assertEqual(owner.content.check_access.call_count, 2)
        owner.retire()

    async def test_new_session_retires_an_existing_unrestricted_native_surface(self):
        owner = self.player(restricted=False)
        owner.native_restricted = False
        owner.app.screen_privacy = SimpleNamespace(gates=lambda: (SimpleNamespace(locked=False),))
        self.assertFalse(owner.allowed(external=True))
        native = owner.native
        owner.retire_stale()
        native.dispose.assert_called_once()
        self.assertTrue(owner.closed)

    async def test_plain_video_conceals_when_another_session_protects_the_app(self):
        owner = self.player(restricted=False)
        owner.app.screen_privacy = SimpleNamespace(gates=lambda: (SimpleNamespace(locked=False),))
        owner.conceal()
        self.assertTrue(owner.hidden)
        owner.native.hide.assert_called_once()
        owner.retire()
        await asyncio.sleep(.01)

    async def test_leaving_protection_retires_an_ordinary_players_fixed_native_policy(self):
        owner = self.player(restricted=False)
        owner.native_restricted = True
        native = owner.native
        owner.retire_changed_policy()
        native.dispose.assert_called_once()
        self.assertTrue(owner.closed)
        await owner.close()
        self.assertIsNone(owner.app.video_player)

    async def test_retained_session_content_keeps_its_native_policy_without_credentials(self):
        owner = self.player(restricted=True)
        owner.native_restricted = True
        self.assertTrue(owner.protection.process.protected())
        owner.retire_changed_policy()
        owner.native.dispose.assert_not_called()
        self.assertFalse(owner.closed)

    async def test_ordinary_background_policy_delegates_pip_but_does_not_hide(self):
        owner = self.player(restricted=False)
        owner.conceal()
        owner.native.pause_for_background.assert_called_once()
        owner.native.hide.assert_not_called()
        self.assertFalse(owner.hidden)
        await asyncio.sleep(.02)
        await owner.close()

    async def test_revocation_retires_native_decoder_and_transport(self):
        owner = self.player()
        native = owner.native
        owner.content.source.check_access.side_effect = ValueError('revoked')
        owner.retire_stale()
        native.dispose.assert_called_once()
        await owner.close()
        owner.transport.close.assert_called_once()
        self.assertIsNone(owner.app.video_player)
        self.assertFalse(owner.allowed())

    async def test_failed_checkpoint_does_not_open_or_read_video(self):
        from features.video.mobile.player import open_video
        app = SimpleNamespace(require_feature=lambda name: True, checkpoint=lambda: False)
        with patch('features.video.mobile.player.VideoContent') as content:
            self.assertFalse(await open_video(app, Mock(), 'movie.mp4'))
            content.assert_not_called()

    async def test_failed_player_construction_releases_acquired_resources(self):
        from features.video.mobile.player import open_video
        for failure in ('progress', 'controls', 'protection'):
            with self.subTest(failure=failure):
                app = SimpleNamespace(require_feature=lambda name: True, checkpoint=lambda: True,
                    loop=asyncio.get_running_loop(), private_root=Path('/unused'),
                    audio_output=Mock(), protection=Mock())
                content = Mock()
                with patch('features.video.mobile.player.VideoContent', return_value=content), patch(
                        'features.video.mobile.player.VideoTransport') as transport, patch(
                        'features.video.mobile.player.VideoProgress') as progress, patch(
                        'features.video.mobile.controls.PlaybackControls') as controls:
                    failing = dict(progress=progress, controls=controls,
                                   protection=app.protection.register)[failure]
                    failing.side_effect = RuntimeError('Controlled construction failure')
                    with self.assertRaisesRegex(RuntimeError, 'Controlled construction failure'):
                        await open_video(app, Mock(), 'movie.mp4')
                    transport.return_value.close.assert_called_once()
                    content.close.assert_called_once()
                    self.assertFalse(hasattr(app, 'video_player'))
                    if failure == 'protection':
                        app.audio_output.unregister.assert_called_once_with(
                            app.audio_output.register.call_args.args[0])
                    else:
                        app.audio_output.register.assert_not_called()

    async def test_failed_native_retirement_keeps_protection_until_disposal_succeeds(self):
        owner = self.player()
        owner.native.dispose.side_effect = RuntimeError('native disposal failed')
        with self.assertRaisesRegex(RuntimeError, 'native disposal failed'):
            owner.retire()
        self.assertTrue(owner.closed)
        self.assertTrue(owner.protection.process.protected())
        owner.content.close.assert_not_called()
        owner.native.dispose.side_effect = None
        owner.retire()
        await owner.close()
        self.assertFalse(owner.protection.process.protected())

    async def test_pending_native_teardown_keeps_source_protected_after_window_disposal(self):
        owner = self.player()
        barrier = owner.app.loop.create_future()
        owner.native.dispose.return_value = barrier
        owner.retire()
        owner.protection.dispose()
        self.assertTrue(owner.closed)
        self.assertFalse(owner.allowed())
        self.assertTrue(owner.protection.process.protected())
        owner.content.close.assert_not_called()
        owner.transport.close.assert_not_called()
        close = asyncio.create_task(owner.close())
        await asyncio.sleep(0)
        self.assertFalse(close.done())
        close.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await close
        self.assertFalse(barrier.cancelled())
        barrier.set_result(None)
        await owner.close()
        owner.content.close.assert_called_once()
        self.assertFalse(owner.protection.process.protected())

    async def test_close_retains_source_until_remote_discovery_finishes(self):
        owner = self.player()
        barrier = asyncio.Event()
        owner.discovery = asyncio.create_task(barrier.wait())
        close = asyncio.create_task(owner.close())
        try:
            await asyncio.sleep(.02)
            owner.native.dispose.assert_called_once()
            owner.content.close.assert_not_called()
            self.assertFalse(close.done())
        finally:
            barrier.set()
            await close
        owner.content.close.assert_called_once()

    async def test_checkpoint_finishes_before_protected_source_disposal(self):
        owner = self.player()
        def assert_flushed():
            owner.progress.flush.assert_called_once_with(None)
            owner.progress.retire.assert_called_once()
        native = owner.native
        owner.content.close.side_effect = assert_flushed
        await owner.close()
        native.position.assert_not_called()
        native.progress_position.assert_not_called()


    async def test_confirmed_native_seek_is_published_before_close_without_resampling(self):
        owner = self.player()
        native = owner.native
        observation = object()
        owner.progress.observe.return_value = observation
        await owner.controls.command('progress', '15000')
        owner.progress.observe.assert_called_once_with(15000, completed=False)
        owner.progress.flush.assert_called_once_with(observation)
        await owner.close()
        native.position.assert_not_called()
        native.progress_position.assert_not_called()
        self.assertEqual(owner.progress.flush.call_args.args, (None,))


    async def test_locked_video_history_status_reaches_native_surface(self):
        owner = self.player()
        owner.progress.flush.return_value = 'locked'
        owner.progress.resume_notice = 'Previous ZIP password needed.'
        await owner.flush_progress(object())
        owner.native.status.assert_called_once_with(owner.progress.resume_notice)


    async def test_protected_controls_save_through_mobile_credential_cipher(self):
        import base64
        import json
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from os import urandom
        from features.video.mobile.controls import PlaybackControls
        from services.documents.video_progress import VideoProgress

        class Client:
            generation = 1
            identity = 'a' * 64
            package_records = (dict(saved=False, document_cache_id='fixture',
                                    crypt_identities={'Secret': identity}),)

            def connection_identity(self, remote):
                return 'b' * 64

            def request(self, action, **values):
                assert values['id'] == 'fixture'
                cipher = AESGCM(b'p' * 32)
                data = base64.b64decode(values['data'])
                if action == 'document_lists_seal':
                    nonce = urandom(12)
                    result = nonce + cipher.encrypt(nonce, data, None)
                elif action == 'document_lists_open':
                    result = cipher.decrypt(data[:12], data[12:], None)
                else:
                    raise AssertionError(action)
                return base64.b64encode(result).decode()

        owner = self.player()
        root = Path(self.enterContext(TemporaryDirectory()))
        owner.app.private_root = root
        owner.app.cloud_client = client = Client()
        owner.content.provider = SimpleNamespace(private=True, client=client, remote='Secret',
                                                  identity=client.identity, storage_id='fixture',
                                                  storage_namespace='localcrypt', relative=lambda path: path,
                                                  entry=Mock(side_effect=FileNotFoundError))
        owner.content.path = 'Hidden-film.mkv'
        owner.content.check = Mock()
        owner.progress = VideoProgress(owner.content, root / 'Video', app=owner.app)
        self.assertEqual(owner.progress.load(), 0)
        self.assertEqual(owner.progress.state.mode, 'encrypted')
        owner.controls = PlaybackControls(owner)
        values = dict(audio_track=1, audio_track_key='voice-choice', subtitle_track=-1,
                      subtitle_delay_ms=350, subtitle_scale=1.25)
        await owner.controls.command('settings', json.dumps(values))
        self.assertEqual(owner.progress.state.write_status, 'saved')
        self.assertFalse((root / 'ReaderPositions/Local').exists())
        encrypted, = (root / 'ReaderPositions').glob('*.zip')
        for private_value in (b'Hidden-film', b'voice-choice', b'subtitle_delay_ms'):
            self.assertNotIn(private_value, encrypted.read_bytes())
        reopened = VideoProgress(owner.content, root / 'Video', app=owner.app)
        reopened.load()
        for key, value in values.items():
            self.assertEqual(getattr(reopened.settings, key), value)


class VideoBuildTests(unittest.TestCase):
    def test_android_pip_refresh_is_idempotent_and_preserves_other_network_policy(self):
        with TemporaryDirectory() as directory:
            project = Path(directory)
            manifest = project / 'app/src/main/AndroidManifest.xml'
            manifest.parent.mkdir(parents=True)
            manifest.write_text('''<manifest xmlns:android="http://schemas.android.com/apk/res/android">
<application android:networkSecurityConfig="@xml/existing"><activity android:name="Main" android:configChanges="uiMode">
<intent-filter><category android:name="android.intent.category.LAUNCHER" /></intent-filter>
</activity></application></manifest>''')
            configure_android(project)
            configure_android(project)
            application = ET.parse(manifest).getroot().find('application')
            def attr(name):
                return '{http://schemas.android.com/apk/res/android}' + name
            self.assertEqual(application.get(attr('networkSecurityConfig')), '@xml/existing')
            activity = application.find('activity')
            self.assertEqual(activity.get(attr('supportsPictureInPicture')), 'true')
            self.assertEqual(activity.get(attr('configChanges')).count('screenSize'), 1)

    def test_ios_pinned_framework_and_native_source_survive_repeat_refresh(self):
        with TemporaryDirectory() as directory:
            project = Path(directory)
            app = project / 'LogisticsMobile'
            app.mkdir()
            (app / 'main.m').write_text('#import <UIKit/UIKit.h>\nint main() {}')
            (app / 'LogisticsMobile-Info.plist').write_bytes(plistlib.dumps({'Keep': True}))
            pbx = project / 'Logistics Mobile.xcodeproj/project.pbxproj'
            pbx.parent.mkdir()
            pbx.write_bytes(plistlib.dumps(dict(rootObject='project', objects={
                'project': {}, 'app': dict(productType='com.apple.product-type.application', buildPhases=['frameworks']),
                'frameworks': dict(isa='PBXFrameworksBuildPhase', files=[])})))
            configure_ios(project)
            configure_ios(project)
            result = plistlib.loads(pbx.read_bytes())
            self.assertEqual(len(result['objects']['project']['packageReferences']), 1)
            self.assertEqual(len(result['objects']['frameworks']['files']), 4)
            packages = [value for value in result['objects'].values() if value.get('isa') == 'XCRemoteSwiftPackageReference']
            self.assertEqual(packages[0]['requirement']['kind'], 'revision')
            self.assertEqual((app / 'main.m').read_text().count('Support/VideoPlayer.m'), 1)
            self.assertTrue(plistlib.loads((app / 'LogisticsMobile-Info.plist').read_bytes())['Keep'])

    def test_mobile_allowlist_contains_video_engine_and_platform_sources(self):
        from mobile_build.tools import load_source_modules
        from services.mobile_features import document_feature
        _, sources = load_source_modules(Path(__file__).resolve().parents[3])
        self.assertIn('features/video/playback.py', sources)
        self.assertIn('features/video/mobile/ios/VideoPlayer.m', sources)
        # Local native compilation can mask a helper omitted from staged sources.
        import re
        owner = Path(__file__).resolve().parents[3] / 'Python/features/video/mobile/ios'
        for native in owner.glob('*.m'):
            for helper in re.findall(r'#import "([^"\n]+\.m)"', native.read_text()):
                if (owner / helper).is_file():
                    self.assertIn('features/video/mobile/ios/' + helper, sources)
                else:
                    import json
                    host = Path(__file__).resolve().parents[3] / 'Python/mobile'
                    modules = json.loads((host / 'mobile_sources.json').read_text())['modules']
                    self.assertIn('ios/' + helper, modules)
                    self.assertTrue((host / 'ios' / helper).is_file())
        self.assertEqual(document_feature('movie.MKV'), 'video')


class CloudVideoDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_browser_dispatches_video_without_document_materialization(self):
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock
        from features.rclone.mobile.cloud_ui import CloudUI
        app = SimpleNamespace(require_feature=lambda name: True)
        resource = Mock()
        resource.readers.side_effect = AssertionError('Video must not use a document snapshot')

        @asynccontextmanager
        async def activity(message):
            yield lambda message: None

        controller = SimpleNamespace(app=app, cloud_busy=False, cloud_open_remote='Secret',
            selected_cloud_remote=lambda: 'Secret', cloud_client=SimpleNamespace(supports_streaming=True),
            browser_state=SimpleNamespace(resource=resource), show_cloud=Mock(),
            cloud_status=SimpleNamespace(value=''), remote_activity=activity, open_crypt=AsyncMock())
        row = dict(path='movie.MKV', size=10**10, directory=False)
        with patch('services.documents.mobile_storage.open_provider_document', new_callable=AsyncMock) as open_video:
            open_video.return_value = True
            self.assertTrue(await CloudUI.open_remote_document(controller, row))
            open_video.assert_awaited_once_with(app, resource, 'movie.MKV')
        controller.open_crypt.assert_not_called()
        resource.readers.assert_not_called()

    async def test_optional_cloud_sidecar_failure_does_not_block_video(self):
        from features.video.mobile.player import MobileVideo
        owner = object.__new__(MobileVideo)
        owner.app = SimpleNamespace(_impl=None)
        owner.progress = Mock(load=lambda: 1234)
        owner.controls = SimpleNamespace(store=Mock())
        owner.content = SimpleNamespace(path='movie.mp4', remote=True,
            provider=Mock(list=Mock(side_effect=OSError('listing unavailable'))))
        self.assertEqual(owner.prepare(), (1234, []))
        owner.content.provider.list.assert_not_called()
        self.assertEqual(owner.prepare_sidecars(), [])
        owner.content.remote = False
        with self.assertRaises(OSError):
            owner.prepare()

    async def test_session_remote_resume_does_not_perform_network_metadata_on_controls(self):
        from services.documents.video_progress import VideoProgress
        content = SimpleNamespace(provider=SimpleNamespace(remote_storage=True, identity='test'),
            path='movie.mkv', source=SimpleNamespace(expected=(1,)),
            check_access=Mock(), check=Mock(side_effect=AssertionError('Network stat on control thread')))
        cipher = SimpleNamespace(transform=lambda data, identity, decode=False: data[6:] if decode else b'opaque' + data)
        with TemporaryDirectory() as root:
            progress = VideoProgress(content, root, remote_cipher=cipher)
            progress.save(3456)
            restored = VideoProgress(content, root, remote_cipher=cipher)
            self.assertEqual(restored.load(), 3456)
            self.assertEqual(restored.state.mode, 'session-memory')
            self.assertFalse(list(Path(root).rglob('*.bin')))
            content.check.assert_not_called()

    async def test_video_feature_cannot_be_disabled_while_player_is_open(self):
        from mobile.feature_settings import set_enabled
        app = SimpleNamespace(video_player=SimpleNamespace(closed=False, content=Mock()))
        with self.assertRaisesRegex(ValueError, 'Close the video'):
            set_enabled(app, 'video', False)


class VideoPresentationReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_native_readiness_waits_for_teardown(self):
        from features.video.mobile.player import open_video

        ready, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        content = Mock(remote=False)
        app = SimpleNamespace(require_feature=lambda name: True, checkpoint=lambda: True,
            active_host=True, video_player=None)

        async def wait_ready():
            ready.set()
            await asyncio.Future()

        async def close():
            closing.set()
            await release.wait()
            content.close()
            app.video_player = None

        player = SimpleNamespace(prepare=lambda: (0, []), close=close, present=Mock(),
            allowed=lambda: True, closed=False, native=SimpleNamespace(wait_ready=wait_ready, play=Mock()))
        with patch('features.video.mobile.player.VideoContent', return_value=content), patch(
                'features.video.mobile.player.MobileVideo', return_value=player), patch(
                'services.documents.mobile_storage.remember_video') as remember:
            opening = asyncio.create_task(open_video(app, Mock(), 'movie.mp4'))
            try:
                await asyncio.wait_for(ready.wait(), 2)
                self.assertIs(app.video_player, player)
                opening.cancel('cancel during readiness')
                await asyncio.wait_for(closing.wait(), 2)
                for _ in range(2):
                    opening.cancel('cancel during teardown')
                    await asyncio.sleep(0)
                    self.assertFalse(opening.done())
                    content.close.assert_not_called()
                release.set()
                with self.assertRaisesRegex(asyncio.CancelledError, 'cancel during readiness'):
                    await opening
            finally:
                release.set()
                if not ready.is_set():
                    opening.cancel()
                await asyncio.gather(opening, return_exceptions=True)
            player.present.assert_called_once_with(0, [], fullscreen=False)
            player.native.play.assert_not_called()
            remember.assert_not_called()
            self.assertIsNone(app.video_player)
            content.close.assert_called_once()

    async def test_cancelled_acquisition_reclaims_late_content(self):
        from threading import Event
        from features.video.mobile.player import open_video

        for fails in (False, True):
            with self.subTest(fails=fails):
                loop = asyncio.get_running_loop()
                entered, release = asyncio.Event(), Event()
                app = SimpleNamespace(require_feature=lambda name: True, checkpoint=lambda: True)
                content = Mock()

                def acquire(*args):
                    loop.call_soon_threadsafe(entered.set)
                    if not release.wait(5):
                        raise TimeoutError('Acquisition test gate timed out')
                    if fails:
                        raise OSError('Source unavailable')
                    return content

                with patch('features.video.mobile.player.VideoContent', side_effect=acquire), patch(
                        'features.video.mobile.player.MobileVideo') as player:
                    opening = asyncio.create_task(open_video(app, Mock(), 'movie.mp4'))
                    try:
                        await asyncio.wait_for(entered.wait(), 2)
                        for reason in ('original cancellation', 'repeated cancellation'):
                            opening.cancel(reason)
                            await asyncio.sleep(0)
                            self.assertFalse(opening.done())
                            content.close.assert_not_called()
                        release.set()
                        with self.assertRaisesRegex(asyncio.CancelledError, 'original cancellation'):
                            await opening
                    finally:
                        release.set()
                        await asyncio.gather(opening, return_exceptions=True)
                    player.assert_not_called()
                self.assertEqual(content.close.call_count, 0 if fails else 1)

    async def test_cancelled_preparation_retires_before_cleanup_and_waits_for_close(self):
        from threading import Event
        from features.video.mobile.player import open_video

        loop = asyncio.get_running_loop()
        preparing, closing, finish_close = asyncio.Event(), asyncio.Event(), asyncio.Event()
        finish_prepare, prepared = Event(), Event()
        app = SimpleNamespace(require_feature=lambda name: True, checkpoint=lambda: True,
            active_host=True, video_player=None)
        content = Mock()

        def prepare():
            loop.call_soon_threadsafe(preparing.set)
            if not finish_prepare.wait(5):
                raise TimeoutError('Preparation test gate timed out')
            prepared.set()
            return 0, []

        async def close():
            self.assertTrue(prepared.is_set())
            closing.set()
            await finish_close.wait()
            content.close()

        player = SimpleNamespace(prepare=prepare, close=close, present=Mock(),
            allowed=lambda: True, closed=False, native=SimpleNamespace(play=Mock()))
        with patch('features.video.mobile.player.VideoContent', return_value=content), patch(
                'features.video.mobile.player.MobileVideo', return_value=player), patch(
                'services.documents.mobile_storage.remember_video') as remember:
            opening = asyncio.create_task(open_video(app, Mock(), 'movie.mp4'))
            try:
                await asyncio.wait_for(preparing.wait(), 2)
                opening.cancel('original cancellation')
                await asyncio.sleep(0)
                opening.cancel('during preparation')
                await asyncio.sleep(0)
                self.assertFalse(closing.is_set())
                self.assertFalse(opening.done())
                finish_prepare.set()
                await asyncio.wait_for(closing.wait(), 2)
                opening.cancel('during close')
                await asyncio.sleep(0)
                opening.cancel('again during close')
                await asyncio.sleep(0)
                self.assertFalse(opening.done())
                content.close.assert_not_called()
                finish_close.set()
                with self.assertRaisesRegex(asyncio.CancelledError, 'original cancellation'):
                    await opening
            finally:
                finish_prepare.set()
                finish_close.set()
                await asyncio.gather(opening, return_exceptions=True)
            player.present.assert_not_called()
            player.native.play.assert_not_called()
            remember.assert_not_called()
            self.assertIsNone(app.video_player)
            content.close.assert_called_once()

    async def test_open_waits_for_native_presentation_and_rechecks_navigation(self):
        from unittest.mock import AsyncMock
        from features.video.mobile.player import open_video
        app = SimpleNamespace(require_feature=lambda name: True, checkpoint=lambda: True,
            active_host=True, navigation_generation=1, video_player=None)
        ready = AsyncMock(return_value=True)
        player = SimpleNamespace(prepare=lambda: (0, []), allowed=lambda: True, closed=False,
            present=Mock(), native=SimpleNamespace(wait_ready=ready, play=Mock()), close=AsyncMock(),
            discover_sidecars=AsyncMock())
        with patch('features.video.mobile.player.VideoContent'), patch(
                'features.video.mobile.player.MobileVideo', return_value=player), patch(
                'services.documents.mobile_storage.remember_video') as remember:
            self.assertTrue(await open_video(app, Mock(), 'movie.mp4'))
        await player.discovery
        player.discover_sidecars.assert_awaited_once()
        remember.assert_called_once()
        ready.assert_awaited_once()
        player.native.play.assert_called_once()
        player.native.play.reset_mock()
        self.assertIs(app.video_player, player)
        app.video_player = None
        def moved():
            app.navigation_generation += 1
            return True
        ready.side_effect = moved
        with patch('features.video.mobile.player.VideoContent'), patch(
                'features.video.mobile.player.MobileVideo', return_value=player), patch(
                'services.documents.mobile_storage.remember_video') as remember:
            self.assertFalse(await open_video(app, Mock(), 'movie.mp4'))
        remember.assert_not_called()
        player.native.play.assert_not_called()
        player.close.assert_awaited_once()


class IOSPresentationPrivacyTests(unittest.TestCase):
    def test_airplay_codec_identifiers_match_the_remuxed_formats(self):
        from base64 import b64encode
        from features.video.mobile.mkv import codec_string

        # AVCDecoderConfigurationRecord, HEVCDecoderConfigurationRecord and
        # AudioSpecificConfig headers; Opus is sent as AAC-LC, never as Opus.
        cases = [
            ('h264', '01640028', 'avc1.640028'),
            ('hevc', '010220000000b0000000000099', 'hvc1.2.4.L153.B0'),
            ('hevc', '01616000000090000100000078', 'hvc1.A1.6.H120.90.00.01'),
            ('aac', '1190', 'mp4a.40.2'),
            ('aac', '2b92', 'mp4a.40.5'),
            ('ac3', '', 'ac-3'), ('eac3', '', 'ec-3'), ('opus', '', 'mp4a.40.2'),
        ]
        for codec, header, expected in cases:
            with self.subTest(codec=codec, header=header):
                self.assertEqual(codec_string(dict(codec=codec,
                    configuration=b64encode(bytes.fromhex(header)).decode('ascii'))), expected)
        for codec, header in [('h264', b'\x01'), ('hevc', b'\x01\x02'), ('aac', b'')]:
            with self.subTest(invalid=codec), self.assertRaises(ValueError):
                codec_string(dict(codec=codec, configuration=b64encode(header).decode('ascii')))

    def test_airplay_master_advertises_receiver_track_roles_and_codecs(self):
        from base64 import b64encode
        from features.video.mobile.mkv import master_playlist

        audio = {
            'audio-1': dict(id=1, name='Commentary', language='en', channels=2, codec='opus', commentary=True),
            'audio-2': dict(id=2, name='Main', language='en', channels=6, codec='eac3'),
            'audio-3': dict(id=3, name='French', language='fr', channels=6, codec='ac3'),
            'audio-4': dict(id=4, name='Description', language='en', channels=2, codec='opus', visualImpaired=True),
        }
        subtitles = {
            'text-5': dict(id=5, name='English', language='en'),
            'text-6': dict(id=6, name='Forced', language='en', forced=True),
            'text-7': dict(id=7, name='SDH', language='en', hearingImpaired=True),
            'text-8': dict(id=8, name='Invalid"\nmetadata', language='en"\n#EXT-X-ENDLIST'),
        }
        video = dict(codec='hevc', configuration=b64encode(bytes.fromhex('010220000000b0000000000099')).decode('ascii'),
                     width=3840, height=2160, range='PQ')
        master = master_playlist(audio, subtitles, 2, 40_000_000, video).decode('utf-8')
        rows = master.splitlines()
        self.assertEqual(sum(row.startswith('#EXT-X-MEDIA:') for row in rows), 8)
        main = next(row for row in rows if 'URI="audio-2/' in row)
        self.assertIn('DEFAULT=YES,AUTOSELECT=YES', main)
        commentary = next(row for row in rows if 'URI="audio-1/' in row)
        self.assertIn('DEFAULT=NO,AUTOSELECT=NO', commentary)
        french = next(row for row in rows if 'URI="audio-3/' in row)
        self.assertIn('AUTOSELECT=YES,LANGUAGE="fr"', french)
        description = next(row for row in rows if 'URI="audio-4/' in row)
        self.assertIn('CHARACTERISTICS="public.accessibility.describes-video"', description)
        forced = next(row for row in rows if 'URI="text-6/' in row)
        self.assertIn('AUTOSELECT=YES,FORCED=YES,LANGUAGE="en"', forced)
        sdh = next(row for row in rows if 'URI="text-7/' in row)
        self.assertIn('CHARACTERISTICS="public.accessibility.transcribes-spoken-dialog,public.accessibility.describes-music-and-sound"', sdh)
        unknown = next(row for row in rows if 'URI="text-8/' in row)
        self.assertIn('LANGUAGE="und"', unknown)
        self.assertNotIn('#EXT-X-ENDLIST', master)
        variant = next(row for row in rows if row.startswith('#EXT-X-STREAM-INF:'))
        self.assertIn('CODECS="hvc1.2.4.L153.B0,mp4a.40.2,ec-3,ac-3"', variant)
        self.assertIn('RESOLUTION=3840x2160', variant)
        self.assertIn('VIDEO-RANGE=PQ', variant)
        self.assertIn('AUDIO="audio"', variant)
        self.assertIn('SUBTITLES="text"', variant)

    def test_mkv_hls_range_and_revocation(self):
        from contextlib import nullcontext
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        from threading import Event
        from features.video.mobile.mkv import MKVStream

        allowed = Mock(return_value=True)
        owner = SimpleNamespace(allowed=allowed, content=Mock(size=200_000), subtitles=[])
        import json
        engine = SimpleNamespace(
            renditionsJSON=lambda: json.dumps(dict(boundaries=[0, 6000, 12000, 18000],
                video=dict(codec='h264', configuration='AWQAKA==', width=1920, height=1080),
                defaultAudio=1, audio=[dict(id=1, name='Main', language='eng', channels=6, codec='ac3'),
                                       dict(id=2, name='Commentary', language='eng', channels=2, codec='opus')],
                text=[dict(id=3, name='Spanish', language='spa')])),
            initializationForTrack=Mock(return_value=SimpleNamespace(payload=b'init')),
            fragment=Mock(return_value=SimpleNamespace(payload=b'abcdef')),
            textSegment=Mock(return_value='[[11900, 12500, "Hello & goodbye"]]'))
        bridge = Mock()
        bridge.streamAddress.return_value = '127.0.0.1'
        bridge.alloc.return_value.initWithPath.return_value = engine
        def from_native(data):
            return data.payload

        modules = {
            'rubicon': SimpleNamespace(),
            'rubicon.objc': SimpleNamespace(ObjCClass=lambda _: bridge, py_from_ns=from_native),
            'rubicon.objc.runtime': SimpleNamespace(autoreleasepool=nullcontext),
        }
        with patch.dict('sys.modules', modules):
            cancelled = Event()
            stream = MKVStream(owner, Path('/movie.mkv'), cancelled)
            try:
                with urlopen(stream.url, timeout=2) as response:
                    master = response.read()
                    self.assertIn(b'URI="audio-2/index.m3u8"', master)
                    self.assertIn(b'URI="text-3/index.m3u8"', master)
                for group in ('video', 'audio-2', 'text-3'):
                    uri = stream.url.replace('video.m3u8', group + '/index.m3u8')
                    with urlopen(uri, timeout=2) as response:
                        self.assertEqual(response.read().count(b'#EXTINF:6.000,'), 3)
                subtitle = stream.url.replace('video.m3u8', 'text-3/segment-2.vtt')
                with urlopen(subtitle, timeout=2) as response:
                    self.assertIn(b'00:00:11.900 --> 00:00:12.500\nHello &amp; goodbye', response.read())
                alternate_audio = stream.url.replace('video.m3u8', 'audio-2/segment-1.m4s')
                with urlopen(alternate_audio, timeout=2) as response:
                    self.assertEqual(response.read(), b'abcdef')
                fragment = stream.url.replace('video.m3u8', 'video/segment-2.m4s')
                request = Request(fragment, headers={'Range': 'bytes=2-4'})
                with urlopen(request, timeout=2) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.read(), b'cde')
                with urlopen(Request(fragment, method='HEAD'), timeout=2) as response:
                    self.assertEqual(response.headers['Content-Length'], '6')
                self.assertEqual(engine.fragment.call_args_list, [unittest.mock.call(1, track=2), unittest.mock.call(2, track=-1)])
                with self.assertRaises(HTTPError) as unrouted:
                    urlopen(fragment.replace(stream.route, '/unknown/'), timeout=2)
                self.assertEqual(unrouted.exception.code, 404)
                allowed.return_value = False
                with self.assertRaises(HTTPError) as revoked:
                    urlopen(fragment, timeout=2)
                self.assertEqual(revoked.exception.code, 404)
                self.assertEqual(engine.fragment.call_args_list, [unittest.mock.call(1, track=2), unittest.mock.call(2, track=-1)])
            finally:
                stream.close()

    def test_native_airplay_only_opens_admitted_ordinary_local_files(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from commonUtils.runtime.platform import OS
        from features.video.mobile.ios import airplay_file
        from features.video.playback import VideoContent
        from services.documents.locations import MobileLocalFiles

        with TemporaryDirectory() as directory, patch('commonUtils.runtime.platform.get_os', return_value=OS.IOS):
            root = Path(directory)
            path = root / 'My movie.MP4'
            path.write_bytes(b'local movie fixture')
            other = root / 'My movie.mkv'
            other.write_bytes(b'matroska fixture')
            preferences = SimpleNamespace(values={})
            for provider_type in (LocalFiles, MobileLocalFiles):
                with self.subTest(provider=provider_type):
                    content = VideoContent(provider_type(root), path.name)
                    self.addCleanup(content.close)
                    owner = SimpleNamespace(app=SimpleNamespace(preferences=preferences),
                        content=content, allowed=Mock(return_value=True))
                    preferences.values.clear()
                    self.assertIsNone(airplay_file(owner))
                    preferences.values['native_video_airplay'] = 'true'
                    self.assertEqual(airplay_file(owner), path)
                    owner.allowed.return_value = False
                    self.assertIsNone(airplay_file(owner))
                    owner.allowed.return_value = True
                    content.provider.private = True
                    self.assertIsNone(airplay_file(owner))
                    content.provider.private = False
                    content.remote = True
                    self.assertIsNone(airplay_file(owner))
                    content.remote = False
                    content.source.backend = Mock()
                    self.assertIsNone(airplay_file(owner))
                    content.source.backend = None
                    owner.content = VideoContent(provider_type(root), other.name)
                    self.addCleanup(owner.content.close)
                    self.assertEqual(airplay_file(owner), other)
                    owner.content = content
            path.write_bytes(b'replaced')
            self.assertIsNone(airplay_file(owner))

    def test_delayed_presentation_rechecks_authorization_and_hidden_state(self):
        from features.video.mobile.ios import IOSVideo
        owner = SimpleNamespace(closed=False, hidden=False, allowed=Mock(return_value=False))
        adapter = object.__new__(IOSVideo)
        adapter.disposed = False
        adapter.owner = owner
        adapter.native = Mock()
        adapter.presentation = object()
        adapter.show()
        adapter.native.revealSurface.assert_not_called()
        owner.allowed.return_value = True
        owner.hidden = True
        adapter.show()
        adapter.native.revealSurface.assert_not_called()

    def test_conceal_cancels_delayed_presentation_and_dismisses_the_video_stack(self):
        from features.video.mobile.ios import IOSVideo
        adapter = object.__new__(IOSVideo)
        adapter.native = Mock()
        presenter = SimpleNamespace(dismissViewControllerAnimated=Mock())
        adapter.container = presenter.presentedViewController = SimpleNamespace(
            presentingViewController=presenter, presentedViewController=object())
        pending = adapter.presentation = Mock()
        adapter.hide()
        pending.cancel.assert_called_once()
        adapter.native.suspendForLock.assert_called_once()
        presenter.dismissViewControllerAnimated.assert_called_once_with(False, completion=None)
        self.assertIsNone(adapter.presentation)
