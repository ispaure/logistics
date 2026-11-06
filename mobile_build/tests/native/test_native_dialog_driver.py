"""Native dialog answers preserve presentation, completion and overlay retirement."""
import asyncio
import sys
from types import SimpleNamespace as State
import unittest
from unittest.mock import Mock, patch
from commonUtils.testing.stages import TestStage
from commonUtils.testing.waiting import wait_until
from mobile_build.native_tests.tests.logisticsmobile.dialog_driver import respond_ios_dialog

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
