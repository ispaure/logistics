"""Draw acknowledgements, fallback bounds and cancelled native callbacks."""
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch




class LoadingPanelLifecycleTests(IsolatedAsyncioTestCase):
    async def test_home_documents_and_workspaces_wait_before_open_and_recheck_navigation(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import AsyncMock
        import toga
        from mobile.app import LogisticsMobile
        from mobile.document_sources import reopen_file
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
                        with (patch('commonUtils.ui.native.draw_ready.wait_for_draw', side_effect=draw),
                              patch('mobile.document_sources._reopen_file', new_callable=AsyncMock,
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
