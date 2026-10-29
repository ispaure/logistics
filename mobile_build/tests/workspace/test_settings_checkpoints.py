"""Settings navigation preserves edits once and avoids unchanged recovery writes."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile.app import LogisticsMobile


class SettingsCheckpointTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', LogisticsMobile.storage_root)
        LogisticsMobile.storage_root = Path(directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        doc = self.app.store.create('Note.md', b'original')
        self.app.open_document(doc.id)
        width = patch.object(self.app.adaptive, 'content_width', return_value=390)
        self.width = width.start()
        self.addCleanup(width.stop)

    def test_settings_tab_checkpoints_once_and_saves_workspace_once(self):
        app = self.app
        for opening in ('first', 'return'):
            with self.subTest(opening=opening), \
                    patch.object(app.store, 'checkpoint', wraps=app.store.checkpoint) as checkpoint, \
                    patch.object(app, 'save_workspace', wraps=app.save_workspace) as save, \
                    patch('os.fsync') as flush:
                self.assertTrue(app.select_destination('settings'))
                checkpoint.assert_called_once_with(app.current)
                save.assert_called_once_with()
                flush.assert_not_called()

    def test_category_change_preserves_new_edits_once_in_compact_and_wide_layouts(self):
        app = self.app
        app.show_settings()
        nav = app.settings_navigation
        for width in (390, 900):
            with self.subTest(width=width):
                self.width.return_value = width
                nav.reflow()
                app.current.text = f'unsaved edits at {width}'
                with patch.object(app.store, 'checkpoint', wraps=app.store.checkpoint) as checkpoint, \
                        patch('os.fsync', wraps=os.fsync) as flush:
                    nav.choose('Text')
                checkpoint.assert_called_once_with(app.current)
                self.assertEqual(flush.call_count, 2)
                self.assertEqual(app.store.open(app.current.id).text, app.current.text)
                with patch('os.fsync') as flush:
                    nav.choose('App')
                flush.assert_not_called()

    def test_failed_checkpoint_blocks_category_change_and_can_be_retried(self):
        app = self.app
        app.show_settings()
        nav = app.settings_navigation
        for width in (390, 900):
            with self.subTest(width=width):
                self.width.return_value = width
                nav.reflow()
                app.current.text = f'pending edits at {width}'
                selected = nav.selected
                screens = list(app.routes.screens['settings'])
                with patch('mobile.documents.atomic_write_json', side_effect=OSError('storage full')):
                    nav.choose('Books & Comics')
                    self.assertFalse(app.select_destination('home'))
                self.assertEqual(nav.selected, selected)
                self.assertEqual(app.routes.screens['settings'], screens)
                self.assertIn('Could not preserve edits', app.status.text)
                nav.choose('Books & Comics')
                self.assertEqual(nav.selected, 'Books & Comics')
                self.assertEqual(app.store.open(app.current.id).text, app.current.text)

    def test_private_unsaved_draft_still_blocks_settings_navigation(self):
        app = self.app
        app.show_settings()
        nav = app.settings_navigation
        app.store.privatize(app.current)
        app.current.text = 'session-only edit'
        with patch('mobile.documents.atomic_write_json') as write:
            nav.choose('Books & Comics')
            self.assertFalse(app.select_destination('home'))
        self.assertEqual(nav.selected, 'App')
        self.assertIn('session-only', app.status.text)
        write.assert_not_called()
