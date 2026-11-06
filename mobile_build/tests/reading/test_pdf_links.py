"""Finger link dispatch, spread geometry, undo and retained-session retirement."""
import asyncio
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage
from mobile.app import LogisticsMobile
from mobile_build.tests.support.pdf import PDF, native_pdf

TEST_STAGE = TestStage.REGRESSION


def linked_pdf():
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import Link
    writer = PdfWriter(clone_from=PdfReader(BytesIO(PDF)))
    writer.add_annotation(0, Link(rect=(30, 420, 150, 540), target_page_index=2))
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


class PDFMobileLinkTests(unittest.TestCase):
    @patch('features.pdf.links.safe_page_links', side_effect=lambda data, index: [index])
    @patch('features.images.validation.image_dimensions', side_effect=lambda page: page)
    def test_only_committed_spreads_replace_link_geometry(self, dimensions, links):
        from features.pdf.mobile.canvas import PDFNavigation

        for action in ('failed load', 'back probe', 'uncommitted resize'):
            with self.subTest(action=action):
                document = SimpleNamespace(data=b'', count=5, page=lambda index: (300, 600))
                navigation = PDFNavigation(document)
                viewport = (1200, 800)
                indices, _ = navigation.load(2, viewport)
                navigation.commit(indices, viewport)
                shown_sizes = {index: navigation.sizes[index] for index in indices}
                shown_links = dict(navigation.links)
                if action == 'failed load':
                    def page(index):
                        if index == 1:
                            raise OSError('Cannot read second page')
                        return (300, 600)
                    document.page = page
                    with self.assertRaisesRegex(OSError, 'Cannot read second page'):
                        navigation.load(0, viewport)
                elif action == 'back probe':
                    self.assertEqual(navigation.previous(), 0)
                else:
                    document.page = lambda index: (600, 1200)
                    navigation.load(2, (600, 1000))

                self.assertEqual(navigation.indices, indices)
                self.assertEqual(navigation.viewport, viewport)
                self.assertEqual(navigation.links, shown_links)
                self.assertEqual({index: navigation.sizes[index] for index in indices}, shown_sizes)

                document.page = lambda index: (400, 800)
                next_indices, _ = navigation.load(0, viewport)
                navigation.commit(next_indices, viewport)
                self.assertEqual(navigation.links, {0: [0], 1: [1]})
                self.assertEqual(navigation.sizes[0], (400, 800))

    def test_link_undo_expiry_and_retired_session(self):
        with TemporaryDirectory() as directory, patch('features.pdf.document.PDFDocument.open', native_pdf):
            previous_root = LogisticsMobile.storage_root
            LogisticsMobile.storage_root = Path(directory)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            path = Path(directory) / 'links.pdf'
            path.write_bytes(linked_pdf())
            async def check():
                self.assertTrue(await app.open_download(path=path))
                owner = app.private_sessions.active
                canvas = owner.crypt_image
                await canvas.jump_link(2)
                self.assertEqual(owner.crypt_reader.pdf_navigation.indices[0], 2)
                self.assertEqual(canvas.return_page, (0, 2))
                self.assertEqual(len(canvas.return_box.children), 1)
                await canvas.undo_link()
                self.assertEqual(owner.crypt_reader.pdf_navigation.indices[0], 0)
                self.assertIsNone(canvas.return_page)
                # Dispatch through the same normalized callback used by native taps.
                nav = owner.crypt_reader.pdf_navigation
                from features.comics.mobile.composite import spread_geometry
                size, rects = spread_geometry([nav.sizes[i] for i in nav.indices], nav.viewport)
                left, top, width, height = rects[0]
                old_image = canvas.image
                old_indices = nav.indices
                from mobile.reading.publication import ReadingPublication
                mount = ReadingPublication.mount
                rejected = []

                def reject_candidate(publication, surface, **kwargs):
                    publication.current = lambda: False
                    rejected.append(mount(publication, surface, **kwargs))
                    return rejected[-1]

                with patch.object(ReadingPublication, 'mount', reject_candidate):
                    await owner.move_private_page(1)
                self.assertEqual(rejected, [False])
                self.assertIn(canvas, owner.crypt_content.children)
                self.assertEqual(nav.indices, old_indices)
                retained_image = canvas.image
                self.assertTrue(canvas.on_tap((left+width*.3)/size[0], (top+height*.2)/size[1]))
                while not canvas.return_page:
                    await asyncio.sleep(.01)
                self.assertEqual(owner.crypt_reader.pdf_navigation.indices[0], 2)
                self.assertIs(retained_image, old_image)
                await owner.move_private_page(1)
                self.assertIsNone(canvas.return_page)
                await canvas.jump_link(0)
                self.assertIsNotNone(canvas.return_page)
                canvas.clear_return()  # timer invokes this exact expiry callback
                await canvas.undo_link()
                self.assertEqual(owner.crypt_reader.pdf_navigation.indices[0], 0)
                owner.set_cloud_busy(True)
                self.assertFalse(canvas.follow_link(.3,.2))
                owner.set_cloud_busy(False)
                app.show_settings()
                await canvas.jump_link(2)
                self.assertEqual(owner.crypt_reader.pdf_navigation.indices[0], 0)
                self.assertFalse(canvas.follow_link(.3,.2))
                canvas.dispose()
                self.assertIsNone(canvas.on_tap)
                self.assertFalse(canvas.link_alive())
            try:
                app.loop.run_until_complete(asyncio.wait_for(check(), 10))
            finally:
                app.main_window.close()
                close_loop(app.loop)
                LogisticsMobile.storage_root = previous_root
