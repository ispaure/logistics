"""Draw acknowledgements, fallback bounds and cancelled native callbacks."""
import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch
from logisticsmobile.draw_ready import wait_for_draw


class DrawReadyTests(IsolatedAsyncioTestCase):
    async def test_waits_for_native_ack_then_removes_listener(self):
        calls, callbacks = [], []
        def install(panel, drawn):
            callbacks.append(drawn)
            return lambda: calls.append('removed')
        with patch('logisticsmobile.draw_ready._install_draw_probe', side_effect=install):
            task = asyncio.create_task(wait_for_draw(SimpleNamespace()))
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            callbacks[0]()
            self.assertTrue(await task)
        self.assertEqual(calls, ['removed'])

    async def test_timeout_and_cancel_retire_late_callbacks(self):
        for cancel in (False, True):
            calls, callbacks = [], []
            def install(panel, drawn):
                callbacks.append(drawn)
                return lambda: calls.append('removed')
            with patch('logisticsmobile.draw_ready._install_draw_probe', side_effect=install):
                task = asyncio.create_task(wait_for_draw(SimpleNamespace(), timeout=.01))
                await asyncio.sleep(0)
                if cancel:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                else:
                    self.assertFalse(await task)
                callbacks[0]()
                await asyncio.sleep(0)
            self.assertEqual(calls, ['removed'])


class LoadingPanelLifecycleTests(IsolatedAsyncioTestCase):
    async def test_home_documents_and_workspaces_wait_before_open_and_recheck_navigation(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import AsyncMock
        import toga
        from logisticsmobile.app import LogisticsMobile
        from logisticsmobile.document_sources import reopen_file
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                for destination in ('home', 'documents', 'files'):
                    for leave in (False, True):
                        app.show_view(toga.Box(), destination=destination, route='origin', root=True)
                        entered, finish = asyncio.Event(), asyncio.Event()
                        panels = []
                        async def draw(panel):
                            panels.append(panel)
                            entered.set()
                            await finish.wait()
                            return True
                        with (patch('logisticsmobile.draw_ready.wait_for_draw', side_effect=draw),
                              patch('logisticsmobile.document_sources._reopen_file', new_callable=AsyncMock,
                                    return_value=True) as operation):
                            task = asyncio.create_task(reopen_file(app, dict(type='local', path='/synthetic/Private.md')))
                            await entered.wait()
                            operation.assert_not_awaited()
                            if leave:
                                app.show_view(toga.Box(), destination='settings', route='replacement', root=True)
                            finish.set()
                            self.assertEqual(await task, not leave)
                            self.assertEqual(operation.await_count, 0 if leave else 1)
                        self.assertIsNone(app._file_loading)
                        content = panels[0].children[1]
                        self.assertEqual(content.children[1].text, '')
                        self.assertIsNone(content.children[0].image)
            finally:
                app.main_window.close()
                LogisticsMobile.storage_root = None
