"""Bound UI work without relying on machine-dependent timing thresholds."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.browser_ui import FileBrowser


class ResponsivenessTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        LogisticsMobile.storage_root = Path(self.temp.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)

    def test_settings_are_lazy_and_native_selection_does_not_reenter_navigation(self):
        app = self.app
        self.assertFalse(hasattr(app, 'settings_navigation'))
        with patch.object(app.native_host, 'activate', wraps=app.native_host.activate) as activate:
            self.assertTrue(app.select_destination('settings'))
            activate.assert_not_called()
        navigation = app.settings_navigation
        self.assertTrue(app.routes.roots['settings'].children)
        app.native_host.activate('settings')
        app.select_destination('home')
        app.native_host.activate('home')
        with patch.object(navigation, 'reflow') as reflow:
            app.show_documents()
            reflow.assert_not_called()
        app.select_destination('settings')
        self.assertIs(app.settings_navigation, navigation)

    def test_file_tap_opens_without_loading_information_but_explicit_selection_keeps_it(self):
        selected, opened = [], []
        details = Mock(return_value=[('Title', 'A book')])
        browser = FileBrowser(selected=selected.append, open_file=opened.append, details=details)
        provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
        row = dict(path='Book.epub', name='Book.epub', directory=False)
        browser.set_entries(provider, '', [row])
        selected.clear()  # Publishing a folder snapshot clears the old selection.

        async def exercise():
            entry = browser.entries[0]
            await browser._select_pressed(entry, browser.buttons[entry.identity])
            self.assertEqual(selected, [row])
            self.assertEqual(opened, [row])
            details.assert_not_called()
            await browser.select(entry)
            details.assert_called_once()
            self.assertTrue(any(getattr(child, 'text', '') == 'Title: A book' for child in browser.info.children))
            await browser.close()
        self.app.loop.run_until_complete(exercise())

    def test_local_markdown_initial_render_runs_once_off_ui_thread(self):
        from commonUtils.runtime.local_files import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        from logisticsmobile.preview import markdown_preview
        app = self.app
        app.show_cloud(present=False)
        path = Path(self.temp.name) / 'Note.md'
        path.write_text('# Hello\n\nA local note.\n')
        ui_thread = get_ident()
        rendered_threads = []
        def render(*args, **kwargs):
            rendered_threads.append(get_ident())
            return markdown_preview(*args, **kwargs)
        with patch('logisticsmobile.preview.markdown_preview', side_effect=render):
            app.loop.run_until_complete(app.open_crypt(copies=LocalTextCopies(LocalFiles(path.parent)), key=path.name))
        self.assertEqual(len(rendered_threads), 1)
        self.assertNotEqual(rendered_threads[0], ui_thread)
        owner = app.private_sessions.active
        self.assertEqual(owner.crypt_text.value, path.read_text())
        self.assertIn(owner.crypt_preview, owner.crypt_content.children)
        app.loop.run_until_complete(asyncio.sleep(0))

    def test_file_tap_rejects_listing_replaced_during_selection(self):
        opened = []
        provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
        row = dict(path='Note.md', name='Note.md', directory=False)
        browser = FileBrowser(open_file=opened.append)
        browser.set_entries(provider, '', [row])
        async def selected(value):
            if value is not None:
                await asyncio.sleep(0)
                browser.set_entries(provider, '', [dict(row, revision='replaced')])
        browser.on_selected = selected
        async def exercise():
            entry = browser.entries[0]
            await browser._select_pressed(entry, browser.buttons[entry.identity])
            self.assertEqual(opened, [])
            self.assertFalse(browser.navigation_busy)
            await browser.close()
        self.app.loop.run_until_complete(exercise())

    def test_selection_styles_only_the_rows_that_changed(self):
        from logisticsmobile.browser_ui import highlight_entry
        browser = FileBrowser()
        provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
        rows = [dict(path=f'{i}.md', name=f'{i}.md', directory=False) for i in range(40)]
        browser.set_entries(provider, '', rows)
        browser.selected = browser.entries[0].identity
        browser.highlight_selection()
        with patch('logisticsmobile.browser_ui.highlight_entry', wraps=highlight_entry) as style:
            browser.highlight_selection()
            style.assert_not_called()
            browser.selected = browser.entries[1].identity
            browser.highlight_selection()
            self.assertEqual(style.call_count, 4)  # Two rows and their buttons.
        self.app.loop.run_until_complete(browser.close())

    def test_cancel_during_markdown_render_does_not_publish_reader(self):
        from commonUtils.runtime.local_files import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        app = self.app
        app.show_cloud(present=False)
        path = Path(self.temp.name) / 'Cancel.md'
        path.write_text('# Cancel me')
        release = Event()

        async def exercise():
            entered = asyncio.Event()
            def render(*args, **kwargs):
                app.loop.call_soon_threadsafe(entered.set)
                release.wait(10)
                return '<html>cancelled passage</html>'
            with patch('logisticsmobile.preview.markdown_preview', side_effect=render):
                opening = asyncio.create_task(app.open_crypt(copies=LocalTextCopies(LocalFiles(path.parent)), key=path.name))
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    owner = next(iter(app.private_sessions.controllers.values()))
                    owner.cancel_cloud()
                finally:
                    release.set()
                self.assertFalse(await opening)
            self.assertFalse(app.private_sessions.controllers)
            self.assertIsNone(app.private_sessions.active)
        app.loop.run_until_complete(exercise())

    def test_markdown_render_error_keeps_source_without_rerendering_on_ui_thread(self):
        from commonUtils.runtime.local_files import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        app = self.app
        app.show_cloud(present=False)
        path = Path(self.temp.name) / 'Source.md'
        path.write_text('# Keep original text')
        with patch('logisticsmobile.preview.markdown_preview', side_effect=ValueError('Cannot render this image')) as render:
            self.assertTrue(app.loop.run_until_complete(app.open_crypt(
                copies=LocalTextCopies(LocalFiles(path.parent)), key=path.name)))
            render.assert_called_once()
        owner = app.private_sessions.active
        self.assertEqual(owner.crypt_text.value, path.read_text())
        self.assertIn(owner.crypt_text, owner.crypt_content.children)
        self.assertIn('Cannot render this image', owner.crypt_title.text)


if __name__ == '__main__':
    unittest.main()
