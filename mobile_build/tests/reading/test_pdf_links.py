"""Finger link dispatch, undo and retained-session retirement."""
import asyncio
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
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
                # A reader progress write owns the document without setting
                # cloud_busy. The accepted link must wait before selecting.
                release_progress = asyncio.Event()
                progress = owner._provider_progress
                async def save_progress():
                    await release_progress.wait()
                    progress.worker = None

                with patch.object(progress, 'worker', None), patch.object(progress, 'task', None):
                    progress.worker = progress.task = asyncio.create_task(save_progress())
                    link = asyncio.create_task(canvas.jump_link(2, 0))
                    try:
                        await asyncio.sleep(0)
                        self.assertFalse(link.done())
                        self.assertFalse(owner.cloud_busy)
                        self.assertFalse(owner.provider_document().can_start())
                        self.assertEqual(owner.crypt_page.value, owner.crypt_reader.labels[0])
                    finally:
                        release_progress.set()
                    await link
                self.assertEqual(owner.crypt_reader.pdf_navigation.index, 2)
                self.assertEqual(canvas.return_page, (0, 2))
                self.assertEqual(len(canvas.return_box.children), 1)
                await canvas.undo_link()
                self.assertEqual(owner.crypt_reader.pdf_navigation.index, 0)
                self.assertIsNone(canvas.return_page)
                # Dispatch through the same normalized callback used by native taps.
                nav = owner.crypt_reader.pdf_navigation
                old_image = canvas.image
                old_index = nav.index
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
                self.assertEqual(nav.index, old_index)
                retained_image = canvas.image
                [link] = canvas.scroll.pages[0][1]
                canvas.action({'target': link['index'], 'from': 0})
                while not canvas.return_page:
                    await asyncio.sleep(.01)
                self.assertEqual(owner.crypt_reader.pdf_navigation.index, 2)
                self.assertIs(retained_image, old_image)
                await owner.move_private_page(1)
                self.assertIsNone(canvas.return_page)
                await canvas.jump_link(0, 1)
                self.assertIsNotNone(canvas.return_page)
                canvas.clear_return()  # timer invokes this exact expiry callback
                await canvas.undo_link()
                self.assertEqual(owner.crypt_reader.pdf_navigation.index, 0)
                owner.set_cloud_busy(True)
                await canvas.jump_link(2, 0)
                owner.set_cloud_busy(False)
                app.show_settings()
                await canvas.jump_link(2, 0)
                self.assertEqual(owner.crypt_reader.pdf_navigation.index, 0)
                canvas.dispose()
                self.assertIsNone(canvas.scroll.on_action)
                self.assertFalse(canvas.active())
            try:
                app.loop.run_until_complete(asyncio.wait_for(check(), 10))
            finally:
                app.main_window.close()
                close_loop(app.loop)
                LogisticsMobile.storage_root = previous_root
