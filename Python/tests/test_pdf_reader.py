"""Real PDF decoding, page navigation and provider memory boundaries."""
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from features.pdf.document import PDFDocument, page_index
from services.documents.readers import PrivateReader


def pdf_bytes(texts=None):
    # Small standards-compliant fixture without another PDF runtime dependency.
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 >>']
    texts = texts if texts is not None else ('Alpha needle first needle', 'Beta page', 'Last NEEDLE')
    for index, width in enumerate((300, 400, 500)):
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} 600] /Resources << /Font << /F1 6 0 R >> >> /Contents {7 + index} 0 R >>'.encode())
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    for text in texts:
        content = f'BT /F1 18 Tf 20 500 Td ({text}) Tj ET'.encode()
        objects.append(f'<< /Length {len(content)} >>\nstream\n'.encode() + content + b'\nendstream')
    result = b'%PDF-1.4\n'
    offsets = [0]
    for number, data in enumerate(objects, 1):
        offsets.append(len(result))
        result += f'{number} 0 obj\n'.encode() + data + b'\nendobj\n'
    start = len(result)
    result += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    result += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return result + f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()


class PDFReaderTests(QtTestCase):
    def test_real_pages_from_memory_and_close(self):
        document = PDFDocument(pdf_bytes())
        self.assertEqual(document.count, 3)
        for index in range(3):
            self.assertTrue(document.page(index).startswith(b'\x89PNG'))
        with self.assertRaises(ValueError):
            document.page(3)
        document.close()
        self.assertEqual(document.data, b'')
        with self.assertRaises(ValueError):
            document.page(0)

    def test_invalid_and_oversized_documents(self):
        for data in (b'', b'not a pdf'):
            with self.assertRaises(ValueError):
                PDFDocument(data)
        with patch('features.pdf.document.MAX_PDF', 8):
            with self.assertRaises(ValueError):
                PDFDocument(pdf_bytes())

    def test_provider_reads_bounded_memory_without_filesystem_fallback(self):
        data = pdf_bytes()
        class Provider:
            @contextmanager
            def open(self, name):
                self.limit = None
                provider = self
                class Stream(BytesIO):
                    def read(self, size=-1):
                        provider.limit = size
                        return super().read(size)
                with Stream(data) as stream:
                    yield stream
        provider = Provider()
        reader = PrivateReader('private.pdf', source=provider)
        self.assertEqual(provider.limit, 1024 * 1024)
        self.assertEqual(reader.labels, ['Page 1', 'Page 2', 'Page 3'])
        self.assertFalse(reader.editable)
        self.assertTrue(reader.read_only)
        self.assertEqual(reader.page(2)[0], 'image')

    def test_bounded_reads_support_large_remote_range_sources(self):
        from commonUtils.runtime.range_reader import RangeReader
        from features.pdf.document import read_pdf
        data = b'x' * (17 * 1024 * 1024)
        with RangeReader(len(data), lambda start, count: data[start:start + count],
                         max_read=16 * 1024 * 1024, cache_blocks=1) as stream:
            self.assertEqual(read_pdf(stream), data)
        with patch('features.pdf.document.MAX_PDF', 16):
            with self.assertRaises(ValueError):
                read_pdf(BytesIO(data))

    def test_desktop_private_choice_uses_provider_stream(self):
        from commonUtils.runtime.resource_selection import ResourceChoice
        from services.documents.ui.readers import open_reader_choice
        class Provider:
            root = Path('/virtual-private-pdf')
            private = True
            @contextmanager
            def open(self, path):
                self.opened = path
                with BytesIO(pdf_bytes()) as stream:
                    yield stream
        provider = Provider()
        released = []
        choice = ResourceChoice(provider, 'private.pdf', lambda: released.append(True))
        window = open_reader_choice(choice, None, 'pdf')
        self.assertIsNotNone(window)
        self.assertEqual(provider.opened, provider.root / 'private.pdf')
        window.number.setValue(2)
        self.assertEqual(window.index, 1)
        window.close()
        from commonUtils.ui import pyside as qt
        qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.assertTrue(released)

    def test_page_numbers(self):
        self.assertEqual(page_index(' 3 ', 3), 2)
        for value in ('0', '4', '-1', 'one', '1.5', ''):
            with self.assertRaises(ValueError):
                page_index(value, 3)

    def test_desktop_navigation_and_close_clear_buffer(self):
        from features.pdf.ui.reader import PDFWindow
        from PySide6.QtCore import QPointF, QEvent, Qt
        from PySide6.QtGui import QMouseEvent
        window = PDFWindow('fixture.pdf', pdf_bytes())
        self.assertEqual(window.index, 0)
        window.number.setValue(3)
        self.assertEqual(window.index, 2)
        self.assertFalse(window.following.isEnabled())
        window.go(-1)
        self.assertEqual(window.index, 2)
        for event_type, position in ((QEvent.Type.MouseButtonPress, QPointF(30, 30)),
                                     (QEvent.Type.MouseButtonRelease, QPointF(30, 150))):
            event = QMouseEvent(event_type, position, position, Qt.MouseButton.LeftButton,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            window.eventFilter(window.view.viewport(), event)
        self.assertEqual(window.index, 1)
        window.close()
        self.assertEqual(bytes(window.buffer.data()), b'')

    def test_search_real_pdf_case_insensitive_matches_and_limits(self):
        from features.pdf.search import search_pdf, result_text
        results = search_pdf(pdf_bytes(), 'NEEDLE')
        self.assertEqual([match.page for match in results.matches], [0, 0, 2])
        self.assertIn('Alpha needle', results.matches[0].snippet)
        self.assertIn('Page 3', result_text(results, 2))
        self.assertFalse(results.limited)
        self.assertFalse(search_pdf(pdf_bytes(), 'absent').matches)
        self.assertFalse(search_pdf(pdf_bytes(), '  ').matches)
        with patch('features.pdf.search.MAX_MATCHES', 2):
            limited = search_pdf(pdf_bytes(), 'needle')
        self.assertTrue(limited.limited)
        self.assertEqual(len(limited.matches), 2)
        self.assertFalse(search_pdf(pdf_bytes(('', '', '')), 'needle').matches)
        with self.assertRaises(ValueError):
            search_pdf(pdf_bytes(), 'x' * 257)
        from commonUtils.runtime.operations import OperationCancelled
        with self.assertRaises(OperationCancelled):
            search_pdf(pdf_bytes(), 'needle', cancelled=lambda: True)

    def test_desktop_search_navigates_wraps_and_clears(self):
        from features.pdf.ui.reader import PDFWindow
        window = PDFWindow('search.pdf', pdf_bytes())
        self.assertTrue(window.search.isHidden())
        window.show_find()
        self.assertFalse(window.search.isHidden())
        self.assertTrue(window.find_button.isChecked())
        search = window.search
        search.input.setText('needle')
        search.find(1)
        self.wait_until(lambda: search.future is None)
        self.assertIn('Match 1 of 3', search.status.text())
        search.find(-1)
        self.assertEqual(window.index, 2)
        self.assertIn('Match 3 of 3', search.status.text())
        search.find(1)
        self.assertEqual(window.index, 0)
        search.input.setText('missing')
        search.find(1)
        self.wait_until(lambda: search.future is None)
        self.assertIn('No matches', search.status.text())
        search.input.clear()
        self.assertFalse(search.results.matches)
        self.assertEqual(search.status.text(), '')
        window.close()
        self.assertEqual(search.data, b'')
        self.assertTrue(search.disposed)

    def test_remote_policy(self):
        from features.rclone.remote_policy import direct_kind, LocalCopyRequired
        self.assertEqual(direct_kind('report.PDF', 2048), 'pdf')
        with self.assertRaises(LocalCopyRequired):
            direct_kind('report.pdf', 32 * 1024 * 1024 + 1)

    def test_feature_registration(self):
        from features.pdf import register
        feature = register()
        self.assertEqual(feature.id, 'pdf')
        self.assertEqual(feature.document_launchers[0].editor_id, 'pdf')


if __name__ == '__main__':
    unittest.main()
