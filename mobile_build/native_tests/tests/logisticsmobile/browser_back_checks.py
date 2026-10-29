"""Native document Back and tab return preserve the browser viewport."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import base64
import json
from zipfile import ZipFile
from commonUtils.runtime.platform import get_os, OS


async def prepare_android_back(app):
    """Measure screen Back after the IME's separate dismissal has settled."""
    if get_os() is not OS.ANDROID:
        return
    from android.content import Context
    from java import jclass
    activity = app._impl.native
    decor = activity.getWindow().getDecorView()
    focused = activity.getCurrentFocus()
    if focused is not None:
        focused.clearFocus()
    decor.setFocusableInTouchMode(True)
    decor.requestFocus()
    manager = activity.getSystemService(Context.INPUT_METHOD_SERVICE)
    settled = 0
    for _ in range(100):
        manager.hideSoftInputFromWindow(decor.getWindowToken(), 0)
        await asyncio.sleep(.1)
        insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(decor)
        visible = bool(insets and insets.isVisible(jclass('androidx.core.view.WindowInsetsCompat$Type').ime()))
        settled = 0 if visible else settled + 1
        if settled >= 4:
            return
    raise AssertionError('IME did not settle before native screen Back')


async def cancel_dirty_reader_back(app, owner):
    """Exercise Back on the actual window-modal draft decision."""
    from unittest.mock import patch
    from features.text_editor.mobile.document_dialogs import DocumentDialog
    shown = []
    original = DocumentDialog._show
    def capture(dialog, window):
        shown.append(dialog)
        return original(dialog, window)
    with patch.object(DocumentDialog, '_show', capture):
        app.native_host.adapter.impl._native_activity.getOnBackPressedDispatcher().onBackPressed()
        for _ in range(100):
            if shown and getattr(shown[0], 'native', None) is not None and shown[0].native.isShowing():
                break
            await asyncio.sleep(.05)
        assert shown and shown[0].native.isShowing(), 'Dirty-reader Back did not present its native decision'
        assert owner.session.id in app.workspace.sessions
        # The dialog owns Back while modal; dispatching directly to the
        # activity would bypass the window a user is actually interacting with.
        native = shown[0].native
        native.onBackPressed()
        for _ in range(100):
            if owner.session.id not in app._document_close_tasks:
                break
            await asyncio.sleep(.05)
        assert not native.isShowing()
        assert owner.session.id not in app._document_close_tasks
        assert app.routes.screens['files'][-1][0] == 'private:' + owner.session.id
        assert owner.session.id in app.workspace.sessions


async def exercise_folder_pop_preview(app, *, scroll_position=120):
    """The parent must already contain rows while its refresh is blocked."""
    if get_os() is not OS.IOS:
        return {}
    from services.documents.locations import collection_path
    root = collection_path(app.private_root) / 'Back transition fixture'
    (root / 'Child').mkdir(parents=True, exist_ok=True)
    for index in range(60):
        (root / f'File-{index:02}.txt').write_text('Native transition fixture')
    await app.show_files(location=('Local files', root.name))
    browser = app.file_browser
    browser.show_list()
    await asyncio.sleep(.3)
    browser.vertical_position = scroll_position
    position = browser.vertical_position
    original = browser.native_list._impl.native
    original_top = float(original.convertRect(original.bounds, toView=None).origin.y)
    original_offset = float(original.contentOffset.y)
    await app.browser_file_folder(next(row for row in app.file_rows.values() if row['name'] == 'Child'))
    await asyncio.sleep(.3)
    parent_route, parent_panel, _ = app.routes.screens['files'][-2]
    parent = app.routes.folders.screens['files', parent_route]
    preview = parent.preview
    assert preview is not None and preview.view in parent_panel.children
    assert len(preview.browser.native_list.data) == 61
    release = asyncio.Event()
    navigate = parent.navigate
    async def delayed(location):
        await release.wait()
        return await navigate(location)
    parent.navigate = delayed
    try:
        navigation = app.native_host.adapter.navigation[app.native_host.destinations.index('files')]
        navigation.popViewControllerAnimated(True)
        await asyncio.sleep(.1)
        native = preview.browser.native_list._impl.native
        assert native.window is not None and len(native.visibleCells) > 0
        assert abs(float(native.adjustedContentInset.top)) < 1
        assert abs(float(native.contentOffset.y) - original_offset) < 2
        assert abs(float(native.convertRect(native.bounds, toView=None).origin.y) - original_top) < 2
        await asyncio.sleep(.6)
        assert app.routes.folders.task is not None and not app.routes.folders.task.done()
        assert preview.view in app.routes.body().children
        assert native.window is not None and len(native.visibleCells) > 0
        assert abs(float(native.adjustedContentInset.top)) < 1
        assert abs(float(native.contentOffset.y) - original_offset) < 2
        assert abs(preview.browser.vertical_position - position) < 2
    finally:
        release.set()
        if app.routes.folders.task is not None:
            await app.routes.folders.task
        parent.navigate = navigate
    assert app.file_path == root.name
    return {'parent_rows_ready_during_native_pop': True}


