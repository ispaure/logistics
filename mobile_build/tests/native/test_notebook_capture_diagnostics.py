"""A failed synthetic PDF capture keeps its original pixel decision and evidence."""
import asyncio
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock

from commonUtils.testing.stages import TestStage
from mobile_build.native_tests.tests.logisticsmobile.notebook_image_checks import ImageWorkflow, write_capture_diagnostic

TEST_STAGE = TestStage.REGRESSION
BAD = dict(width=401, height=320, pixels=[[255,255,255,255],[20,190,60,255],[0,0,0,255],[0,0,0,0]])
GOOD = dict(width=400, height=320, pixels=[[230,76,38,255],[20,190,60,255],[0,0,0,255],[0,0,0,0]])


class CaptureDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_pixel_is_not_retried_or_replaced_by_later_decode(self):
        saved = Mock()
        capture = AsyncMock()
        workflow = ImageWorkflow(AsyncMock(), lambda:None, capture, diagnostic=saved)
        snapshot = dict(latched_clip=BAD, decode_at_latch=dict(settled=False))
        workflow.js = AsyncMock(side_effect=[snapshot, dict(settled=True, ready=True)])
        with self.assertRaises(AssertionError) as caught:
            await workflow.verify_capture(BAD)
        self.assertEqual(caught.exception.args, (BAD,))
        capture.assert_awaited_once_with('capture-failure')
        self.assertEqual(workflow.js.await_count, 2)
        saved.assert_called_once_with(snapshot)
        self.assertTrue(snapshot['decode_after_capture']['ready'])

    async def test_valid_pixels_do_not_launch_extra_capture_or_decode(self):
        workflow = ImageWorkflow(AsyncMock(), lambda:None, AsyncMock(), diagnostic=Mock())
        workflow.js = AsyncMock()
        await workflow.verify_capture(GOOD)
        workflow.js.assert_not_awaited()
        workflow.capture.assert_not_awaited()
        workflow.diagnostic.assert_not_called()

    async def test_diagnostic_failure_or_cancellation_cannot_mask_primary_pixel_error(self):
        for error in (OSError('evidence failed'), asyncio.CancelledError()):
            workflow = ImageWorkflow(AsyncMock(), lambda:None, AsyncMock())
            workflow.js = AsyncMock(side_effect=error)
            with self.assertRaises(AssertionError) as caught:
                await workflow.verify_capture(BAD)
            self.assertEqual(caught.exception.args, (BAD,))
            self.assertIn(type(error).__name__, caught.exception.__notes__[0])


class CaptureEvidenceWriterTests(unittest.TestCase):
    def test_original_current_clipboard_bytes_and_hashes_are_separate_from_json(self):
        import json
        from hashlib import sha256
        png = b'\x89PNG\r\n\x1a\nsynthetic-fixture'
        source = 'data:image/png;base64,' + base64.b64encode(png).decode()
        with TemporaryDirectory() as directory:
            output = Path(directory)
            snapshot = dict(clip_roi=[[99,100],[500,100],[500,420],[99,420]],
                naturalWidth=960,naturalHeight=960,complete=True,pdf_paper=None,width=1404,height=1872,
                direct_background_sample=[255,255,255,255],latched_clip=BAD,
                sources=dict(original=source,current=source,clipboard=source))
            write_capture_diagnostic(output,'LocalCrypt',snapshot)
            for name in ('original','current','clipboard'):
                self.assertEqual((output / ('LocalCrypt-capture-failure-'+name+'.png')).read_bytes(), png)
            metadata = json.loads((output/'LocalCrypt-capture-failure.json').read_text())
            self.assertNotIn('sources',metadata)
            self.assertNotIn('base64',json.dumps(metadata))
            self.assertEqual(metadata['source_hashes']['current']['src_sha256'],sha256(source.encode()).hexdigest())
            self.assertEqual(metadata['latched_clip'],BAD)

    def test_unrecognized_provider_or_non_png_data_cannot_publish_arbitrary_evidence(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                write_capture_diagnostic(Path(directory),'../outside',{})
            source = 'data:image/png;base64,' + base64.b64encode(b'not PNG').decode()
            with self.assertRaisesRegex(ValueError,'PNG signature'):
                write_capture_diagnostic(Path(directory),'Local',dict(sources={name:source for name in ('original','current','clipboard')}))
