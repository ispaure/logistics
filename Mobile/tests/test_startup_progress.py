"""Startup reports real phases, yields for drawing and preserves failure state."""
import asyncio
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from logisticsmobile.startup import STEPS, AndroidStartupCover, begin_startup, finish_startup
from logisticsmobile.app import LogisticsMobile


class StartupProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_exit_during_loading_cancels_initialization_without_partial_checkpoint(self):
        app = SimpleNamespace(_startup_in_progress=True, startup_task=Mock(), active_host=True)
        self.assertTrue(LogisticsMobile.exit_app(app, app))
        app.startup_task.cancel.assert_called_once_with()
        self.assertFalse(app.active_host)

    async def test_native_running_callback_waits_for_ready_and_receives_app(self):
        running = AsyncMock()
        screen = SimpleNamespace(reveal_workspace=AsyncMock(), view=object(), show_step=Mock(), hide_chrome=Mock(), progress=SimpleNamespace(value=0))
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
        screen = SimpleNamespace(reveal_workspace=AsyncMock(), show_step=lambda index, name: events.append(('stage', index)),
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
        screen = SimpleNamespace(reveal_workspace=AsyncMock(), show_step=Mock(), progress=SimpleNamespace(value=0),
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
        screen = SimpleNamespace(reveal_workspace=AsyncMock(), show_step=Mock(), progress=SimpleNamespace(value=0), failed=Mock())
        app = SimpleNamespace(_startup_steps=steps, startup_screen=screen,
                              _startup_in_progress=True, resize_workspace=Mock())
        with self.assertRaises(asyncio.CancelledError):
            await finish_startup(app)
        screen.failed.assert_not_called()
        app.resize_workspace.assert_not_called()


class StartupCoverTests(unittest.IsolatedAsyncioTestCase):
    async def test_android_snapshot_includes_flattened_window_children_and_cleans_up(self):
        container = SimpleNamespace(native_parent=Mock(), native_content=Mock())
        root, image, bitmap, canvas = Mock(), Mock(), Mock(), Mock()
        container.native_content.getWidth.return_value = 900
        container.native_content.getHeight.return_value = 1200
        app = SimpleNamespace(loop=asyncio.get_running_loop(),
            main_window=SimpleNamespace(_impl=SimpleNamespace(container=container)),
            navigation=SimpleNamespace(_impl=SimpleNamespace(native=root)))
        modules = {
            'android.graphics': SimpleNamespace(Bitmap=SimpleNamespace(
                createBitmap=Mock(return_value=bitmap), Config=SimpleNamespace(ARGB_8888=1)),
                Canvas=Mock(return_value=canvas)),
            'android.widget': SimpleNamespace(FrameLayout=SimpleNamespace(LayoutParams=Mock()),
                ImageView=Mock(return_value=image)),
            'android.view': SimpleNamespace(ViewTreeObserver=SimpleNamespace(OnPreDrawListener=object)),
            'java': SimpleNamespace(dynamic_proxy=lambda interface: object),
        }
        with patch.dict(sys.modules, modules):
            cover = AndroidStartupCover(app)
        container.native_content.draw.assert_called_once_with(canvas)
        modules['android.graphics'].Bitmap.createBitmap.assert_called_once_with(900, 1200, 1)
        container.native_parent.addView.assert_called_once()
        cover.observer = Mock()
        cover.dispose()
        cover.observer.removeOnPreDrawListener.assert_called_once_with(cover.listener)
        container.native_parent.removeView.assert_called_once_with(image)
        root.setImportantForAccessibility.assert_called_with(cover.accessibility)
        image.setImageDrawable.assert_called_once_with(None)
        self.assertTrue(cover.future.cancelled())

    async def test_android_cover_waits_for_measured_reflow_and_clean_draw(self):
        root, content = Mock(), Mock()
        for native in (root, content):
            native.getWidth.return_value = 0
            native.getHeight.return_value = 800
            native.isLayoutRequested.return_value = False
        app = SimpleNamespace(navigation=SimpleNamespace(
            _impl=SimpleNamespace(native=root, native_content=content), refresh=Mock()),
            resize_workspace=Mock())
        cover = object.__new__(AndroidStartupCover)
        cover.app, cover.parent, cover.geometry = app, Mock(), None
        cover.future = asyncio.get_running_loop().create_future()
        cover.before_draw()
        self.assertFalse(cover.future.done())
        app.resize_workspace.assert_not_called()
        root.getWidth.return_value = 900
        content.getWidth.return_value = 820
        root.isLayoutRequested.return_value = True
        cover.before_draw()
        self.assertFalse(cover.future.done())
        root.isLayoutRequested.return_value = False
        cover.before_draw()
        app.resize_workspace.assert_called_once_with()
        app.navigation.refresh.assert_called_once_with()
        self.assertFalse(cover.future.done())
        # A rail resize before the next draw must reflow again under the cover.
        content.getWidth.return_value = 810
        cover.before_draw()
        self.assertEqual(app.resize_workspace.call_count, 2)
        self.assertFalse(cover.future.done())
        cover.before_draw()
        self.assertTrue(cover.future.result())

    async def test_startup_stays_cancellable_until_workspace_is_revealed(self):
        ready = asyncio.Event()
        async def reveal(app):
            self.assertTrue(app._startup_in_progress)
            self.assertTrue(app._startup_layout_ready)
            await ready.wait()
        screen = SimpleNamespace(show_step=Mock(), progress=SimpleNamespace(value=0),
            reveal_workspace=reveal, cover=SimpleNamespace(dispose=Mock()))
        app = SimpleNamespace(_startup_steps=lambda: iter(()), startup_screen=screen,
            _startup_in_progress=True, resize_workspace=Mock())
        task = asyncio.create_task(finish_startup(app))
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        screen.cover.dispose.assert_called_once_with()

    async def test_reveal_removes_cover_when_native_measurement_fails(self):
        from logisticsmobile.startup import StartupScreen
        screen = object.__new__(StartupScreen)
        cover = screen.cover = SimpleNamespace(ready=AsyncMock(side_effect=ValueError('layout')),
                                                dispose=Mock())
        with self.assertRaises(ValueError):
            await screen.reveal_workspace(SimpleNamespace())
        cover.dispose.assert_called_once_with()
        self.assertIsNone(screen.cover)
