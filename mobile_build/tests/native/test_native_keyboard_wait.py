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

    async def test_visible_keyboard_for_unserved_input_does_not_pass(self):
        request = Mock()
        ready = Mock(side_effect=[False, False, True, True, True])
        with patch('mobile_build.native_tests.tests.logisticsmobile.keyboard_wait.asyncio.sleep', new_callable=AsyncMock):
            self.assertTrue(await settled_keyboard(request, lambda: True, ready=ready, attempts=6))
        self.assertEqual(ready.call_count, 5)
        self.assertEqual(request.call_count, 3)

    async def test_unserved_input_exhausts_explicit_budget_even_with_visible_ime(self):
        with patch('mobile_build.native_tests.tests.logisticsmobile.keyboard_wait.asyncio.sleep', new_callable=AsyncMock) as sleep:
            self.assertFalse(await settled_keyboard(Mock(), lambda: True, ready=lambda: False, attempts=60))
        self.assertEqual(sleep.await_count, 60)

    async def test_hidden_keyboard_never_passes_and_wait_is_bounded(self):
        request = Mock()
        with patch('mobile_build.native_tests.tests.logisticsmobile.keyboard_wait.asyncio.sleep', new_callable=AsyncMock) as sleep:
            self.assertFalse(await settled_keyboard(request, lambda: False))
        self.assertEqual(request.call_count, 20)
        self.assertEqual(sleep.await_count, 20)
