"""PDF-backed archive round trips, exclusive sibling creation and reader commands."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.runtime.resources.local import LocalFiles
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from features.notebooks.recovery import Repository
from features.pdf.annotation import duplicate_pdf, LABEL
from tests.readers.test_pdf_reader import pdf_bytes


class PDFAnnotationTests(QtTestCase):
    def test_sibling_archive_ink_recovery_page_mapping_and_original(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'Paper.PDF'
            original = pdf_bytes()
            source.write_bytes(original)
            provider = LocalFiles(root)
            self.assertEqual(duplicate_pdf(provider, source.name), 'Paper.rmdoc')
            created = root / 'Paper.rmdoc'
            book = Notebook.read(created.read_bytes())
            self.assertEqual(book.members[book.id + '.pdf'], original)
            self.assertEqual(len(book.pages), 3)
            repository = Repository(root / 'recovery')
            key = repository.create(book)
            editor = Editor(book, lambda b: repository.save(key, b))
            self.assertTrue(editor.state()['background'].startswith('data:image/png;base64,'))
            editor.apply(dict(op='stroke', points=[[20, 30, .5], [60, 70, .8]]))
            editor.apply(dict(op='duplicate-page'))
            editor.apply(dict(op='move-page', index=3))
            editor.apply(dict(op='add-page'))
            self.assertIsNone(editor.state()['background'])
            reopened = Notebook.read(book.to_bytes())
            self.assertEqual([p.record['redir']['value'] for p in reopened.pages], [0, 1, 2, 0, -1])
            self.assertEqual(len(reopened.page(3).strokes), 1)
            self.assertEqual(repository.open(key).members[book.id + '.pdf'], original)
            self.assertEqual(source.read_bytes(), original)
            before = created.read_bytes()
            with self.assertRaisesRegex(FileExistsError, 'already exists'):
                duplicate_pdf(provider, source.name)
            self.assertEqual(created.read_bytes(), before)

    def test_competing_destination_is_never_replaced(self):
        from features.pdf.annotation import notebook_from_pdf
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'paper.pdf').write_bytes(pdf_bytes())
            def race(data, name):
                book = notebook_from_pdf(data, name)
                (root / 'paper.rmdoc').write_bytes(b'competing writer')
                return book
            with patch('features.pdf.annotation.notebook_from_pdf', side_effect=race):
                with self.assertRaises((ValueError, FileExistsError)):
                    duplicate_pdf(LocalFiles(root), 'paper.pdf')
            self.assertEqual((root / 'paper.rmdoc').read_bytes(), b'competing writer')

    def test_pdf_background_is_not_dropped_during_cross_notebook_copy(self):
        from features.pdf.annotation import notebook_from_pdf
        book = notebook_from_pdf(pdf_bytes(), 'PDF')
        with self.assertRaisesRegex(ValueError, 'within their notebook'):
            Notebook.new().copy_page(book, 0)

    def test_desktop_reader_overflow_dispatches_annotation_command(self):
        from features.pdf.ui.reader import PDFWindow
        provider = object()
        with patch('features.pdf.ui.annotation.annotate_pdf') as annotate:
            window = PDFWindow('paper.pdf', pdf_bytes(), annotation_provider=provider, annotation_path='paper.pdf')
            self.addCleanup(window.close)
            action, = window.actions_menu.actions()
            self.assertEqual(action.text(), LABEL)
            action.trigger()
            annotate.assert_called_once_with(provider, 'paper.pdf', window)

    def test_desktop_browser_offers_single_pdf_action(self):
        from features.pdf.ui.annotation import annotation_actions
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'paper.pdf'
            path.write_bytes(pdf_bytes())
            context = SimpleNamespace(selection=[SimpleNamespace(path=path)])
            action, = annotation_actions(None, context)
            self.assertEqual(action.title, LABEL)
