"""Native dialog answers preserve presentation, completion and overlay retirement."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace as State
import unittest
from unittest.mock import Mock, patch
from commonUtils.testing.stages import TestStage
from commonUtils.testing.waiting import wait_until
from mobile_build.native_tests.tests.logisticsmobile.dialog_driver import respond_ios_dialog
from mobile_build.native_tests.tests.logisticsmobile.localcrypt_checks import _check_wrong_archive_password
from mobile_build.native_tests.tests.logisticsmobile.timings import SuiteTimings

TEST_STAGE = TestStage.REGRESSION


class NativeDialogDriverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.modules = patch.dict(sys.modules, {'rubicon.objc': State(Block=lambda callback, result: callback)})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def fixture(self, *, presenting=True):
        native = State(presentingViewController=object(), view=State(window=object()),
            isBeingPresented=lambda: presenting, dismissViewControllerAnimated=Mock())
        response = Mock()
        dialog = State(_impl=State(native=native, response=response))
        return dialog, native, response

    async def test_waits_for_presentation_and_dismissal_before_answering(self):
        dialog, native, response = self.fixture()
        native.isBeingPresented = Mock(return_value=True)
        task = asyncio.create_task(respond_ios_dialog(dialog, False))
        await wait_until(lambda: native.isBeingPresented.called, timeout=2, interval=.01,
                         message='Driver did not check presentation state')
        native.dismissViewControllerAnimated.assert_not_called()
        response.assert_not_called()
        native.isBeingPresented.return_value = False
        await wait_until(lambda: native.dismissViewControllerAnimated.called, timeout=2, interval=.01,
                         message='Driver did not request dismissal after presentation finished')
        native.dismissViewControllerAnimated.assert_called_once()
        response.assert_not_called()
        native.presentingViewController = None
        native.view.window = None
        native.dismissViewControllerAnimated.call_args.kwargs['completion']()
        await task
        response.assert_called_once_with(False)

    async def test_completion_alone_does_not_answer_while_overlay_is_attached(self):
        dialog, native, response = self.fixture(presenting=False)
        attachment_checked = asyncio.Event()
        presenter = native.presentingViewController

        def attached_presenter():
            attachment_checked.set()
            return presenter

        def complete_dismissal(animated, completion):
            native.presentingViewController = attached_presenter
            completion()

        native.dismissViewControllerAnimated.side_effect = complete_dismissal
        task = asyncio.create_task(respond_ios_dialog(dialog, True))
        await wait_until(attachment_checked.is_set, timeout=2, interval=.01,
                         message='Driver did not check overlay attachment after dismissal completed')
        response.assert_not_called()
        native.presentingViewController = None
        native.view.window = None
        await task
        response.assert_called_once_with(True)

    async def test_missing_presentation_fails_without_dismissing_or_answering(self):
        dialog, native, response = self.fixture()
        with self.assertRaisesRegex(AssertionError, 'presentation did not finish'):
            await respond_ios_dialog(dialog, None, timeout=.02)
        native.dismissViewControllerAnimated.assert_not_called()
        response.assert_not_called()

    async def test_missing_dismissal_completion_fails_without_answering(self):
        dialog, native, response = self.fixture(presenting=False)
        with self.assertRaisesRegex(AssertionError, 'completion did not arrive'):
            await respond_ios_dialog(dialog, True, timeout=.02)
        response.assert_not_called()

    def password_fixture(self, report, *, presenting=True):
        from commonUtils.archives.zip_access import ArchivePasswordError
        from commonUtils.runtime.platform import OS

        dialog, native, _ = self.fixture(presenting=presenting)
        native.title = 'Could not open document'
        native.message = 'Wrong archive password'
        shown, retired = asyncio.Event(), asyncio.Event()

        class InfoDialog:
            _impl = dialog._impl

        dialog._impl.native = None
        copies = State(open=Mock(side_effect=ArchivePasswordError('Wrong archive password')))
        self.enterContext(patch.dict(sys.modules, {'toga': State(InfoDialog=InfoDialog)}))
        self.enterContext(patch('commonUtils.runtime.platform.get_os', return_value=OS.IOS))

        async def show(dialog):
            answer = asyncio.get_running_loop().create_future()
            dialog._impl.native = native
            dialog._impl.response = answer.set_result
            shown.set()
            try:
                return await answer
            finally:
                retired.set()

        async def open_crypt():
            try:
                await asyncio.to_thread(copies.open)
            except ArchivePasswordError:
                await app.main_window.dialog(InfoDialog())

        app = State(main_window=State(dialog=show), crypt_copies=copies, open_crypt=open_crypt,
                    crypt_password=State(value=''), cloud_status=State(value='Wrong archive password'),
                    provider_sessions=lambda: State(active=None), _native_suite_timings=SuiteTimings(report, emit=Mock()))
        return app, native, shown, retired

    async def test_wrong_password_waits_for_native_presentation_without_fixed_delay(self):
        with TemporaryDirectory() as directory:
            report = Path(directory) / 'timings.json'
            app, native, shown, retired = self.password_fixture(report, presenting=False)

            def dismiss(animated, completion):
                self.assertTrue(shown.is_set())
                native.presentingViewController = None
                native.view.window = None
                completion()

            native.dismissViewControllerAnimated.side_effect = dismiss
            with patch.object(asyncio, 'sleep', wraps=asyncio.sleep) as sleep, \
                    patch.object(asyncio, 'wait_for', wraps=asyncio.wait_for) as wait:
                await _check_wrong_archive_password(app, 'encrypted.cbz')
            row, = json.loads(report.read_text())['records']

        self.assertEqual(wait.await_args_list[0].args[1], 30)
        self.assertTrue(all(call.args[0] != .2 for call in sleep.await_args_list))
        self.assertTrue(retired.is_set())
        native.dismissViewControllerAnimated.assert_called_once()
        self.assertEqual(row['status'], 'ok')
        phases = row['details']['phases_s']
        self.assertEqual(list(phases), ['open_requested', 'acquisition_started', 'archive_password_rejected',
                                       'dialog_entered', 'dialog_presented', 'dialog_answered',
                                       'dialog_task_returned', 'open_returned'])
        self.assertEqual(list(phases.values()), sorted(phases.values()))

    async def test_wrong_password_timeout_keeps_last_phase_and_cancels_modal_task(self):
        wait_for = asyncio.wait_for
        with TemporaryDirectory() as directory:
            report = Path(directory) / 'timings.json'
            app, native, shown, retired = self.password_fixture(report)

            async def cancel_after_dialog_started(operation, timeout):
                self.assertEqual(timeout, 30)
                task = asyncio.create_task(operation)
                try:
                    await wait_for(shown.wait(), 2)
                finally:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                raise TimeoutError()

            with patch.object(asyncio, 'wait_for', side_effect=cancel_after_dialog_started):
                with self.assertRaises(TimeoutError):
                    await _check_wrong_archive_password(app, 'encrypted.cbz')
            row, = json.loads(report.read_text())['records']

        self.assertTrue(retired.is_set())
        native.dismissViewControllerAnimated.assert_not_called()
        self.assertEqual(row['status'], 'TimeoutError')
        self.assertEqual(list(row['details']['phases_s']),
                         ['open_requested', 'acquisition_started', 'archive_password_rejected', 'dialog_entered'])
