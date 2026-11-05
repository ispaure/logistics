"""Failure safety of the normal native PDF acceptance driver, without a device."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


def driver():
    root = Path(__file__).resolve().parents[3]
    path = root / 'mobile_build/native_tests/tests/logisticsmobile/native_pdf_edge_checks.py'
    spec = importlib.util.spec_from_file_location('native_pdf_edge_guard_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cleanup_fixture(fail):
    calls, proof = [], {}
    app = SimpleNamespace(editor_view=SimpleNamespace(session=SimpleNamespace(id='pdf')))
    canvas = SimpleNamespace(return_timer=object() if fail else None,
        on_tap=object() if fail else None,
        _impl=SimpleNamespace(listener=object() if fail else None))
    def clear():
        calls.append('clear')
        if fail:
            raise ValueError('clear failed')
    def close(key):
        calls.append('close')
        return not fail
    def restore():
        calls.append('restore')
        app.editor_view.session.id = 'original'
    def show():
        calls.append('show')
        if fail:
            raise ValueError('show failed')
    app.close_session = close
    app.session_opener = lambda key: restore
    app.show_documents = show
    owner = SimpleNamespace(session=SimpleNamespace(id='pdf'), clear_private_reader=clear)
    path = SimpleNamespace(unlink=lambda **kwargs: calls.append('unlink'))
    return app, owner, canvas, path, proof, calls


class NativePDFCleanupTests(unittest.TestCase):
    def test_primary_error_identity_survives_all_cleanup_failures(self):
        app, owner, canvas, path, proof, calls = cleanup_fixture(True)
        primary = AssertionError('PRIMARY native failure')
        with self.assertRaises(AssertionError) as caught:
            try:
                raise primary
            except BaseException as error:
                driver().cleanup_pdf_fixture(app, owner, canvas, path, 'original', proof, error)
                raise
        self.assertIs(caught.exception, primary)
        self.assertIn('PDF cleanup', primary.__notes__[0])
        self.assertEqual(calls, ['clear', 'close', 'unlink', 'restore', 'show'])
        self.assertTrue(proof['original_session_restored'])
        self.assertEqual(len(proof['cleanup_errors']), 4)

    def test_cleanup_only_failure_raises_after_all_actions(self):
        app, owner, canvas, path, proof, calls = cleanup_fixture(True)
        with self.assertRaisesRegex(AssertionError, 'PDF cleanup'):
            driver().cleanup_pdf_fixture(app, owner, canvas, path, 'original', proof, None)
        self.assertEqual(calls, ['clear', 'close', 'unlink', 'restore', 'show'])
        self.assertTrue(proof['original_session_restored'])

    def test_success_records_callback_retirement_and_session_restoration(self):
        app, owner, canvas, path, proof, calls = cleanup_fixture(False)
        driver().cleanup_pdf_fixture(app, owner, canvas, path, 'original', proof, None)
        self.assertTrue(proof['callbacks_retired'])
        self.assertTrue(proof['original_session_restored'])
        self.assertEqual(proof['cleanup_errors'], [])


class NativePDFQueuedNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_queued_jump_outliving_old_delay_is_drained_before_rejection(self):
        owner = SimpleNamespace(cloud_busy=False,
            crypt_reader=SimpleNamespace(pdf_navigation=SimpleNamespace(
                viewport=(400, 600), indices=(0,))))
        class Canvas:
            async def jump_link(self):
                await asyncio.sleep(.12)
                owner.cloud_busy = True
                await asyncio.sleep(.08)
                owner.crypt_reader.pdf_navigation.indices = (2,)
                owner.cloud_busy = False
        canvas = Canvas()
        task = asyncio.create_task(canvas.jump_link())
        self.addAsyncCleanup(self.retire_task, task)
        await asyncio.sleep(.08)
        self.assertEqual(owner.crypt_reader.pdf_navigation.indices, (0,))
        self.assertFalse(task.done())
        await driver().wait_pdf_idle(owner, canvas, lambda reader: (400, 600))
        self.assertTrue(task.done())
        self.assertEqual(owner.crypt_reader.pdf_navigation.indices, (2,))
        # A delayed wrong navigation must now fail the native rejection check.
        with self.assertRaises(AssertionError):
            self.assertEqual(owner.crypt_reader.pdf_navigation.indices[0], 0)

    async def retire_task(self, task):
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
