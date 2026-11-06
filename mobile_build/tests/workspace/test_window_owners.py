
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from mobile.window_owners import WindowOwners
from mobile.workspace import Workspace
from pathlib import Path
import toga
from mobile.app import LogisticsMobile
from unittest.mock import Mock, patch
from mobile.window_scenes import SceneManager
import sys


class SceneRetirementTests(unittest.TestCase):
    def setUp(self):
        self.registrations = {}
        self.enterContext(patch('mobile.app._active_hosts', self.registrations))
        self.picker = self.enterContext(patch('commonUtils.ui.native.documents.cancel_document_picker'))
        self.manager = object.__new__(SceneManager)
        self.manager.app = SimpleNamespace(windows=[], factory=SimpleNamespace(), active_host=True)
        self.manager.owners = WindowOwners()
        self.manager.owners.attach('primary', self.manager.app)
        self.manager.scenes = {}
        self.manager.external_comics = Mock()
        self.manager.primary_disconnected = False
        self.manager.primary_disconnects = 0
        self.host = self.make_host()

    def make_host(self):
        host = SimpleNamespace(active_host=True, scene_active=True, window_id='b' * 32,
            private_root=Path('/scene-test'), checkpoint=Mock(return_value=True),
            release_disposable_resources=Mock(), main_window=SimpleNamespace(
                on_gain_focus=Mock(), on_lose_focus=Mock(), on_resize=Mock(), _impl=SimpleNamespace(native=Mock())),
            workspace=SimpleNamespace(sessions={'doc': SimpleNamespace(id='doc')}, invalidate=Mock()),
            text_views={}, memory_pressure=Mock(), screen_privacy=Mock(), seasonal_snow=Mock(),
            adaptive=Mock(), routes=Mock(), native_host=Mock(), audio_output=Mock(),
            startup_document_task=Mock(), _layout_participants=Mock(), _editor_picker=Mock())
        host.navigation = SimpleNamespace(app=host, window=host.main_window)
        host.scene_manager = self.manager
        self.manager.owners.attach(host.window_id, host)
        self.manager.owners.claim(host.window_id, ('managed-text', 'doc'))
        self.manager.scenes['native-scene'] = host
        self.manager.app.windows.append(host.main_window)
        self.registrations[str(host.private_root.resolve()) + ':' + host.window_id] = host
        return host

    def install_delegate(self):
        class NativeObject:
            def __init_subclass__(cls, **kwargs):
                pass
        self.enterContext(patch.dict(sys.modules, {
            'rubicon.objc': SimpleNamespace(ObjCClass=lambda name: NativeObject,
                ObjCProtocol=lambda name: name, objc_method=lambda method: method, objc_property=lambda: None),
            'toga_iOS.app': SimpleNamespace(PythonAppDelegate=NativeObject),
            'toga_iOS.window': SimpleNamespace(MainWindow=NativeObject),
        }))
        self.manager.install_ios()
        delegate = self.manager.external_scene_delegate()
        delegate.host = self.host
        return delegate

    def test_secondary_uses_complete_host_retirement_and_releases_its_registrations(self):
        self.manager.disconnect(self.host)
        self.host.audio_output.dispose.assert_called_once_with()
        self.host.startup_document_task.cancel.assert_called_once_with()
        self.host._layout_participants.dispose.assert_called_once_with()
        self.host._editor_picker.clear.assert_called_once_with()
        self.host.release_disposable_resources.assert_not_called()
        self.assertFalse(self.host.active_host)
        self.assertTrue(self.manager.app.active_host)
        self.assertNotIn(self.host.window_id, self.manager.owners.hosts)
        self.assertFalse(self.manager.owners.writers)
        self.assertFalse(self.manager.scenes)
        self.assertFalse(self.manager.app.windows)
        self.assertFalse(self.registrations)
        self.manager.external_comics.dispose.assert_not_called()

    def test_failed_resource_retries_without_detaching_a_new_host_with_the_same_key(self):
        old = self.host
        old.memory_pressure.dispose.side_effect = RuntimeError('private-native-detail')
        with self.assertLogs('mobile.application_lifecycle', level='ERROR') as logs:
            self.manager.disconnect(old)
        self.assertNotIn('private-native-detail', '\n'.join(logs.output))
        old.audio_output.dispose.assert_called_once_with()
        old.native_host.dispose.assert_called_once_with()
        self.assertFalse(self.manager.app.windows)
        new = self.make_host()
        old.memory_pressure.dispose.side_effect = None
        self.manager.disconnect(old)
        self.assertEqual(old.memory_pressure.dispose.call_count, 2)
        old.audio_output.dispose.assert_called_once_with()
        old.checkpoint.assert_called_once_with()
        self.assertIs(self.manager.owners.hosts[old.window_id], new)
        self.assertEqual(self.manager.owners.writers[('managed-text', 'doc')], new.window_id)
        self.assertEqual(self.manager.scenes, {'native-scene': new})
        self.assertEqual(self.manager.app.windows, [new.main_window])
        self.assertIs(self.registrations[str(old.private_root.resolve()) + ':' + old.window_id], new)
        self.assertTrue(new.active_host)

    def test_retirement_closes_scene_callback_gate_before_checkpoint_and_native_cleanup(self):
        delegate = self.install_delegate()
        def callbacks():
            delegate.sceneDidBecomeActive_(None)
            delegate.sceneWillResignActive_(None)
            delegate.sceneDidEnterBackground_(None)
        focus = self.host.main_window.on_gain_focus
        def checkpoint():
            if self.host.checkpoint.call_count == 1:
                callbacks()
            return True
        self.host.checkpoint.side_effect = checkpoint
        self.host.native_host.dispose.side_effect = callbacks
        self.manager.disconnect(self.host)
        callbacks()
        self.host.checkpoint.assert_called_once_with()
        self.host.screen_privacy.reveal.assert_not_called()
        self.host.screen_privacy.interrupt.assert_not_called()
        self.host.screen_privacy.conceal.assert_not_called()
        focus.assert_not_called()

    def test_reentrant_disconnect_does_not_repeat_in_progress_cleanup(self):
        registrations_during_cleanup = []
        def dispose():
            # A native adapter can synchronously deliver another notification.
            if self.host.native_host.dispose.call_count == 1:
                self.manager.disconnect(self.host)
            registrations_during_cleanup.append(self.manager.owners.hosts.get(self.host.window_id))
        self.host.native_host.dispose.side_effect = dispose
        self.manager.disconnect(self.host)
        self.host.native_host.dispose.assert_called_once_with()
        self.assertEqual(len(registrations_during_cleanup), 1)
        self.assertIs(registrations_during_cleanup[0], self.host)
        self.host.checkpoint.assert_called_once_with()
        self.assertNotIn(self.host.window_id, self.manager.owners.hosts)

    def test_unexpected_retirement_error_still_releases_scene_registrations(self):
        from mobile.application_lifecycle import lifecycle
        with patch.object(lifecycle(self.host), 'retire_secondary_scene', side_effect=RuntimeError('synthetic')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                self.manager.disconnect(self.host)
        self.assertNotIn(self.host.window_id, self.manager.owners.hosts)
        self.assertFalse(self.manager.owners.writers)
        self.assertFalse(self.manager.scenes)
        self.assertFalse(self.manager.app.windows)
        self.assertFalse(self.registrations)

    def test_primary_disconnect_reuses_live_host_on_native_reconnect(self):
        primary = self.host
        self.manager.owners.detach(primary.window_id)
        self.manager.owners.detach('primary')
        primary.window_id = 'primary'
        primary.factory = SimpleNamespace()
        primary.windows = [primary.main_window]
        self.manager.app = primary
        self.manager.owners.attach('primary', primary)
        self.manager.owners.claim('primary', ('managed-text', 'doc'))
        primary.native_scene = object()
        delegate = self.install_delegate()
        self.manager.disconnect(primary)
        self.manager.disconnect(primary)
        self.assertTrue(primary.active_host)
        self.assertTrue(self.manager.primary_disconnected)
        self.assertEqual(self.manager.primary_disconnects, 1)
        primary.checkpoint.assert_called_once_with()
        primary.audio_output.dispose.assert_not_called()
        primary.native_host.dispose.assert_not_called()
        self.assertIs(self.manager.owners.hosts['primary'], primary)
        self.assertEqual(self.manager.owners.writers[('managed-text', 'doc')], 'primary')
        session = SimpleNamespace(role='UIWindowSceneSessionRoleApplication',
            persistentIdentifier='reconnected-primary', stateRestorationActivity=None)
        scene = SimpleNamespace(session=session)
        options = SimpleNamespace(userActivities=None, URLContexts=None)
        delegate.scene_willConnectToSession_options_(scene, session, options)
        self.assertIs(delegate.host, primary)
        self.assertIs(primary.native_scene, scene)
        self.assertFalse(self.manager.primary_disconnected)
        delegate.sceneDidBecomeActive_(scene)
        primary.screen_privacy.reveal.assert_called_once_with()
        primary.main_window.on_gain_focus.assert_called_once_with()

    def test_voluntary_close_veto_keeps_secondary_live(self):
        self.host.checkpoint.return_value = False
        self.assertFalse(self.manager.close_window(self.host))
        self.assertTrue(self.host.active_host)
        self.assertIs(self.manager.owners.hosts[self.host.window_id], self.host)
        self.host.audio_output.dispose.assert_not_called()
        self.picker.assert_not_called()


class WindowOwnerTests(unittest.TestCase):
    def test_failed_secondary_startup_releases_its_identity_and_leaves_primary_live(self):
        from unittest.mock import patch
        from mobile.app import _active_hosts
        from mobile_build.tests.support.app import mobile_app
        with mobile_app() as app:
            manager = app.scene_manager
            manager.window_class = toga.Window
            identifier = 'c' * 32
            windows = set(app.windows)
            owners = dict(manager.owners.hosts)
            writers = dict(manager.owners.writers)
            failed = []
            attach = LogisticsMobile._attach_startup_window
            def fail(host, restored_document):
                attach(host, restored_document)
                failed.append(host)
                raise ValueError('synthetic late scene startup failure')
            with patch.object(LogisticsMobile, '_attach_startup_window', fail):
                with self.assertRaisesRegex(ValueError, 'synthetic late scene startup failure'):
                    manager.make_host(identifier)
            self.assertFalse(failed[0].active_host)
            self.assertTrue(app.active_host)
            self.assertEqual(set(app.windows), windows)
            self.assertEqual(manager.owners.hosts, owners)
            self.assertEqual(manager.owners.writers, writers)
            self.assertNotIn(str(app.private_root.resolve()) + ':' + identifier, _active_hosts)
            restored = manager.make_host(identifier)
            self.assertTrue(restored.active_host)
            self.assertIs(manager.owners.hosts[identifier], restored)
            manager.disconnect(restored)

    def test_scene_activity_before_privacy_initialization_waits_for_ready_host(self):
        from unittest.mock import Mock
        from mobile.window_scenes import SceneManager
        host = SimpleNamespace(main_window=SimpleNamespace(on_gain_focus=Mock()), checkpoint=Mock())
        SceneManager.scene_activity(host, True)
        self.assertTrue(host.scene_active)
        SceneManager.scene_activity(host, False)
        self.assertFalse(host.scene_active)
        host.main_window.on_gain_focus.assert_not_called()
        host.checkpoint.assert_not_called()
        host.screen_privacy = SimpleNamespace(reveal=Mock(), interrupt=Mock())
        SceneManager.scene_activity(host, True)
        host.screen_privacy.reveal.assert_called_once()
        host.main_window.on_gain_focus.assert_called_once()
        SceneManager.scene_activity(host, False)
        host.screen_privacy.interrupt.assert_called_once()
        host.checkpoint.assert_called_once()

    def test_independent_host_callbacks_and_restoration(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            app.show_documents()
            manager = app.scene_manager
            manager.window_class = toga.Window
            child = manager.make_host('b' * 32)
            self.assertIs(child.commands, app.commands)
            child.show_documents()
            self.assertNotEqual(app.current.id, child.current.id)
            self.assertIsNot(app.routes, child.routes)
            child.editor.value = 'Child draft'
            app.editor.value = 'Primary draft'
            self.assertFalse(child.open_document(app.current.id))
            self.assertEqual(child.editor.value, 'Child draft')
            child.show_settings()
            self.assertTrue(child.checkpoint())
            key = child.current.id
            from unittest.mock import Mock
            keyboard = child._keyboard_dismissal = Mock()
            primary_keyboard = app._keyboard_dismissal = Mock()
            manager.disconnect(child)
            keyboard.dispose.assert_called_once()
            manager.disconnect(child)
            keyboard.dispose.assert_called_once()
            primary_keyboard.dispose.assert_not_called()
            restored = manager.make_host('b' * 32)
            self.assertEqual(restored.current.id, key)
            self.assertEqual(restored.editor.value, 'Child draft')
            self.assertEqual(restored.native_host.state.destination, 'settings')
            self.assertEqual(app.editor.value, 'Primary draft')

    def test_duplicate_writer_private_boundary_and_release(self):
        with TemporaryDirectory() as directory:
            owners = WindowOwners()
            a, b = Workspace(directory + '/a'), Workspace(directory + '/b')
            for key, workspace in [('a', a), ('b', b)]:
                owners.attach(key, SimpleNamespace(workspace=workspace))
                workspace.window_owners, workspace.window_id = owners, key
            first = a.open('managed-text', 'a' * 32, 'text')
            with self.assertRaisesRegex(ValueError, 'another window'):
                b.open('managed-text', 'a' * 32, 'text')
            with self.assertRaisesRegex(ValueError, 'protected'):
                b.open('provider-session', 'secret', 'text', transient=True)
            self.assertFalse(a.close(first.id, guard=lambda value: False))
            self.assertEqual(owners.writers[first.identity], 'a')
            self.assertTrue(a.close(first.id, guard=lambda value: True))
            second = b.open('managed-text', 'a' * 32, 'text')
            owners.detach('b')
            self.assertNotIn(second.identity, owners.writers)
