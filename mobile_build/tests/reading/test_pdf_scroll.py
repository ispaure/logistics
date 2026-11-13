"""PDF scroll publication keeps viewport observation and page jumps independent."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.testing.stages import TestStage
from features.pdf.mobile.continuous import PDFScroll

TEST_STAGE = TestStage.REGRESSION


class PDFScrollTests(unittest.IsolatedAsyncioTestCase):
    def surface(self):
        events = []
        view = SimpleNamespace(set_content=lambda *args: None, _impl=object())
        scroll = PDFScroll(view, object(), [.5, 2] * 5000, loop=asyncio.get_running_loop(),
                           active=lambda: True, on_position=lambda *args: events.append(args))
        return scroll, events

    async def test_scroll_samples_trim_pixels_without_seeking(self):
        scroll, events = self.surface()
        scroll.jump(400, (b'pixels', []))
        first = dict(page=400, offset=.85, zoom=1.25, x=.5, wanted=[400, 401, 402, 399],
                     missing=[401], action=None, revision=scroll.revision)
        reverse = dict(first, page=399, wanted=[399, 400, 398], missing=[])
        scroll.js = AsyncMock(side_effect=[True, first, True, reverse])
        with patch('features.pdf.mobile.continuous.render_page', return_value=(b'next', [])) as render:
            await scroll.update()
            await scroll.update()
        render.assert_called_once_with(scroll.document, 401, links=False)
        self.assertEqual([index for index, _ in events], [400, 399])
        self.assertEqual(events[0][1], {'zoom': 1.25, 'offset': .85, 'center': [.5]})
        self.assertEqual(list(scroll.pages), [400])
        self.assertEqual(sum('seek(' in call.args[0] for call in scroll.js.call_args_list), 1)

    async def test_jump_rejects_pixels_from_old_viewport(self):
        scroll, _ = self.surface()
        scroll.jump(2, (b'initial', []))
        state = dict(page=2, offset=0, zoom=1, x=.5, wanted=[2, 3], missing=[3],
                     action=None, revision=scroll.revision)
        scroll.js = AsyncMock(side_effect=[True, state])
        started = asyncio.Event()
        release = asyncio.Event()

        async def decode(*args, **kwargs):
            started.set()
            await release.wait()
            return b'stale', []

        with patch('features.pdf.mobile.continuous.asyncio.to_thread', side_effect=decode):
            update = asyncio.create_task(scroll.update())
            await asyncio.wait_for(started.wait(), 1)
            scroll.jump(9999, (b'last', []))
            release.set()
            await update
        self.assertEqual(scroll.pages, {9999: (b'last', [])})
        self.assertEqual(scroll.js.await_count, 2)
