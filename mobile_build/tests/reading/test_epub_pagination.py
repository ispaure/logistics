"""Native page-count jobs retain numeric results and retire with their bridge."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from features.books.mobile.pagination import MobilePagination
from features.books.mobile.presentation import ChapterBridge


class Book:
    spine = ['short', 'long']


class PaginationTests(unittest.TestCase):
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
            counter.bind(view, 0, render, asyncio.get_running_loop())
            counter.receive(dict(layout='portrait', count=1, index=0, columns=1))
            await bridge.pagination_task
            self.assertEqual(counter.pages.counts, [1, 9])
            render.assert_called_once_with(1)
            self.assertEqual(changed.call_args.args[0]['text'], '10% · Page 1 of 10 · Chapter 1 of 2')
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
            bridge.dispose()
            await asyncio.sleep(0)
            self.assertTrue(task.cancelled())
            render.assert_not_called()
            self.assertIsNone(counter.bridge)
            self.assertEqual(counter.pages.counts, [1, None])
        asyncio.run(exercise())
