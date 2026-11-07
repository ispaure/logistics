"""Native page-count jobs retain numeric results and retire with their bridge."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call

from features.books.mobile.pagination import MobilePagination
from features.books.mobile.presentation import ChapterBridge


class Book:
    spine = ['short', 'long']


class PaginationTests(unittest.TestCase):
    def test_page_visit_back_is_bounded_and_failed_publication_keeps_target(self):
        from services.documents.page_visits import PageVisits
        async def exercise():
            visits = PageVisits()
            for index in range(105):
                visits.visit((0, index))
            self.assertEqual(len(visits.previous), 100)
            async def fail(position):
                raise ValueError('Page unavailable')
            with self.assertRaises(ValueError):
                await visits.back(fail)
            self.assertEqual(visits.previous[-1], (0, 103))
            async def publish(position):
                visits.visit(position)
            await visits.back(publish)
            self.assertEqual(visits.current, (0, 103))
            self.assertEqual(visits.previous[-1], (0, 102))
        asyncio.run(exercise())

    def test_counts_unknown_chapters_without_changing_the_current_page(self):
        async def exercise():
            request = [None]
            def evaluate(script):
                future = asyncio.get_running_loop().create_future()
                if '.measure(' in script:
                    request[0] = script.rsplit(',', 1)[1].strip(')"')
                    future.set_result(None)
                elif '.measurement()' in script:
                    future.set_result(json.dumps(dict(id=request[0], layout='portrait', done=True, count=9)))
                else:
                    future.set_result(None)
                return future
            view = SimpleNamespace(evaluate_javascript=Mock(side_effect=evaluate))
            view._chapter_bridge = bridge = ChapterBridge(view, root='https://logistics.invalid/count/')
            bridge.ready = True
            changed, render = Mock(), Mock(return_value='<html><body>Private test text</body></html>')
            book = Book()
            counter = MobilePagination(book, changed)
            counter.bind(view, 0, render, asyncio.get_running_loop(), length=3)
            counter.receive(dict(layout='portrait', count=1, index=0, columns=1))
            await bridge.pagination_task
            self.assertEqual(counter.pages.counts, [1, 9])
            self.assertEqual(render.call_args_list, [call(1), call(1)])
            self.assertEqual(changed.call_args.args[0]['text'], '0% · Page 1 of 10 · Chapter 1 of 2')
            bridge.dispose()
            self.assertIsNone(counter.view)
            self.assertIsNone(counter.render)
            self.assertIsNone(bridge.pagination_task)
        asyncio.run(exercise())

    def test_dispose_cancels_before_reading_another_private_chapter(self):
        async def exercise():
            view = SimpleNamespace(evaluate_javascript=Mock())
            view._chapter_bridge = bridge = ChapterBridge(view, root='https://logistics.invalid/count/')
            book, render = Book(), Mock()
            counter = MobilePagination(book, Mock())
            counter.bind(view, 0, render, asyncio.get_running_loop())
            counter.receive(dict(layout='portrait', count=1, index=0, columns=1))
            task = bridge.pagination_task
            scan = counter.text_scan
            bridge.dispose()
            await asyncio.sleep(0)
            self.assertTrue(task.cancelled())
            self.assertTrue(scan.cancelled())
            render.assert_not_called()
            self.assertIsNone(counter.bridge)
            self.assertEqual(counter.pages.counts, [1, None])
        asyncio.run(exercise())

    def test_text_progress_precedes_page_counts_and_survives_reflow(self):
        async def exercise():
            view = SimpleNamespace(evaluate_javascript=Mock())
            bridge = view._chapter_bridge = ChapterBridge(view, root='https://logistics.invalid/count/', offset=2)
            book = Book()
            changed = Mock()
            render = Mock(return_value='<html><body>abcd</body></html>')
            counter = MobilePagination(book, changed)
            counter.bind(view, 1, render, asyncio.get_running_loop(), length=8, worker=True)
            await counter.text_scan
            self.assertEqual(changed.call_args.args[0]['mobile'], '50% · Counting pages…\nChapter 2 of 2')
            for layout, counts, label in (
                ('portrait', [2, 4], '50% · Page 3 of 6 · Chapter 2 of 2'),
                ('landscape', [1, 2], '50% · Page 2 of 3 · Chapter 2 of 2'),
            ):
                counter.pages.reset(layout)
                counter.pages.record(0, counts[0])
                counter.receive(dict(layout=layout, count=counts[1], index=0, columns=1))
                self.assertEqual(changed.call_args.args[0]['text'], label)
            counter.text_position(5)
            self.assertEqual(changed.call_args.args[0]['text'], '75% · Page 2 of 3 · Chapter 2 of 2')
            render.assert_called_once_with(0)
            bridge.dispose()
        asyncio.run(exercise())
