"""Performance evidence observes blocking without exposing fixture contents."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.EXTENDED
import asyncio
import json
import time
from unittest import IsolatedAsyncioTestCase

from mobile_build.native_tests.tests.logisticsmobile.performance_workloads import measure_operation


class PerformanceWorkloadTests(IsolatedAsyncioTestCase):
    async def test_blocking_callback_is_visible_and_content_is_not_reported(self):
        secret = 'SESSION-ONLY-SENTINEL'
        def operation():
            time.sleep(.035)
            return secret
        result = await measure_operation('synthetic', operation)
        self.assertGreater(result['max_loop_delay_ms'], 15)
        self.assertGreater(result['elapsed_ms'], 30)
        self.assertNotIn(secret, json.dumps(result))

    async def test_yielding_operation_is_awaited(self):
        events = []
        async def operation():
            await asyncio.sleep(.01)
            events.append('finished')
        result = await measure_operation('yielding', operation)
        self.assertEqual(events, ['finished'])
        self.assertGreaterEqual(result['python_peak_bytes'], 0)
