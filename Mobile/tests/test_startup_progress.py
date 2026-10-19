"""Startup reports real phases, yields for drawing and preserves failure state."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from logisticsmobile.startup import STEPS, begin_startup, finish_startup
from logisticsmobile.app import LogisticsMobile


class StartupProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_exit_during_loading_cancels_initialization_without_partial_checkpoint(self):
        app = SimpleNamespace(_startup_in_progress=True, startup_task=Mock(), active_host=True)
        self.assertTrue(LogisticsMobile.exit_app(app, app))
        app.startup_task.cancel.assert_called_once_with()
        self.assertFalse(app.active_host)

    async def test_native_running_callback_waits_for_ready_and_receives_app(self):
        running = AsyncMock()
        screen = SimpleNamespace(view=object(), show_step=Mock(), hide_chrome=Mock(), progress=SimpleNamespace(value=0))
        app = SimpleNamespace(loop=asyncio.get_running_loop(), on_running=running,
            _startup_steps=lambda: iter(STEPS), _startup_in_progress=True, resize_workspace=Mock())
        window = Mock()
        with patch('logisticsmobile.startup.StartupScreen', return_value=screen), \
                patch('logisticsmobile.startup.toga.MainWindow', return_value=window):
            begin_startup(app)
        window.show.assert_called_once_with()
        running.assert_not_called()
        await app.on_running(app)
        running.assert_awaited_once_with(app)
        self.assertIs(app.main_window, window)
        self.assertTrue(app.startup_task.result())

    async def test_each_phase_is_presented_before_its_work_and_completion(self):
        events = []
        def steps():
            for index, name in enumerate(STEPS):
                yield name
                events.append(('work', index))
        screen = SimpleNamespace(show_step=lambda index, name: events.append(('stage', index)),
                                 progress=SimpleNamespace(value=0))
        app = SimpleNamespace(_startup_steps=steps, startup_screen=screen,
                              _startup_in_progress=True, resize_workspace=Mock())
        sleep = asyncio.sleep
        async def draw(delay):
            events.append(('draw', events[-1][1]))
            await sleep(0)
        with patch('logisticsmobile.startup.asyncio.sleep', side_effect=draw):
            self.assertTrue(await finish_startup(app))
        self.assertEqual(events, [(kind, index) for index in range(len(STEPS))
                                  for kind in ('stage', 'draw', 'work')])
        self.assertEqual(screen.progress.value, len(STEPS))
        self.assertFalse(app._startup_in_progress)
        app.resize_workspace.assert_called_once_with()

    async def test_failed_phase_keeps_loading_screen_without_false_completion(self):
        def steps():
            yield STEPS[0]
            raise OSError('private/path/account-name')
        screen = SimpleNamespace(show_step=Mock(), progress=SimpleNamespace(value=0),
                                 failed=Mock(), view=object())
        app = SimpleNamespace(_startup_steps=steps, startup_screen=screen,
            _startup_in_progress=True, resize_workspace=Mock(),
            main_window=SimpleNamespace(content=object(), on_resize=Mock(), on_lose_focus=Mock()))
        with self.assertLogs('logisticsmobile.startup', level='ERROR'):
            self.assertFalse(await finish_startup(app))
        screen.failed.assert_called_once_with()
        self.assertIs(app.main_window.content, screen.view)
        self.assertLess(screen.progress.value, len(STEPS))
        self.assertTrue(app._startup_in_progress)
        self.assertIsNone(app.main_window.on_lose_focus)
        app.resize_workspace.assert_not_called()

    async def test_cancelled_startup_does_not_show_failure_or_open_workspace(self):
        def steps():
            yield STEPS[0]
            raise asyncio.CancelledError
        screen = SimpleNamespace(show_step=Mock(), progress=SimpleNamespace(value=0), failed=Mock())
        app = SimpleNamespace(_startup_steps=steps, startup_screen=screen,
                              _startup_in_progress=True, resize_workspace=Mock())
        with self.assertRaises(asyncio.CancelledError):
            await finish_startup(app)
        screen.failed.assert_not_called()
        app.resize_workspace.assert_not_called()
