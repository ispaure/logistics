"""Metadata edits must preserve pages, extensions and the original on failure."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
from xml.etree import ElementTree as ET
from features.comics.comicinfo import ComicInfoXML
from features.comics.library import ComicDocument


class ComicFixture:
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'comic.cbz'

    def archive(self, xml=b'<ComicInfo><Writer>Old</Writer><Pages><Page Image="0" Bookmark="Keep"/></Pages></ComicInfo>'):
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.comment = b'archive comment'
            archive.writestr('01.png', b'original image bytes', compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr('notes.txt', b'keep me')
            if xml is not None:
                archive.writestr('ComicInfo.xml', xml)



class MetadataTests(ComicFixture, unittest.TestCase):
    def test_metadata_round_trip_preserves_unknowns_comments_pages_and_unicode(self):
        xml = ('<ComicInfo xmlns="urn:comic"><!--keep--><?keep yes?>'
               '<Custom flag="yes">extra</Custom><Notes>a&#13;b\u2028c</Notes>'
               '<PageCount>1</PageCount><Pages><Page Image="0" Bookmark="Keep"/></Pages></ComicInfo>').encode()
        self.archive(xml)
        document = ComicDocument(self.path)
        document.save({'Writer': 'Été & <friends>', 'Summary': 'first\nsecond'})
        with zipfile.ZipFile(self.path) as archive:
            self.assertEqual(archive.read('01.png'), b'original image bytes')
            self.assertEqual(archive.read('notes.txt'), b'keep me')
            self.assertEqual(archive.comment, b'archive comment')
            data = archive.read('ComicInfo.xml')
            root = ET.fromstring(data)
            ns = '{urn:comic}'
            self.assertEqual(root.findtext(ns+'Writer'), 'Été & <friends>')
            self.assertEqual(root.findtext(ns+'Notes'), 'a\rb\u2028c')
            self.assertEqual(root.find(ns+'Pages/'+ns+'Page').get('Bookmark'), 'Keep')
            self.assertEqual(root.find(ns+'Custom').get('flag'), 'yes')
            self.assertIn(b'<!--keep-->', data)
            self.assertIn(b'<?keep yes?>', data)

    def test_properties_noop_and_remove(self):
        info = ComicInfoXML.from_bytes(b'<ComicInfo><Writer>A</Writer></ComicInfo>')
        self.assertEqual(info.writer, 'A')
        self.assertEqual(info.to_bytes(), b'<ComicInfo><Writer>A</Writer></ComicInfo>')
        info.writer = ''
        info.series = 'B'
        self.assertIsNone(ET.fromstring(info.to_bytes()).find('Writer'))
        self.assertEqual(info.series, 'B')
        with self.assertRaises(ValueError):
            info.page_count = '9'

    def test_create_metadata_and_noop(self):
        self.archive(None)
        document = ComicDocument(self.path)
        before = self.path.read_bytes()
        document.save({})
        self.assertEqual(self.path.read_bytes(), before)
        document.save({'Title': 'New'})
        self.assertEqual(ComicDocument(self.path).info.title, 'New')

    def test_concurrent_change_and_failed_replace_preserve_original(self):
        self.archive()
        document = ComicDocument(self.path)
        before = self.path.read_bytes()
        with patch('features.comics.library.os.replace', side_effect=OSError('failed')):
            with self.assertRaises(OSError):
                document.save({'Writer': 'New'})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(document.info.writer, 'Old')
        self.path.write_bytes(b'another operation')
        with self.assertRaises(RuntimeError):
            document.save({'Writer': 'New'})
        self.assertEqual(self.path.read_bytes(), b'another operation')

    def test_invalid_xml_and_duplicate_metadata_are_rejected(self):
        for xml in (b'<Other/>', b'<ComicInfo>', b'<ComicInfo><Writer>A</Writer><Writer>B</Writer></ComicInfo>'):
            self.archive(xml)
            before = self.path.read_bytes()
            with self.assertRaises((ValueError, ET.ParseError)):
                ComicDocument(self.path).info.metadata
            self.assertEqual(self.path.read_bytes(), before)
        self.archive()
        with zipfile.ZipFile(self.path, 'a') as archive:
            archive.writestr('nested/ComicInfo.xml', b'<ComicInfo/>')
        with self.assertRaises(ValueError):
            ComicDocument(self.path)

    def test_illegal_xml_characters_do_not_replace_archive(self):
        self.archive()
        before = self.path.read_bytes()
        with self.assertRaises(ET.ParseError):
            ComicDocument(self.path).save({'Title': '\x00'})
        self.assertEqual(self.path.read_bytes(), before)


class WindowTests(ComicFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        from commonUtils.ui import pyside as qt
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def wait_for(self, target):
        import time
        deadline = time.monotonic() + 5
        while target.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertFalse(target.busy, 'Background operation did not finish')

    def test_window_load_edit_save(self):
        from commonUtils.ui import pyside as qt
        from features.comics.ui.library import ComicLibraryWindow
        app = self.app
        self.archive()
        window = ComicLibraryWindow(self.path.parent)
        window._load(self.path)
        self.wait_for(window)
        self.assertTrue(window.preview.isReadOnly())
        self.assertIn('Writer: Old', window.preview.toPlainText())
        index = window.model.index(str(self.path))
        menu = window._context_menu_for(index)
        self.assertEqual(menu.actions()[0].text(), 'Edit Metadata')
        menu.actions()[0].trigger()
        editor = window.metadata_windows[0]
        self.wait_for(editor)
        self.assertEqual(editor.tabs.count(), 2)
        self.assertEqual(editor.tabs.tabText(0), 'Details')
        self.assertEqual(editor.tabs.tabText(1), 'Plot && Notes')
        self.assertFalse(editor.apply_button.isEnabled())
        editor.editors['Writer'].setText('New & writer')
        self.assertTrue(editor.apply_button.isEnabled())
        editor._save()
        self.wait_for(editor)
        self.wait_for(window)
        self.assertEqual(ComicDocument(self.path).info.writer, 'New & writer')
        self.assertFalse(editor.apply_button.isEnabled())
        editor.reject()
        window.close()
        app.processEvents()

    def test_cancel_apply_navigation_and_ok(self):
        from commonUtils.ui import pyside as qt
        from features.comics.ui.metadata_editor import MetadataEditor
        app = self.app
        self.archive()
        second = self.path.with_name('second.cbz')
        second.write_bytes(self.path.read_bytes())
        editor = MetadataEditor(self.path, [self.path, second])
        editor.show()
        self.wait_for(editor)
        before = self.path.read_bytes()
        editor.editors['Writer'].setText('Unsaved')
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
            editor._navigate(1)
        self.assertEqual(editor.path, self.path)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
            editor._navigate(1)
        self.wait_for(editor)
        self.assertEqual(editor.path, second)
        self.assertEqual(self.path.read_bytes(), before)
        editor.editors['Writer'].setText('Saved')
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Save):
            editor._navigate(-1)
        self.wait_for(editor)
        self.assertEqual(editor.path, self.path)
        self.assertEqual(ComicDocument(second).info.writer, 'Saved')
        editor.editors['Writer'].setText('OK saved')
        editor._ok()
        self.wait_for(editor)
        self.assertEqual(ComicDocument(self.path).info.writer, 'OK saved')
        self.assertFalse(editor.isVisible())
        app.processEvents()

    def test_combo_mapping_unknown_values_and_hidden_fields(self):
        from features.comics.ui.metadata_widgets import editor_value
        from commonUtils.ui import pyside as qt
        from features.comics.ui.metadata_editor import MetadataEditor
        app = self.app
        xml = ('<ComicInfo><LanguageISO>zh-Hant</LanguageISO><Manga>legacy</Manga>'
               '<Summary>a&#13;b\u2028c</Summary><GTIN>123456</GTIN>'
               '<Translator>Hidden translator</Translator><Future><Nested x="1"/></Future>'
               '<SeriesComplete>Yes</SeriesComplete><EnableProposed>true</EnableProposed></ComicInfo>').encode()
        self.archive(xml)
        editor = MetadataEditor(self.path)
        self.wait_for(editor)
        self.assertFalse(editor._changes())
        self.assertEqual(editor_value(editor.editors['LanguageISO']), 'zh-Hant')
        language = editor.editors['LanguageISO']
        language.setCurrentIndex(language.findData('fr'))
        manga = editor.editors['Manga']
        manga.setCurrentIndex(manga.findData('YesAndRightToLeft'))
        editor.editors['Writer'].setText('Author')
        editor._save()
        self.wait_for(editor)
        doc = ComicDocument(self.path)
        self.assertEqual(doc.info.language_iso, 'fr')
        self.assertEqual(doc.info.manga, 'YesAndRightToLeft')
        self.assertEqual(doc.info.summary, 'a\rb\u2028c')
        self.assertEqual(doc.info.gtin, '123456')
        root = ET.fromstring(doc.info.to_bytes())
        self.assertEqual(root.find('Future/Nested').get('x'), '1')
        self.assertEqual(root.findtext('SeriesComplete'), 'Yes')
        self.assertEqual(root.findtext('EnableProposed'), 'true')
        editor.reject()
        app.processEvents()

    def test_failed_ok_save_keeps_dialog_and_edits(self):
        from commonUtils.ui import pyside as qt
        from features.comics.ui.metadata_editor import MetadataEditor
        app = self.app
        self.archive()
        before = self.path.read_bytes()
        editor = MetadataEditor(self.path)
        editor.show()
        self.wait_for(editor)
        editor.editors['Writer'].setText('Keep unsaved')
        with patch('features.comics.library.os.replace', side_effect=OSError('simulated failure')), \
                patch.object(qt.QMessageBox, 'warning') as warning:
            editor._ok()
            self.wait_for(editor)
            warning.assert_called_once()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(editor.isVisible())
        self.assertEqual(editor.editors['Writer'].text(), 'Keep unsaved')
        self.assertTrue(editor.apply_button.isEnabled())
        self.assertIsNone(editor.pending_action)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
            editor.reject()
        app.processEvents()

    def test_numeric_controls_reject_text_and_preserve_missing_and_legacy_values(self):
        from features.comics.ui.metadata_widgets import editor_value
        from commonUtils.ui import pyside as qt
        from PySide6.QtTest import QTest
        from features.comics.ui.metadata_editor import MetadataEditor
        from features.comics.ui.metadata_widgets import OptionalIntegerSpinBox, IssueNumberSpinBox
        app = self.app
        self.archive(b'<ComicInfo><Volume>-1</Volume><Month>legacy</Month><Number>1A</Number></ComicInfo>')
        editor = MetadataEditor(self.path)
        self.wait_for(editor)
        self.assertEqual(editor.size(), qt.QSize(789, 635))
        self.assertEqual(editor.ok_button.size(), qt.QSize(105, 28))
        self.assertFalse(editor._changes())
        for field in ComicInfoXML.INTEGER_FIELDS:
            self.assertIsInstance(editor.editors[field], OptionalIntegerSpinBox)
            state, _, _ = editor.editors[field].validate('letters', 7)
            self.assertEqual(state, qt.QValidator.State.Invalid)
        count = editor.editors['Count']
        self.assertEqual(count.metadata_value(), '')
        count.stepUp()
        self.assertEqual(count.metadata_value(), '1')
        self.assertTrue(editor.apply_button.isEnabled())
        self.assertIsInstance(editor.editors['Number'], IssueNumberSpinBox)
        self.assertEqual(editor_value(editor.editors['Number']), '1A')
        issue = editor.editors['AlternateNumber']
        issue.setText('0.5')
        issue.stepUp()
        self.assertEqual(issue.text(), '1.5')
        count.lineEdit().selectAll()
        QTest.keyClick(count.lineEdit(), qt.Qt.Key.Key_Backspace)
        QTest.keyClicks(count.lineEdit(), 'abc')
        self.assertEqual(count.metadata_value(), '')
        QTest.keyClicks(count.lineEdit(), '23')
        self.assertEqual(count.metadata_value(), '23')
        editor._save()
        self.wait_for(editor)
        info = ComicDocument(self.path).info
        self.assertEqual(info.count, '23')
        self.assertEqual(info.volume, '-1')
        self.assertEqual(info.month, 'legacy')
        self.assertEqual(info.number, '1A')
        self.assertEqual(info.alternate_number, '1.5')
        count.lineEdit().selectAll()
        QTest.keyClick(count.lineEdit(), qt.Qt.Key.Key_Backspace)
        editor._save()
        self.wait_for(editor)
        self.assertEqual(ComicDocument(self.path).info.count, '')
        editor.reject()
        app.processEvents()


class GenericXMLTests(unittest.TestCase):
    def test_full_document_and_namespace_extensions_are_preserved(self):
        from commonUtils.fileTypes.xmlType import XMLFile
        data = (b'<?xml version="1.0"?><!--before--><?before yes?>'
                b'<c:Record xmlns:c="urn:root" xmlns:x="urn:extra" xmlns:unused="urn:unused" '
                b'x:kind="unused:Type"><c:Title keep="yes">Old</c:Title>'
                b'<x:Title>Extension title</x:Title><x:Data a="b"><x:Child/>Tail</x:Data>'
                b'<!--inside--></c:Record><?after yes?><!--after-->')
        document = XMLFile.from_bytes(data)
        self.assertEqual(document.to_bytes(), data)
        document.set_text('Title', 'New & <title>')
        document.set_text('Added', 'New')
        result = document.to_bytes()
        root = ET.fromstring(result)
        self.assertEqual(root.findtext('{urn:root}Title'), 'New & <title>')
        self.assertEqual(root.find('{urn:root}Title').get('keep'), 'yes')
        self.assertEqual(root.findtext('{urn:extra}Title'), 'Extension title')
        self.assertEqual(root.findtext('{urn:root}Added'), 'New')
        self.assertEqual(root.find('{urn:extra}Data').get('a'), 'b')
        self.assertEqual(root.find('{urn:extra}Data/{urn:extra}Child').tail, 'Tail')
        for preserved in (b'<!--before-->', b'<?before yes?>', b'<!--inside-->',
                          b'<?after yes?>', b'<!--after-->', b'xmlns:unused="urn:unused"'):
            self.assertIn(preserved, result)

    def test_generic_file_loading_is_separate_from_lines(self):
        from commonUtils.fileTypes.xmlType import XMLFile
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'record.xml'
            path.write_text('<Record><Title>Old</Title></Record>')
            document = XMLFile(path)
            document.line_lst = ['untouched']
            self.assertEqual(document.read_xml().localName, 'Record')
            document.set_text('Title', 'New')
            self.assertEqual(document.line_lst, ['untouched'])
            self.assertEqual(document.get_text('Title'), 'New')
            self.assertEqual(path.read_text(), '<Record><Title>Old</Title></Record>')

    def test_comic_schema_types_validate_only_changed_fields(self):
        document = ComicInfoXML.from_bytes(b'<ComicInfo><Month>legacy</Month></ComicInfo>')
        document.writer = 'New writer'
        self.assertEqual(document.get_field('Month'), 'legacy')
        document.number = '1A'
        document.alternate_number = '0.5'
        for field, value in (('Month', '13'), ('Day', '32'), ('Volume', '1.5'), ('Manga', 'true')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                document.set_field(field, value)
        document.month = ''
        self.assertEqual(document.month, '')

    def test_direct_dom_changes_are_serialized(self):
        from commonUtils.fileTypes.xmlType import XMLFile
        document = XMLFile.from_bytes(b'<Root><Item>Old</Item></Root>')
        document.xml_root.setAttribute('added', 'yes')
        self.assertEqual(ET.fromstring(document.to_bytes()).get('added'), 'yes')

    def test_new_comic_fields_follow_schema_order_without_moving_extensions(self):
        document = ComicInfoXML.from_bytes(b'<ComicInfo><Series>S</Series><Custom x="yes"/>'
                                          b'<Pages><Page Image="0"/></Pages></ComicInfo>')
        document.writer = 'W'
        document.title = 'T'
        document.publisher = 'P'
        root = ET.fromstring(document.to_bytes())
        self.assertEqual([node.tag for node in root], ['Title', 'Series', 'Custom', 'Writer', 'Publisher', 'Pages'])
        self.assertEqual(root.find('Custom').get('x'), 'yes')
