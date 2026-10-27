"""A transient IME acknowledgement is insufficient; permanent absence fails."""
import unittest
from unittest.mock import AsyncMock, Mock, patch
from mobile_build.native_tests.tests.logisticsmobile.keyboard_wait import settled_keyboard


class NativeKeyboardWaitTests(unittest.IsolatedAsyncioTestCase):
    async def test_animation_hide_restarts_stability_before_acceptance(self):
        request = Mock()
        visible = Mock(side_effect=[True, False, True, True, True])
        with patch('mobile_build.native_tests.tests.logisticsmobile.keyboard_wait.asyncio.sleep', new_callable=AsyncMock) as sleep:
            self.assertTrue(await settled_keyboard(request, visible))
        self.assertEqual(visible.call_count, 5)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(sleep.await_count, 5)

    async def test_hidden_keyboard_never_passes_and_wait_is_bounded(self):
        request = Mock()
        with patch('mobile_build.native_tests.tests.logisticsmobile.keyboard_wait.asyncio.sleep', new_callable=AsyncMock) as sleep:
            self.assertFalse(await settled_keyboard(request, lambda: False))
        self.assertEqual(request.call_count, 20)
        self.assertEqual(sleep.await_count, 20)
