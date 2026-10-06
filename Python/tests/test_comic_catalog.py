"""Incremental suggestions and floating list helpers use disposable libraries."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from features.comics.catalog import LibraryCatalog, split_values
from features.comics.library import ComicDocument


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'comic.cbz'
        self.catalog = LibraryCatalog(self.root)

    def comic(self, path=None, writer='Alice, Bob', publisher='Publisher'):
        with zipfile.ZipFile(path or self.path, 'w') as archive:
            archive.writestr('01.png', b'original pages')
            archive.writestr('ComicInfo.xml', f'<ComicInfo><Writer>{writer}</Writer><Publisher>{publisher}</Publisher></ComicInfo>')

    def test_unchanged_archives_skip_xml_and_changed_deleted_new_files_refresh(self):
        self.comic()
        first = self.catalog.refresh()
        self.assertEqual(first['suggestions']['Writer'], ['Alice', 'Bob'])
        before = self.catalog.path.read_bytes()
        with patch('features.comics.catalog.ComicDocument', side_effect=AssertionError('Unchanged XML was reopened')):
            cached = self.catalog.refresh()
        self.assertEqual(cached['parsed'], 0)
        self.assertEqual(before, self.catalog.path.read_bytes())
        ComicDocument(self.path).save({'Writer': 'Carol'})
        extra = self.root / 'extra.CBZ'
        self.comic(extra, 'Dave')
        updated = self.catalog.refresh()
        self.assertEqual(updated['parsed'], 2)
        self.assertEqual(updated['suggestions']['Writer'], ['Carol', 'Dave'])
        self.path.unlink()
        self.assertEqual(self.catalog.refresh()['suggestions']['Writer'], ['Dave'])
        data = json.loads(self.catalog.path.read_text())
        self.assertEqual(set(data['files']), {'extra.CBZ'})
        self.assertEqual(data['files']['extra.CBZ'][:2], [extra.stat().st_mtime_ns, extra.stat().st_size])
        self.assertEqual(data['suggestions']['Writer'], ['Dave'])

    def test_compact_cache_stores_only_unique_nonempty_autofill_values(self):
        self.comic(writer='Repeated author')
        document = ComicDocument(self.path)
        document.save({'Series': 'Do not cache this series', 'Title': 'Do not cache this title'})
        extra = self.root / 'extra.cbz'
        extra.write_bytes(self.path.read_bytes())
        self.catalog.refresh()
        data = json.loads(self.catalog.path.read_text())
        self.assertEqual(set(data['suggestions']), {'Writer', 'Publisher'})
        self.assertEqual(data['suggestions']['Writer'], ['Repeated author'])
        self.assertEqual(data['files']['comic.cbz'][2], {'Writer': [0], 'Publisher': [0]})
        text = self.catalog.path.read_text()
        self.assertEqual(text.count('Repeated author'), 1)
        self.assertNotIn('Do not cache', text)
        self.assertNotIn('metadata_sha256', text)
        self.assertNotIn('Inker', text)
        self.assertNotIn(': ', text)

    def test_existing_cache_migrates_without_reopening_unchanged_archives(self):
        self.comic()
        signature = self.path.stat()
        self.catalog.path.parent.mkdir()
        self.catalog.path.write_text(json.dumps({'version': 1, 'files': {'comic.cbz': {
            'signature': [signature.st_size, signature.st_mtime_ns, signature.st_ctime_ns,
                          signature.st_dev, signature.st_ino],
            'metadata_sha256': 'obsolete hash',
            'fields': {'Writer': 'Alice, Bob', 'Publisher': 'Publisher', 'Inker': '', 'Series': 'Unused'}
        }}}))
        with patch('features.comics.catalog.ComicDocument', side_effect=AssertionError('Migration reopened XML')):
            result = self.catalog.refresh()
        self.assertEqual(result['parsed'], 0)
        self.assertEqual(result['suggestions'], {'Writer': ['Alice', 'Bob'], 'Publisher': ['Publisher']})
        data = json.loads(self.catalog.path.read_text())
        self.assertEqual(data['version'], self.catalog.VERSION)
        self.assertNotIn('Unused', self.catalog.path.read_text())

    def test_empty_metadata_keeps_only_change_tracking_and_is_reused(self):
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('01.png', b'original pages')
        self.catalog.refresh()
        data = json.loads(self.catalog.path.read_text())
        self.assertEqual(data['suggestions'], {})
        self.assertEqual(data['files']['comic.cbz'][2], {})
        with patch('features.comics.catalog.ComicDocument', side_effect=AssertionError('Empty archive reopened')):
            self.assertEqual(self.catalog.refresh()['parsed'], 0)

    def test_bad_pooled_reference_rebuilds_only_the_affected_file(self):
        self.comic()
        extra = self.root / 'extra.cbz'
        self.comic(extra, 'Carol')
        self.catalog.refresh()
        data = json.loads(self.catalog.path.read_text())
        data['files']['comic.cbz'][2]['Writer'] = [-1]
        self.catalog.path.write_text(json.dumps(data))
        with patch('features.comics.catalog.ComicDocument', wraps=ComicDocument) as loaded:
            result = self.catalog.refresh()
        self.assertEqual(result['parsed'], 1)
        loaded.assert_called_once_with(self.path)
        self.assertEqual(result['suggestions']['Writer'], ['Alice', 'Bob', 'Carol'])

    def test_whitespace_normalizes_new_and_cached_suggestions_without_changing_xml(self):
        self.comic(writer='Alice  Writer, Bob', publisher='Publisher&#10;')
        before = self.path.read_bytes()
        result = self.catalog.refresh()
        self.assertEqual(result['suggestions']['Publisher'], ['Publisher'])
        self.assertEqual(result['suggestions']['Writer'], ['Alice Writer', 'Bob'])
        data = json.loads(self.catalog.path.read_text())
        data['version'] = 2
        data['suggestions']['Publisher'] = ['  Publisher\r\n', 'Publisher']
        data['files']['comic.cbz'][2]['Publisher'] = [0, 1]
        self.catalog.path.write_text(json.dumps(data))
        with patch('features.comics.catalog.ComicDocument', side_effect=AssertionError('Unchanged archive reopened')):
            migrated = self.catalog.refresh()
        self.assertEqual(migrated['suggestions']['Publisher'], ['Publisher'])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(json.loads(self.catalog.path.read_text())['version'], self.catalog.VERSION)

    def test_tags_are_indexed_from_standard_xml_field(self):
        self.comic()
        ComicDocument(self.path).save({'Tags': 'One tag, Second tag'})
        self.assertEqual(self.catalog.refresh()['suggestions']['Tags'], ['One tag', 'Second tag'])

    def test_index_reads_only_metadata_and_preserves_archive_bytes(self):
        self.comic()
        before = self.path.read_bytes()
        original_open = zipfile.ZipFile.open
        opened = []
        def open_member(archive, member, *args, **kwargs):
            opened.append(member.filename if isinstance(member, zipfile.ZipInfo) else member)
            return original_open(archive, member, *args, **kwargs)
        with patch.object(zipfile.ZipFile, 'open', open_member):
            self.catalog.refresh()
        self.assertEqual(opened, ['ComicInfo.xml'])
        self.assertEqual(before, self.path.read_bytes())

    def test_corrupt_cache_bad_archive_and_write_failure_are_recoverable(self):
        self.comic()
        self.catalog.path.parent.mkdir()
        self.catalog.path.write_text('invalid JSON')
        broken = self.root / 'broken.cbz'
        broken.write_bytes(b'not a zip')
        with patch('features.comics.catalog.os.replace', side_effect=PermissionError('read only')):
            result = self.catalog.refresh()
        self.assertEqual(result['suggestions']['Writer'], ['Alice', 'Bob'])
        self.assertEqual(result['count'], 1)
        self.assertEqual(len(result['errors']), 2)
        self.assertFalse(list(self.catalog.path.parent.glob('*.tmp')))
        self.assertEqual(self.catalog.refresh()['parsed'], 1)

    def test_cancelled_index_keeps_previous_cache_and_skips_links_data_folder(self):
        self.comic()
        self.catalog.refresh()
        before = self.catalog.path.read_bytes()
        (self.root / 'link.cbz').symlink_to(self.path)
        self.comic(self.catalog.path.parent / 'ignored.cbz', 'Ignored')
        self.assertEqual(self.catalog.refresh()['count'], 1)
        self.assertIsNone(self.catalog.refresh(lambda: True))
        self.assertEqual(self.catalog.path.read_bytes(), before)

    def test_list_normalization_preserves_order_and_deduplicates(self):
        self.assertEqual(split_values(' A, B\nC\r\nA, , B '), ['A', 'B', 'C'])


class PopupTests(unittest.TestCase):
    def setUp(self):
        from commonUtils.ui import pyside as qt
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def form(self, values=None):
        from features.comics.ui.metadata_form import MetadataForm
        form = MetadataForm()
        form.load_values(values or [{field: '' for field in form.editors}])
        self.addCleanup(form.deleteLater)
        return form

    def test_three_modes_preserve_untouched_values_and_update_one_pending_field(self):
        from commonUtils.ui import pyside as qt
        form = self.form()
        values = {field: '' for field in form.editors}
        values['Writer'] = 'Alice,Bob'
        form.load_values([values])
        form.set_suggestions({'Writer': ['Alice', 'Bob', 'Carol']})
        form.open_list('Writer')
        popup = form.popup
        self.assertTrue(popup.windowFlags() & qt.Qt.WindowType.Popup)
        self.assertEqual([popup.tabs.tabText(i) for i in range(3)], ['Lists', 'Check', 'Text'])
        for tab in range(3):
            popup.tabs.setCurrentIndex(tab)
        self.assertEqual(form.changes(), {})
        popup.tabs.setCurrentIndex(0)
        popup.available.item(0).setSelected(True)
        popup._add()
        self.assertEqual(form.changes(), {'Writer': 'Alice, Bob, Carol'})
        popup.tabs.setCurrentIndex(1)
        item = next(popup.checks.item(i) for i in range(popup.checks.count()) if popup.checks.item(i).text() == 'Bob')
        item.setCheckState(qt.Qt.CheckState.Unchecked)
        self.assertEqual(form.changes(), {'Writer': 'Alice, Carol'})
        popup.tabs.setCurrentIndex(2)
        popup.text.setPlainText('New\nOther, New')
        self.assertEqual(form.changes(), {'Writer': 'New, Other'})
        popup.close()
        self.assertTrue(form.editors['Writer'].property('pendingChange'))
        form.revert_field('Writer')
        self.assertEqual(form.editors['Writer'].text(), 'Alice,Bob')
        self.assertFalse(form.changes())

    def test_suggestion_refresh_preserves_pending_values_and_removes_stale_dropdown_items(self):
        form = self.form()
        form.editors['Publisher'].setEditText('Pending')
        form.set_suggestions({'Publisher': ['Old', 'Existing']})
        self.assertEqual(form.changes(), {'Publisher': 'Pending'})
        form.set_suggestions({'Publisher': ['New']})
        self.assertEqual(form.editors['Publisher'].currentText(), 'Pending')
        self.assertEqual(form.editors['Publisher'].findData('Old'), -1)
        self.assertGreaterEqual(form.editors['Publisher'].findData('New'), 0)
        self.assertEqual(form.changes(), {'Publisher': 'Pending'})

    def test_publisher_display_is_normalized_while_original_xml_value_is_retained(self):
        from features.comics.ui.metadata_widgets import editor_value
        form = self.form()
        values = {field: '' for field in form.editors}
        values['Publisher'] = '  Publisher\n'
        form.load_values([values])
        form.set_suggestions({'Publisher': ['Publisher']})
        self.assertEqual(form.editors['Publisher'].currentText(), 'Publisher')
        self.assertEqual(editor_value(form.editors['Publisher']), values['Publisher'])
        self.assertFalse(form.changes())

    def test_mixed_popup_open_is_noop_new_values_and_clear_are_explicit(self):
        form = self.form()
        first = {field: '' for field in form.editors}
        second = dict(first, Tags='Original')
        form.load_values([first, second])
        form.open_list('Tags')
        self.assertEqual(form.changes(), {})
        popup = form.popup
        popup._clear()
        self.assertEqual(form.changes(), {'Tags': ''})
        form.revert_field('Tags')
        popup.new_value.setText('New tag')
        popup._new()
        self.assertEqual(form.changes(), {'Tags': 'New tag'})
        popup._clear()
        self.assertEqual(form.changes(), {'Tags': ''})
        popup.close()
