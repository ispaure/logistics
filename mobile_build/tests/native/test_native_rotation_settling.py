"""Native rotation auditing tolerates transitions, never persistent overflow."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from unittest.mock import AsyncMock, patch

from mobile_build.native_tests.tests.logisticsmobile import rotation_checks
from commonUtils.testing import waiting


class RotationSettlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_native_morph_is_remeasured_before_acceptance(self):
        with patch.object(rotation_checks, 'assert_visible_controls',
                          side_effect=[AssertionError('button still morphing'), 4]) as audit, \
                patch.object(waiting.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            self.assertEqual(await rotation_checks.settled_visible_controls(object()), 4)
            self.assertEqual(audit.call_count, 2)
            sleep.assert_awaited_once_with(.1)

    async def test_persistent_overflow_still_fails_after_bounded_settling(self):
        with patch.object(rotation_checks, 'assert_visible_controls',
                          side_effect=AssertionError('control outside viewport')) as audit, \
                patch.object(waiting, 'monotonic', side_effect=[0, 1, 2, 2]), \
                patch.object(waiting.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            with self.assertRaisesRegex(AssertionError, 'control outside viewport'):
                await rotation_checks.settled_visible_controls(object())
            self.assertEqual(audit.call_count, 2)
            self.assertEqual(sleep.await_count, 1)
