"""Real platform Back returns file readers to the retained browser viewport."""
import asyncio
import base64
from zipfile import ZipFile
from commonUtils.runtime.platform import get_os, OS


async def exercise_browser_back(app):
    await app.show_files()
    root = app.private_root / 'LocalFiles' / 'Back review'
    root.mkdir(exist_ok=True)
    (root / 'A Notes.md').write_text('# Browser note')
    for index in range(30):
        (root / f'Item-{index:02}.txt').write_text('Native scroll fixture')
    with ZipFile(root / 'Comic.cbz', 'w') as archive:
        archive.writestr('page.webp', base64.b64decode('UklGRhwAAABXRUJQVlA4TA8AAAAvAYAAEAcQ/Y8CBiKi/wEA'))
    await app.browser_file_location(('Local files', 'Back review'))
    panel, browser = app.body, app.file_browser
    browser.sort.value = browser.sort.items[0].value
    browser.mode = 'List'
    browser.page = 0
    browser.render()
    tree = browser.tree
    scroll = app.files_view._workspace_frame.main.children[-1]
    for filename in ('Comic.cbz', 'A Notes.md', 'Comic.cbz'):
        browser.search.value = ''
        await asyncio.sleep(.3)
        target = min(120, scroll.max_vertical_position)
        scroll.vertical_position = target
        # UIKit's public scroll setter animates. Measure the settled position,
        # not a transient offset partway through that animation.
        for _ in range(20):
            if abs(scroll.vertical_position - target) < 1:
                break
            await asyncio.sleep(.05)
        position = scroll.vertical_position
        assert position > 0, 'Scroll fixture did not exceed the viewport'
        entry = next(item for item in browser.entries if item.label == filename)
        await browser._select_pressed(entry, browser.buttons[entry.identity])
        assert app.native_host.state.destination == 'files'
        owner = app.readers.active if filename.endswith('.cbz') else app.private_sessions.active
        if filename.endswith('.cbz'):
            # Reveal the native Back button, as a user would from fullscreen.
            if owner.reader_immersive:
                owner.book_content.children[0].toggle_controls()
            reader_panel = app.body
            owner.show_reader_tools()
            await asyncio.sleep(.2)
            if get_os() is OS.IOS:
                app.native_host.adapter.navigation[1].popViewControllerAnimated(True)
            else:
                app.native_host.adapter.impl._native_activity.getOnBackPressedDispatcher().onBackPressed()
            for _ in range(60):
                if app.body is reader_panel and owner.library_view in app.body.children:
                    break
                await asyncio.sleep(.05)
            assert app.body is reader_panel and owner.library_view in app.body.children, (
                'Tools Back lost the reader', app.native_host.state.routes['files'],
                [type(child).__name__ for child in app.body.children], app.body is reader_panel)
        else:
            owner.crypt_text.value = '# Unsaved note after opening from Files'
        await asyncio.sleep(.3)
        if get_os() is OS.IOS:
            app.native_host.adapter.navigation[1].popViewControllerAnimated(True)
        else:
            app.native_host.adapter.impl._native_activity.getOnBackPressedDispatcher().onBackPressed()
        await asyncio.sleep(.7)
        assert app.body is panel and browser.tree is tree
        assert app.file_path == 'Back review'
        assert abs(scroll.vertical_position - position) < 2, (position, scroll.vertical_position)
        assert owner.session.id in app.workspace.sessions
        assert not app._comic_chrome_hidden
        if filename.endswith('.md'):
            assert owner.crypt_text.value == '# Unsaved note after opening from Files'
    assert not hasattr(app, 'book_reader') and not hasattr(app, 'crypt_text')
    return {'native_back_to_files': True, 'browser_scroll_preserved': True,
            'draft_retained_on_back': True, 'reader_tools_back_preserved': True,
            'controller_state_is_owned': True}