async def exercise_browser_back(app):
    await exercise_folder_pop_preview(app, scroll_position=0)
    transition = await exercise_folder_pop_preview(app)
    await app.show_files()
    root = app.private_root / 'LocalFiles' / 'Back review'
    root.mkdir(exist_ok=True)
    (root / 'A Notes.md').write_text('# Browser note')
    # Keep the measured offset well inside the scroll range on large iPads.
    for index in range(60):
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
    scroll = browser
    for filename in ('Comic.cbz', 'A Notes.md', 'Comic.cbz'):
        def trace_viewport(phase):
            print('LOGISTICS_BROWSER_BACK=' + json.dumps(dict(
                phase=phase, filename=filename, position=scroll.vertical_position,
                routes=app.native_host.state.routes['files'],
                reader_busy=bool(getattr(app.readers.active, 'book_busy', False)),
                back_pending=app.routes.back_task is not None)), flush=True)
            if get_os() is OS.IOS:
                native = browser.native_list._impl.native
                print('LOGISTICS_BROWSER_VIEWPORT=' + json.dumps(dict(
                    phase=phase, filename=filename, position=scroll.vertical_position,
                    raw_y=float(native.contentOffset.y), inset_top=float(native.adjustedContentInset.top),
                    content_inset_top=float(native.contentInset.top), height=float(native.bounds.size.height),
                    content_height=float(native.contentSize.height), rows=len(browser.native_list.data))), flush=True)
        browser.search.value = ''
        # Clearing search still schedules the 400 ms query render. Finish it
        # before measuring the viewport; otherwise it can reset scroll while
        # the reader is opening and make Back look like it lost the position.
        async def settle_search():
            while browser.tasks:
                await asyncio.gather(*tuple(browser.tasks))
        await asyncio.wait_for(settle_search(), timeout=30)
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
        assert scroll.max_vertical_position - position > 88, 'Scroll fixture is too close to its lower bound'
        trace_viewport('before-activate')
        entry = next(item for item in browser.entries if item.label == filename)
        open_file = browser.on_open_file
        def traced_open(payload):
            trace_viewport('before-open-callback')
            return open_file(payload)
        browser.on_open_file = traced_open
        try:
            await browser.activate_entry(entry)
        finally:
            browser.on_open_file = open_file
        trace_viewport('after-activate')
        assert app.native_host.state.destination == 'files'
        owner = app.readers.active if filename.endswith('.cbz') else app.private_sessions.active
        if filename.endswith('.cbz'):
            from .reader_checks import wait_for_reader
            await wait_for_reader(owner)
            # Reveal the native Back button, as a user would from fullscreen.
            if owner.reader_immersive:
                owner.book_content.children[0].toggle_controls()
            reader_panel = app.body
            owner.show_reader_tools()
            await asyncio.sleep(.2)
            await prepare_android_back(app)
            if get_os() is OS.IOS:
                navigation = app.native_host.adapter.navigation[app.native_host.destinations.index('files')]
                navigation.popViewControllerAnimated(True)
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
        if filename.endswith('.cbz'):
            # Returning from tools can reload the native page. Back is guarded
            # while that operation is busy; wait for readiness before tapping.
            await wait_for_reader(owner)
        await prepare_android_back(app)
        trace_viewport('before-return')
        if get_os() is OS.IOS:
            app.native_host.adapter.navigation[
                app.native_host.destinations.index('files')].popViewControllerAnimated(True)
        elif filename.endswith('.md'):
            await cancel_dirty_reader_back(app, owner)
        else:
            app.native_host.adapter.impl._native_activity.getOnBackPressedDispatcher().onBackPressed()
        if filename.endswith('.md') and get_os() is OS.ANDROID:
            # Android Back requests a close. Dirty drafts require a decision;
            # cancelling that decision and selecting Files preserves the draft.
            await app.show_files()
        # didShow arrives after UIKit's transition and layout work. A fixed
        # delay races cold hosted iPads; wait for the retained viewport itself.
        for _ in range(100):
            if (app.body is panel and browser.tree is tree
                    and abs(scroll.vertical_position - position) < 2):
                break
            await asyncio.sleep(.05)
        assert app.body is panel and browser.tree is tree, (
            filename, app.body is panel, browser.tree is tree,
            app.native_host.state.routes['files'], app.file_path)
        assert app.file_path == 'Back review'
        trace_viewport('after-return')
        assert abs(scroll.vertical_position - position) < 2, (position, scroll.vertical_position)
        if filename.endswith('.cbz') and get_os() is OS.ANDROID:
            assert owner.session.id not in app.workspace.sessions
        else:
            assert owner.session.id in app.workspace.sessions
        assert not app._comic_chrome_hidden
        if filename.endswith('.md'):
            assert owner.crypt_text.value == '# Unsaved note after opening from Files'
    assert not hasattr(app, 'book_reader') and not hasattr(app, 'crypt_text')
    return {**transition, 'native_back_to_files': True,
            'native_tab_to_files': get_os() is OS.ANDROID, 'browser_scroll_preserved': True,
            'clean_reader_back_closes': get_os() is OS.ANDROID,
            'draft_retained_on_back': True, 'reader_tools_back_preserved': True,
            'controller_state_is_owned': True}
