"""Exact picker destinations, shared ID navigation and stale retrieval guards."""
from contextlib import contextmanager
from io import BufferedReader, BytesIO
from pathlib import Path
import tarfile
from unittest.mock import patch
from zipfile import ZipFile

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.testing.stages import TestStage
from commonUtils.ui import pyside as qt
from features.notebooks import remarkable_ssh
from features.notebooks.notebook import Notebook
from features.notebooks.remarkable_store import ROOT, TabletSnapshot
from features.notebooks.ui import remarkable_destination, remarkable_retrieval
from features.notebooks.ui.remarkable_browser import TabletBrowser

TEST_STAGE = TestStage.REGRESSION
FOLDER = '10000000-0000-4000-8000-000000000001'
OTHER = '10000000-0000-4000-8000-000000000002'
DOCUMENT = '10000000-0000-4000-8000-000000000003'


def fixture():
    return TabletSnapshot.from_metadata({FOLDER: dict(type='CollectionType', visibleName='Same'),
        OTHER: dict(type='CollectionType', visibleName='Same'),
        DOCUMENT: dict(type='DocumentType', visibleName='Journal', parent=FOLDER)})


class RemarkableRetrievalTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def picker(self, path, *, accepted=True, after_selection=lambda: None):
        def execute(dialog):
            self.assertEqual(dialog.acceptMode(), qt.QFileDialog.AcceptMode.AcceptSave)
            self.assertEqual(dialog.defaultSuffix(), 'rmdoc')
            self.assertFalse(dialog.testOption(qt.QFileDialog.Option.DontConfirmOverwrite))
            self.assertFalse(dialog.testOption(qt.QFileDialog.Option.DontUseNativeDialog))
            if not accepted:
                return qt.QDialog.DialogCode.Rejected
            dialog.selectFile(str(path))
            dialog.fileSelected.emit(dialog.selectedFiles()[0])
            after_selection()
            return qt.QDialog.DialogCode.Accepted
        return patch.object(qt.QFileDialog, 'exec', execute)

    def test_picker_resolves_default_suffix_before_capture_and_decline_returns_none(self):
        with self.temporary_directory() as folder:
            name = Path(folder) / 'Notebook'
            with self.picker(name):
                path, revision = remarkable_destination.choose_destination(None, name)
            self.assertEqual(path, name.with_suffix('.rmdoc'))
            self.assertIsNone(revision)
            path.write_bytes(b'existing')
            with self.picker(path, accepted=False):
                self.assertIsNone(remarkable_destination.choose_destination(None, path))
            self.assertEqual(path.read_bytes(), b'existing')

    def test_picker_captures_revision_once_and_never_retargets_a_different_extension(self):
        with self.temporary_directory() as folder:
            path = Path(folder) / 'Notebook.rmdoc'
            path.write_bytes(b'existing')
            expected = remarkable_destination.local_document_export_revision(path)
            with self.picker(path, after_selection=lambda: path.write_bytes(b'changed after selection')):
                self.assertEqual(remarkable_destination.choose_destination(None, path), (path, expected))
            with self.picker(path.with_suffix('.txt')):
                with self.assertRaisesRegex(ValueError, 'ending in .rmdoc'):
                    remarkable_destination.choose_destination(None, path)
            self.assertFalse(path.with_suffix('.txt.rmdoc').exists())

    def test_shared_browser_displays_names_and_navigates_empty_duplicate_folders(self):
        browser = TabletBrowser(fixture())
        self.assertEqual(browser.model.rowCount(browser.model.browse_index(ROOT)), 2)
        browser.navigate(OTHER)
        self.assertEqual(browser.model.rowCount(browser.model.browse_index(OTHER)), 0)
        self.assertEqual([button.text() for button in browser.breadcrumbs.buttons], ['reMarkable', 'Same'])
        browser.up.click()
        browser.search.setText('Journal')
        self.assertTrue(browser.model.browse_index(FOLDER).isValid())
        self.assertFalse(browser.model.browse_index(OTHER).isValid())
        self.assertEqual(browser.model.data(browser.model.browse_index(DOCUMENT)), 'Journal')
        self.assertIn(DOCUMENT, browser.model.data(browser.model.browse_index(DOCUMENT), qt.Qt.ItemDataRole.ToolTipRole))
        browser.activate(browser.model.browse_index(FOLDER))
        self.assertEqual(browser.directory, FOLDER)
        self.assertEqual(browser.search.text(), '')
        browser.views.select_source(browser.model.browse_index(DOCUMENT))
        browser.view_selector.setCurrentIndex(1)
        self.assertEqual(browser.selected(), DOCUMENT)
        self.assertEqual(browser.directory, FOLDER)
        browser.step(-1)
        self.assertEqual(browser.directory, ROOT)
        browser.stop()

    def connected_dialog(self, snapshot=None):
        dialog = remarkable_retrieval.RetrievalDialog()
        dialog.host.setText('synthetic.invalid')
        with patch.object(remarkable_retrieval, 'list_snapshot', return_value=snapshot or fixture()):
            dialog.connect_tablet()
            self.wait_until(lambda: not dialog.progress.busy)
        return dialog

    def test_refresh_preserves_valid_location_and_removed_folder_returns_to_root(self):
        dialog = self.connected_dialog()
        dialog.browser.navigate(FOLDER)
        dialog.browser.views.select_source(dialog.browser.model.browse_index(DOCUMENT))
        previous = dialog.browser
        with patch.object(remarkable_retrieval, 'list_snapshot', return_value=fixture()):
            dialog.connect_tablet()
            self.assertFalse(dialog.save_button.isEnabled())
            self.wait_until(lambda: not dialog.progress.busy)
        self.assertTrue(previous.closing)
        self.assertEqual(dialog.browser.directory, FOLDER)
        self.assertEqual(dialog.browser.selected(), DOCUMENT)
        self.assertTrue(dialog.save_button.isEnabled())
        with patch.object(remarkable_retrieval, 'list_snapshot', return_value=TabletSnapshot.from_metadata({})):
            dialog.connect_tablet()
            self.wait_until(lambda: not dialog.progress.busy)
        self.assertEqual(dialog.browser.directory, ROOT)
        self.assertFalse(dialog.save_button.isEnabled())

    def test_endpoint_change_failure_and_stale_completion_disable_retrieval(self):
        dialog = self.connected_dialog()
        dialog.browser.navigate(FOLDER)
        dialog.browser.views.select_source(dialog.browser.model.browse_index(DOCUMENT))
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.port.setValue(2222)
        self.assertFalse(dialog.save_button.isEnabled())
        with patch.object(remarkable_retrieval, 'list_snapshot', side_effect=OSError('Synthetic disconnect')):
            dialog.connect_tablet()
            self.wait_until(lambda: not dialog.progress.busy)
        self.assertIsNone(dialog.connected_endpoint)
        self.assertFalse(dialog.browser.isEnabled())
        dialog.completed((dialog.connection_generation - 1, ('synthetic.invalid', 2222), fixture()), '')
        self.assertIsNone(dialog.connected_endpoint)

    def test_retrieval_replaces_native_fixture_and_preserves_file_appearing_after_selection(self):
        book = Notebook.new('Synthetic retrieval', template='Blank')
        with ZipFile(BytesIO(book.to_bytes())) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        buffer = BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            for name, data in entries.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, BytesIO(data))

        @contextmanager
        def stream(*args, **kwargs):
            with BufferedReader(BytesIO(buffer.getvalue())) as data:
                yield data

        snapshot = TabletSnapshot.from_metadata({book.id: dict(type='DocumentType', visibleName=book.name)})
        with self.temporary_directory() as folder, patch.object(remarkable_ssh, 'ssh_stream', stream):
            dialog = self.connected_dialog(snapshot)
            dialog.browser.views.select_source(dialog.browser.model.browse_index(book.id))
            path = Path(folder) / 'retrieved.rmdoc'
            path.write_bytes(b'old')
            with self.picker(path):
                dialog.choose_destination()
                self.wait_until(lambda: not dialog.progress.busy)
            self.assertEqual(Notebook.read(path.read_bytes()).name, book.name)
            with self.picker(path, accepted=False):
                before = path.read_bytes()
                dialog.choose_destination()
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(dialog.progress.busy)
            path.unlink()
            with self.picker(path, after_selection=lambda: path.write_bytes(b'concurrent creator')):
                dialog.choose_destination()
                self.wait_until(lambda: not dialog.progress.busy)
            self.assertEqual(path.read_bytes(), b'concurrent creator')
            self.assertIn('already exists', dialog.progress.message.text())

    def test_selection_cannot_retarget_to_a_new_endpoint_during_picker(self):
        dialog = self.connected_dialog()
        dialog.browser.navigate(FOLDER)
        dialog.browser.views.select_source(dialog.browser.model.browse_index(DOCUMENT))
        with self.temporary_directory() as folder:
            path = Path(folder) / 'copy.rmdoc'
            with self.picker(path, after_selection=lambda: dialog.port.setValue(2222)), \
                    patch.object(remarkable_retrieval, 'export_document') as export:
                dialog.choose_destination()
            export.assert_not_called()
            self.assertFalse(path.exists())
