"""Notes Library destination admission, lifetime and saved-reference reopening."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock, patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.contributions import RegisteredContribution
from desktop import main_window
from tests.application._main_window_fixture import MainWindowFixture


class NotesLibraryHostingTests(MainWindowFixture, QtTestCase):
    def test_notes_library_disabled_at_startup_rejects_saved_reference_before_provider_open(self):
        from commonUtils.ui.document_host import current_document_host
        from features.notes_library.ui.notes_library import open_notes
        from desktop.document_catalog import reopen
        window = self.window(); window.dlg.show()
        # A disabled-at-startup feature has no constructed destination host.
        with patch.dict(self.app._commonutils_document_hosts, {'notes_library': lambda: None}), patch.object(
                main_window.registry, 'is_feature_enabled', return_value=False), patch(
                'features.notes_library.ui.library_workspace.TabbedNotesLibrary') as constructor, patch(
                'desktop.document_catalog.provider_for') as provider, patch.object(qt.QMessageBox, 'warning') as warning:
            self.assertIsNone(current_document_host(destination='notes_library'))
            factory = Mock()
            with self.assertRaisesRegex(ValueError, 'Enable Notes Library'):
                open_notes(factory, 'Disabled')
            row = dict(source=dict(type='crypt', path='Home.md'),
                       opener=dict(editor='notes', root='Vault'), title='Home.md')
            self.assertIsNone(reopen(row, window.dlg))
            warning.assert_called_once()
            provider.assert_not_called(); factory.assert_not_called(); constructor.assert_not_called()

    def test_notes_library_closing_host_never_falls_back_to_a_standalone_window(self):
        from features.notes_library.ui.notes_library import open_notes
        window = self.window(); window.dlg.show()
        window.documents.closing = True
        try:
            with patch.dict(self.app._commonutils_document_hosts, {'notes_library': lambda: None}), patch.object(
                    main_window.registry, 'is_feature_enabled', return_value=True):
                factory = Mock()
                with self.assertRaisesRegex(ValueError, 'closing'):
                    open_notes(factory, 'Closing')
                factory.assert_not_called()
        finally:
            window.documents.closing = False

    def test_notes_library_retries_failed_initial_load_and_reuses_hidden_host(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from commonUtils.runtime.resources.local import LocalFiles
        from commonUtils.ui.document_host import request_document_close, CloseOutcome
        from features.notes_library import register
        from features.notes_library.ui.notes_library import open_notes
        entry = RegisteredContribution('notes_library', 'Notes Library', register().pages[0])
        with TemporaryDirectory() as directory, patch.object(main_window.registry, 'get_pages', return_value=[entry]):
            root = Path(directory); (root / 'Home.md').write_text('# Home')
            window = self.window([entry]); window.dlg.show()
            page = window._feature_pages['notes_library', 'notes_library.workspace']
            broken = LocalFiles(root)
            with patch.object(broken, 'list', side_effect=OSError('Temporarily unavailable')):
                failed = open_notes(lambda: broken, 'Retry')
                self.wait_until(lambda: not failed.progress.busy)
            self.assertIsNone(failed.library)
            retried = open_notes(lambda: LocalFiles(root), 'Retry')
            self.assertIsNot(retried, failed)
            self.wait_until(lambda: retried.library is not None and not retried.progress.busy)
            self.assertEqual(page.count, 1)
            window.dlg.hide()
            self.assertIs(open_notes(lambda: LocalFiles(root), 'Retry'), retried)
            self.assertEqual(page.count, 1)
            (root / 'Other').mkdir()
            hidden = open_notes(lambda: LocalFiles(root / 'Other'), 'Hidden host')
            self.wait_until(lambda: hidden.library is not None and not hidden.progress.busy)
            self.assertIn(hidden, page.records)
            self.assertFalse(hidden.isWindow())
            self.assertEqual(page.count, 2)
            window.dlg.show()
            for owner in (retried, hidden):
                self.wait_until(lambda owner=owner: request_document_close(owner) is CloseOutcome.ACCEPTED)

    def test_notes_favourite_waits_for_a_busy_retained_library(self):
        from types import SimpleNamespace
        from desktop.document_catalog import reopen
        class Library(qt.QWidget):
            idle = qt.Signal()
        owner = Library()
        self.addCleanup(owner.deleteLater)
        owner.library = object()
        owner.progress = SimpleNamespace(busy=True)
        owner.open_note = Mock()
        row = dict(source=dict(type='local', path='/notes/Home.md'),
                   opener=dict(editor='notes', root='/notes'), title='Home.md')
        with patch('features.notes_library.ui.notes_library.open_notes', return_value=owner):
            self.assertIs(reopen(row), owner)
        owner.open_note.assert_not_called()
        owner.idle.emit()
        owner.open_note.assert_not_called()
        owner.progress.busy = False
        owner.idle.emit()
        owner.open_note.assert_called_once_with('Home.md')
        owner.idle.emit()
        owner.open_note.assert_called_once()

    def test_notes_library_has_own_destination_reuses_roots_and_survives_disable(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from commonUtils.runtime.resources.local import LocalFiles
        from commonUtils.ui.document_host import close_document, current_document_host
        from features.notes_library import register
        from features.notes_library.ui.notes_library import open_notes
        entry = RegisteredContribution('notes_library', 'Notes Library', register().pages[0])
        pages = [entry]
        with TemporaryDirectory() as directory, patch.object(main_window.registry, 'get_pages', side_effect=lambda: pages), patch.object(
                main_window.registry, 'is_feature_enabled', side_effect=lambda name: bool(pages) if name == 'notes_library' else name != 'text_editor'):
            root = Path(directory)
            (root / 'A').mkdir(); (root / 'B').mkdir()
            # Ordinary folders need no Obsidian marker.
            (root / 'A/note.md').write_text('# First')
            (root / 'B/note.md').write_text('# Second')
            window = self.window(pages); window.dlg.show()
            page = window._feature_pages['notes_library', 'notes_library.workspace']
            self.assertIs(current_document_host(destination='notes_library'), page)
            key = window._launch_key('notes_library', 'notes_library.workspace')
            button = window.sidebar.buttons[key]
            self.assertEqual(window.sidebar.library_destinations.indexOf(button), 0)
            self.assertEqual(button.accessibleName(), 'Notes Library')
            self.assertLess(window.sidebar.buttons['documents'].geometry().top(), button.geometry().top())
            from threading import get_ident
            provider_threads = []
            def factory():
                provider_threads.append(get_ident())
                return LocalFiles(root / 'A')
            first = open_notes(factory, 'Same label')
            self.assertNotEqual(provider_threads, [get_ident()])
            self.wait_until(lambda: first.library is not None and not first.progress.busy)
            self.assertIs(window.tabs.currentWidget(), page)
            self.assertEqual(window.documents.count, 0)
            self.assertEqual(page.count, 1)
            self.assertIs(open_notes(lambda: LocalFiles(root), 'Other label', root='A'), first)
            second = open_notes(lambda: LocalFiles(root / 'B'), 'Same label')
            self.wait_until(lambda: second.library is not None and not second.progress.busy)
            self.assertEqual(page.count, 2)
            note = first.open_note('note.md')
            self.wait_until(lambda: note.index >= 0 and not note.progress.busy)
            note.viewer.set_editing(True); note.viewer.set_edit_mode('source')
            note.viewer.editor.insertPlainText('draft ')
            page.present(second); page.present(first)
            self.assertTrue(note.viewer.is_modified)
            # Registry no longer contributes the disabled page, but open sessions stay reachable.
            pages.clear(); window._sync_feature_pages()
            self.assertGreaterEqual(window.tabs.indexOf(page), 0)
            page._refresh_choosers()
            with self.assertRaisesRegex(ValueError, 'Enable Notes Library'):
                open_notes(lambda: LocalFiles(root / 'A'), 'Disabled')
            self.assertIn(key, window.sidebar.buttons)
            self.assertTrue(window.sidebar.buttons[key].isVisible())
            self.assertEqual(window.sidebar.library_destinations.indexOf(button), 0)
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(window.can_close())
            self.assertFalse(window._closing)
            self.assertFalse(page.closing)
            page.closing = True  # A previous asynchronous quit may already have stopped admission.
            page.can_close = lambda: False
            self.assertFalse(window.can_close())
            self.assertFalse(page.closing)
            del page.can_close
            self.assertTrue(note.viewer.is_modified)
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard):
                self.assertTrue(close_document(first))
            self.assertTrue(close_document(second))
            self.wait_until(lambda: page.count == 0)
            window._sync_feature_pages()
            self.assertEqual(window.tabs.indexOf(page), -1)

    def test_cancelled_library_provider_preparation_releases_lease_without_a_session(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from threading import Event
        from commonUtils.runtime.resources.local import LocalFiles
        from commonUtils.ui.resources.picker import ResourceTaskDialog
        from features.notes_library import register
        from features.notes_library.ui.notes_library import open_notes
        entry = RegisteredContribution('notes_library', 'Notes Library', register().pages[0])
        with TemporaryDirectory() as directory, patch.object(main_window.registry, 'get_pages', return_value=[entry]):
            window = self.window([entry]); window.dlg.show()
            page = window._feature_pages['notes_library', 'notes_library.workspace']
            provider = LocalFiles(Path(directory))
            entered, proceed = Event(), Event()
            releases = []
            provider.acquire = lambda: lambda: releases.append(True)
            def factory():
                entered.set()
                if not proceed.wait(3):
                    raise RuntimeError('Cancellation timer did not run')
                return provider
            timer = qt.QTimer(window.dlg)
            def cancel():
                if entered.is_set():
                    loading = window.dlg.findChild(ResourceTaskDialog)
                    if loading is not None:
                        loading.reject(); proceed.set(); timer.stop()
            timer.timeout.connect(cancel); timer.start(5)
            try:
                self.assertIsNone(open_notes(factory, 'Cancelled'))
                self.assertEqual(releases, [True])
                self.assertEqual(page.count, 0)
            finally:
                proceed.set(); timer.stop()

    def test_notes_library_detaches_and_favourite_reopens_existing_note(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from commonUtils.runtime.resources.local import LocalFiles
        from commonUtils.ui.document_host import close_document
        from features.notes_library import register
        from features.notes_library.ui.notes_library import open_notes
        from desktop.document_catalog import reopen
        entry = RegisteredContribution('notes_library', 'Notes Library', register().pages[0])
        with TemporaryDirectory() as directory, patch.object(main_window.registry, 'get_pages', return_value=[entry]):
            root = Path(directory); (root / 'note.md').write_text('# Hello')
            window = self.window([entry]); window.dlg.show()
            page = window._feature_pages['notes_library', 'notes_library.workspace']
            owner = open_notes(lambda: LocalFiles(root), 'Notes')
            self.wait_until(lambda: owner.library is not None and not owner.progress.busy)
            page.workspace.detach_active()
            self.app.processEvents()
            self.assertTrue(page.records[owner]['detached'])
            self.assertIs(open_notes(lambda: LocalFiles(root), 'Notes'), owner)
            self.assertTrue(page.records[owner]['detached'])
            row = dict(source=dict(type='local', path=str(root / 'note.md')),
                       opener=dict(editor='notes', root=str(root)), title='note.md')
            self.assertIs(reopen(row, window.dlg), owner)
            self.wait_until(lambda: owner.document_tabs.current is not None
                            and owner.document_tabs.path(owner.document_tabs.current) == 'note.md'
                            and not owner.document_tabs.current.progress.busy)
            self.assertEqual(page.count, 1)
            page.attach(owner)
            self.assertFalse(page.records[owner]['detached'])
            from commonUtils.ui.document_host import request_document_close, CloseOutcome
            self.wait_until(lambda: request_document_close(owner) is CloseOutcome.ACCEPTED)
            self.wait_until(lambda: page.count == 0)
