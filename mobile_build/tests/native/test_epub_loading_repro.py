"""The diagnostic's passive observer only evaluates after native load events."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from mobile_build.native_tests.tests.logisticsmobile.epub_loading_repro import passive_text


class PassiveObservationTests(unittest.TestCase):
    def test_no_load_event_means_no_javascript_polling(self):
        async def exercise():
            view = SimpleNamespace(_repro_load_count=0, _repro_loaded=asyncio.Event(), evaluate_javascript=AsyncMock())
            with self.assertRaises(TimeoutError):
                await passive_text(view, 'second', .01, 0)
            view.evaluate_javascript.assert_not_awaited()
        asyncio.run(exercise())

    def test_one_native_event_reads_the_document_once(self):
        async def exercise():
            view = SimpleNamespace(_repro_load_count=1, _repro_loaded=asyncio.Event(), evaluate_javascript=AsyncMock(return_value='second'))
            self.assertEqual(await passive_text(view, 'second', .1, 0), 'second')
            view.evaluate_javascript.assert_awaited_once()
        asyncio.run(exercise())

    def test_an_initial_blank_event_does_not_count_as_the_target_document(self):
        async def exercise():
            view = SimpleNamespace(_repro_load_count=1, _repro_loaded=asyncio.Event(), evaluate_javascript=AsyncMock(side_effect=['', 'second']))
            async def complete():
                await asyncio.sleep(.01)
                view._repro_load_count += 1
                view._repro_loaded.set()
            task = asyncio.create_task(complete())
            self.assertEqual(await passive_text(view, 'second', .2, 0), 'second')
            await task
            self.assertEqual(view.evaluate_javascript.await_count, 2)
        asyncio.run(exercise())
