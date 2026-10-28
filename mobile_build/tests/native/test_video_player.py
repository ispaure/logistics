"""Mobile playback admission, privacy lifetime and generated project wiring."""
import asyncio
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from mobile_build.build_support.video_build import configure_android, configure_ios


class VideoMobileLifetimeTests(unittest.IsolatedAsyncioTestCase):
    def player(self, *, restricted=True):
        from features.video.mobile.player import MobileVideo
        app = SimpleNamespace(active_host=True, private_root=Path('/unused'), loop=asyncio.get_running_loop())
        content = SimpleNamespace(provider=SimpleNamespace(storage_id='test', private=False),
            source=SimpleNamespace(expected=(1,), check_access=Mock()), path='movie.mkv',
            restricted=restricted, check_access=Mock(), require_external=Mock(), close=Mock())
        with patch('features.video.mobile.player.VideoTransport'):
            owner = MobileVideo(app, content)
        owner.native = Mock()
        owner.native.position.return_value = (12000, False)
        owner.progress = Mock()
        app.video_player = owner
        return owner

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

    async def test_native_controls_deny_pending_resume_even_if_own_gate_is_unlocked(self):
        owner = self.player()
        privacy = SimpleNamespace(inactive=True, saved_content=None, gates=lambda: ())
        owner.app.screen_privacy = privacy
        self.assertFalse(owner.allowed())
        owner.transport.resume.assert_not_called()
        privacy.inactive = False
        privacy.saved_content = object()
        self.assertFalse(owner.allowed())
        privacy.saved_content = None
        privacy.gates = lambda: (SimpleNamespace(locked=True),)
        self.assertFalse(owner.allowed())
        privacy.gates = lambda: ()
        self.assertTrue(owner.allowed())
        owner.content.check_access.assert_called_once()
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
        owner.transport.close.assert_called_once()
        self.assertIsNone(owner.app.video_player)
        self.assertFalse(owner.allowed())

    async def test_failed_checkpoint_does_not_open_or_read_video(self):
        from features.video.mobile.player import open_video
        app = SimpleNamespace(require_feature=lambda name: True, checkpoint=lambda: False)
        with patch('features.video.mobile.player.VideoContent') as content:
            self.assertFalse(await open_video(app, Mock(), 'movie.mp4'))
            content.assert_not_called()


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
            self.assertEqual(len(result['objects']['frameworks']['files']), 2)
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
        owner.progress = Mock(load=lambda: 1234)
        owner.content = SimpleNamespace(path='movie.mp4', remote=True,
            provider=Mock(list=Mock(side_effect=OSError('listing unavailable'))))
        self.assertEqual(owner.prepare(), (1234, []))
        owner.content.remote = False
        with self.assertRaises(OSError):
            owner.prepare()

    async def test_remote_memory_resume_does_not_perform_network_metadata_on_controls(self):
        from services.documents.video_progress import VideoProgress
        content = SimpleNamespace(provider=SimpleNamespace(remote_storage=True),
            check_access=Mock(), check=Mock(side_effect=AssertionError('Network stat on control thread')))
        progress = VideoProgress(content, '/unused')
        progress.save(3456)
        self.assertEqual(progress.load(), 3456)
        content.check.assert_not_called()

    async def test_video_feature_cannot_be_disabled_while_player_is_open(self):
        from mobile.feature_settings import set_enabled
        app = SimpleNamespace(video_player=SimpleNamespace(closed=False, content=Mock()))
        with self.assertRaisesRegex(ValueError, 'Close the video'):
            set_enabled(app, 'video', False)


class VideoPresentationReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_waits_for_native_presentation_and_rechecks_navigation(self):
        from unittest.mock import AsyncMock
        from features.video.mobile.player import open_video
        app = SimpleNamespace(require_feature=lambda name: True, checkpoint=lambda: True,
            active_host=True, navigation_generation=1, video_player=None)
        ready = AsyncMock(return_value=True)
        player = SimpleNamespace(prepare=lambda: (0, []), allowed=lambda: True, closed=False,
            present=Mock(), native=SimpleNamespace(wait_ready=ready), close=AsyncMock())
        with patch('features.video.mobile.player.VideoContent'), patch(
                'features.video.mobile.player.MobileVideo', return_value=player):
            self.assertTrue(await open_video(app, Mock(), 'movie.mp4'))
        ready.assert_awaited_once()
        self.assertIs(app.video_player, player)
        app.video_player = None
        def moved():
            app.navigation_generation += 1
            return True
        ready.side_effect = moved
        with patch('features.video.mobile.player.VideoContent'), patch(
                'features.video.mobile.player.MobileVideo', return_value=player):
            self.assertFalse(await open_video(app, Mock(), 'movie.mp4'))
        player.close.assert_awaited_once()


class IOSPresentationPrivacyTests(unittest.TestCase):
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

    def test_conceal_cancels_delayed_native_presentation(self):
        from features.video.mobile.ios import IOSVideo
        adapter = object.__new__(IOSVideo)
        adapter.native = Mock()
        pending = adapter.presentation = Mock()
        adapter.hide()
        pending.cancel.assert_called_once()
        adapter.native.suspendForLock.assert_called_once()
        self.assertIsNone(adapter.presentation)
