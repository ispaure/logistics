"""Feature selection persists, gates real openings and preserves user documents."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile.app import LogisticsMobile
from mobile.preferences import Preferences
from mobile.document_choices import available_choices
from services.mobile_features import FEATURES, enabled
from services.documents.mobile_notebooks import open_notebook


class MobileFeatureTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        LogisticsMobile.storage_root = self.root
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_home()

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.run_until_complete(self.app.loop.shutdown_default_executor())
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def run_async(self, action):
        return self.app.loop.run_until_complete(action)

    def test_existing_preferences_and_new_installs_enable_every_current_feature(self):
        self.assertTrue(all(enabled(self.app.preferences, feature.name) for feature in FEATURES))
        root = self.root / 'old-install'
        root.mkdir()
        (root / 'preferences.ini').write_text('[Mobile]\ntext_font_size = 24\n')
        old = Preferences(root)
        self.assertEqual(old.values['text_font_size'], '24')
        self.assertTrue(all(enabled(old, feature.name) for feature in FEATURES))

    def test_switches_persist_desktop_groups_and_remain_on_the_features_page(self):
        app = self.app
        app.show_settings()
        app.settings_navigation.choose('Features')
        control = app.settings_navigation.sections['Features'].feature_switches['books']
        control.value = False
        self.run_async(asyncio.sleep(0))
        self.assertFalse(app.feature_enabled('books'))
        self.assertFalse(app.feature_enabled('comics'))
        self.assertTrue(app.feature_enabled('pdf'))
        self.assertFalse(enabled(Preferences(self.root), 'books'))
        self.assertEqual(app.settings_navigation.selected, 'Features')
        self.assertFalse(app.settings_navigation.sections['Features'].feature_switches['books'].value)
        self.assertNotIn('EPUB', app.settings_navigation.sections)
        self.assertNotIn('comics', app.settings_navigation.sections['Features'].feature_switches)
        control = app.settings_navigation.sections['Features'].feature_switches['books']
        control.value = True
        self.run_async(asyncio.sleep(0))
        self.assertTrue(app.feature_enabled('books'))
        self.assertTrue(app.feature_enabled('comics'))

    def test_legacy_partial_book_selection_can_enable_the_entire_group(self):
        self.app.preferences.save(disabled_features='["comics"]')
        self.app.show_settings()
        self.app.settings_navigation.choose('Features')
        control = self.app.settings_navigation.sections['Features'].feature_switches['books']
        self.assertFalse(control.value)
        control.value = True
        self.run_async(asyncio.sleep(0))
        self.assertTrue(self.app.feature_enabled('books'))
        self.assertTrue(enabled(Preferences(self.root), 'comics'))

    def test_book_group_refuses_disable_when_a_comic_is_open(self):
        from mobile.workspace import Session
        app = self.app
        app.workspace.sessions['comic'] = Session('comic', 'comic', 'a' * 32, 'comic', title='Issue.cbz')
        with self.assertRaisesRegex(ValueError, 'Close the open Books & Comics'):
            app.set_feature_enabled('books', False, refresh=False)
        self.assertTrue(app.feature_enabled('books'))
        self.assertTrue(app.feature_enabled('comics'))

    def test_notebook_off_removes_creation_type_and_blocks_open_without_writing(self):
        app = self.app
        app.set_feature_enabled('notebooks', False, refresh=False)
        self.assertNotIn('rmdoc', dict(available_choices(app)).values())
        self.assertFalse(self.run_async(open_notebook(app, name='Blocked')))
        self.assertFalse(getattr(app, '_notebook_views', {}))
        self.assertFalse(list((self.root / 'notebooks').glob('*/base.rmdoc')))
        app.set_feature_enabled('notebooks', True, refresh=False)
        self.assertIn('rmdoc', dict(available_choices(app)).values())
        self.assertTrue(self.run_async(open_notebook(app, name='Allowed')))

    def test_disabled_books_and_comics_do_not_construct_a_library_on_launch(self):
        app = self.app
        app.set_feature_enabled('books', False, refresh=False)
        app.set_feature_enabled('comics', False, refresh=False)
        app.show_library()
        self.assertNotIn('readers', app.__dict__)
        app.set_feature_enabled('books', True, refresh=False)
        app.show_library()
        self.assertIn('readers', app.__dict__)
        self.assertTrue(hasattr(app.readers.catalog, 'library_store'))
        self.run_async(app.readers.catalog.wait_for_refresh())

    def test_disable_refuses_open_notebook_and_keeps_edits_and_preference(self):
        app = self.app
        self.assertTrue(self.run_async(open_notebook(app, name='Keep me')))
        panel = app.notebook_panel
        panel.editor.apply(dict(op='stroke', points=[[1,2,.5],[4,6,.8]], tool=12, width=2))
        with self.assertRaisesRegex(ValueError, 'Close the open Notebooks'):
            app.set_feature_enabled('notebooks', False, refresh=False)
        self.assertTrue(app.feature_enabled('notebooks'))
        self.assertEqual(len(panel.editor.notebook.page(0).strokes), 1)
        self.assertIn(panel.session.id, app.workspace.sessions)

    def test_disabled_chat_tab_offers_enable_without_starting_a_client(self):
        app = self.app
        app.set_feature_enabled('lm', False, refresh=False)
        app.native_host.activate('chat')
        app.select_destination('chat')
        chat = app.chat_controller()
        self.assertFalse(hasattr(chat, 'chat_store'))
        self.assertFalse(app.feature_enabled('lm'))
        view = app.routes.roots['chat'].children[0]
        view.children[2].on_press()
        self.run_async(asyncio.sleep(0))
        self.assertTrue(app.feature_enabled('lm'))
        self.assertTrue(hasattr(chat, 'chat_store'))
        self.assertIsNone(chat.state.client)

    def test_cloud_off_keeps_local_text_creation_and_hides_remote_sources(self):
        app = self.app
        app.set_feature_enabled('rclone', False)
        self.run_async(asyncio.sleep(0))
        self.assertIsNone(app.start_cloud_restore())
        self.assertEqual(app.existing_crypt_locations(), {})
        app.show_folder_picker(initialize=False)
        self.assertEqual(set(app.folder_source_buttons), {'Local'})
        app.show_home()
        self.run_async(app.choose_document_type())
        picker = app.editor_picker()
        picker.save_as_name.value = 'Offline'
        self.run_async(picker.browser_editor_location(('Local', '')))
        self.run_async(picker.confirm_editor_file())
        self.assertEqual((self.root / 'LocalFiles/Offline.txt').read_bytes(), b'')
        self.assertIsNotNone(app.private_sessions.active)
        app.set_feature_enabled('rclone', False, refresh=False)
        self.run_async(picker.show_crypt_save_as(owner=app.private_sessions.active))
        self.assertEqual(picker.save_as_storage.value, 'Source location')
        picker.save_as_name.value = 'Offline copy.txt'
        self.run_async(picker.confirm_editor_file())
        self.assertTrue((self.root / 'LocalFiles/Offline copy.txt').is_file())

    def test_disabled_cloud_hides_remote_recent_references(self):
        from mobile.workspace import Session
        from services.mobile_features import session_enabled
        self.app.set_feature_enabled('rclone', False, refresh=False)
        reference = Session('', 'file-reference', 'a' * 64, 'markdown', title='Remote.md')
        reference.source = dict(type='remote', remote='Drive', key='Remote.md')
        self.assertFalse(session_enabled(self.app.preferences, reference))
        reference.source = dict(type='local', path=str(self.root / 'Remote.md'))
        self.assertTrue(session_enabled(self.app.preferences, reference))

    def test_disabling_cloud_retires_retained_remote_routes(self):
        import toga
        app = self.app
        app.show_view(toga.Box(), destination='files', route='remote-browser', title='Remote files')
        app.show_settings()
        app.set_feature_enabled('rclone', False)
        self.run_async(asyncio.sleep(0))
        self.assertFalse(app.routes.screens['files'])
        app.select_destination('files')
        self.assertEqual(set(app.folder_source_buttons), {'Local'})

    def test_disabled_readers_are_rejected_before_reading_source_bytes(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.mobile_storage import TextDocumentCopies
        from unittest.mock import Mock
        app = self.app
        copies = TextDocumentCopies(LocalFiles(self.root))
        copies.open = Mock(side_effect=AssertionError('Disabled reader must not read the file'))
        for name, feature in [('Book.epub', 'books'), ('Comic.cbz', 'comics'),
                              ('Document.pdf', 'pdf'), ('Photo.png', 'images'), ('Note.md', 'text_editor')]:
            with self.subTest(feature=feature):
                app.set_feature_enabled(feature, False, refresh=False)
                self.assertFalse(self.run_async(app.provider_sessions().open(copies, name)))
                copies.open.assert_not_called()
                self.assertFalse(app.workspace.sessions)
                app.set_feature_enabled(feature, True, refresh=False)

    def test_rejected_save_restores_switch_and_does_not_disable_feature(self):
        app = self.app
        app.show_settings()
        app.settings_navigation.choose('Features')
        control = app.settings_navigation.sections['Features'].feature_switches['books']
        with patch.object(app.preferences, 'save', side_effect=OSError('Disk full')):
            control.value = False
        self.assertTrue(control.value)
        self.assertTrue(app.feature_enabled('comics'))
        self.assertIn('Disk full', app.settings_status.text)

    def test_scene_windows_share_feature_choices_but_keep_other_preferences(self):
        from types import SimpleNamespace
        from mobile.feature_settings import set_enabled
        from mobile.workspace import Workspace, Session
        app = self.app
        directory = self.root / 'Windows/secondary'
        preferences = Preferences(directory)
        preferences.save(text_font_size='24')
        preferences.feature_preferences = app.preferences
        other = SimpleNamespace(preferences=preferences, workspace=Workspace(directory), scene_manager=app.scene_manager)
        with patch.object(app.scene_manager.owners, 'hosts', {'primary': app, 'secondary': other}):
            set_enabled(other, 'notebooks', False, refresh=False)
            self.assertFalse(app.feature_enabled('notebooks'))
            self.assertFalse(enabled(other.preferences, 'notebooks'))
            self.assertFalse(enabled(Preferences(self.root), 'notebooks'))
            self.assertEqual(Preferences(directory).values['text_font_size'], '24')
            other.workspace.sessions['active'] = Session('active', 'notebook', 'a' * 32, 'notebook', title='Drawing')
            with self.assertRaisesRegex(ValueError, 'Close the open Notebooks'):
                app.set_feature_enabled('notebooks', False, refresh=False)

    def test_invalid_feature_file_is_preserved_and_defaults_remain_on(self):
        path = self.root / 'preferences.ini'
        data = '[Mobile]\ndisabled_features = ["unknown-feature"]\n'
        path.write_text(data)
        settings = Preferences(self.root)
        self.assertTrue(settings.error)
        self.assertEqual(path.read_text(), data)
        self.assertEqual(json.loads(settings.values['disabled_features']), [])


if __name__ == '__main__':
    unittest.main()
