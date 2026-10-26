"""UIKit property and callable getter bindings preserve native transition waits."""
from types import SimpleNamespace as NS
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch
from commonUtils.runtime.platform import OS
from mobile_build.native_tests.tests.logisticsmobile.navigation_checks import wait_for_transitions


class NavigationReadinessTests(IsolatedAsyncioTestCase):
    def app(self, *controllers):
        return NS(native_host=NS(adapter=NS(navigation=list(controllers))), adaptive=NS(secondary=None))

    async def test_callable_getter_is_evaluated_instead_of_treated_as_active(self):
        getter = Mock(return_value=None)
        with patch('mobile_build.native_tests.tests.logisticsmobile.navigation_checks.get_os', return_value=OS.IOS), patch(
                'mobile_build.native_tests.tests.logisticsmobile.navigation_checks.asyncio.sleep', new_callable=AsyncMock):
            await wait_for_transitions(self.app(NS(transitionCoordinator=getter)))
        getter.assert_called_once_with()

    async def test_next_action_waits_for_an_active_coordinator_to_clear(self):
        getter = Mock(side_effect=[object(), None])
        with patch('mobile_build.native_tests.tests.logisticsmobile.navigation_checks.get_os', return_value=OS.IOS), patch(
                'mobile_build.native_tests.tests.logisticsmobile.navigation_checks.asyncio.sleep', new_callable=AsyncMock) as sleep:
            await wait_for_transitions(self.app(NS(transitionCoordinator=None), NS(transitionCoordinator=getter)))
        self.assertEqual(getter.call_count, 2)
        self.assertEqual(sleep.await_count, 2)

    async def test_stalled_transition_remains_a_bounded_failure(self):
        with patch('mobile_build.native_tests.tests.logisticsmobile.navigation_checks.get_os', return_value=OS.IOS), patch(
                'mobile_build.native_tests.tests.logisticsmobile.navigation_checks.asyncio.sleep', new_callable=AsyncMock):
            with self.assertRaisesRegex(RuntimeError, 'did not finish'):
                await wait_for_transitions(self.app(NS(transitionCoordinator=object())))
