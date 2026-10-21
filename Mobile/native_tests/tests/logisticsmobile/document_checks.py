"""Native Back, persisted preferences, document drafts and Markdown ownership."""
import asyncio
import gc
from commonUtils.runtime.platform import get_os, OS
from logisticsmobile.preferences import Preferences
from .web_checks import wait_for_text


async def exercise_loading_layout(app):
    """Long filenames must not enlarge or displace the loading presentation."""
    if get_os() is not OS.IOS:
        return
    from logisticsmobile.document_sources import opening_status
    app.show_home()
    for name in ('Book.epub', 'A very long book filename ' * 12 + '.epub'):
        with opening_status(app, dict(key=name), destination='home'):
            await asyncio.sleep(.3)
            panel = app.routes.body().children[0]
            content = panel.children[1]
            width = float(app.main_window._impl.native.bounds.size.width)
            for widget in content.children:
                native = widget._impl.native
                rect = native.convertRect(native.bounds, toView=None)
                left, size = float(rect.origin.x), float(rect.size.width)
                assert left >= 31 and left + size <= width - 31
                assert abs(left + size / 2 - width / 2) < 2
            label = content.children[1]
            assert label.text == name
            assert label._impl.native.textAlignment == 1  # Center
            assert label._impl.native.lineBreakMode == 5  # Middle ellipsis


async def exercise_documents(app, passed):
    await exercise_loading_layout(app)
    await exercise_loading_progress(app)
    app.show_documents(destination='documents')
    app.editor.value = 'Draft survives actual Back'
    import toga
    app.show_view(toga.Label('Route detail'), route='route-check', title='Route detail')
    assert app.native_host.state.routes['documents'] == ['editor', 'route-check']
    if get_os() is OS.IOS:
        navigation = app.adaptive.secondary if app.adaptive.split is not None else app.native_host.adapter.navigation[2]
        # UIKit can ignore a pop requested during the preceding push.
        await asyncio.sleep(.05)
        for _ in range(60):
            if navigation.transitionCoordinator is None:
                break
            await asyncio.sleep(.05)
        navigation.popViewControllerAnimated(False)
    else:
        app._impl.native.getOnBackPressedDispatcher().onBackPressed()
    for _ in range(60):
        if app.native_host.state.routes['documents'] == ['editor']:
            break
        await asyncio.sleep(.05)
    assert app.native_host.state.routes['documents'] == ['editor'], app.native_host.state.routes['documents']
    assert app.body.children[0] is app.document_view
    assert app.editor.value == 'Draft survives actual Back'
    passed.append('native_route_back')
    app.show_settings()
    app.settings_navigation.choose('Text')
    app.text_font_size_choice.value = '18'
    app.save_preferences()
    assert Preferences(app.private_root).values['text_font_size'] == '18'
    passed.append('native_preferences')
    app.show_documents()
    app.name.value = 'Native.md'
    app.editor.value = '# Native preview\n'
    app.save_document()
    assert app.store.open(app.current.id).text == '# Native preview\n'
    passed.append('native_documents')
    a, a_editor = app.current.id, app.editor
    app.editor.value = '# Native preview\nA draft\n'
    app.new_document()
    b, b_session = app.current.id, app.editor_view.session.id
    app.name.value = 'Other.md'
    app.editor.value = 'B draft\n'
    assert app.editor is not a_editor
    app.show_locations()
    app.show_settings()
    app.open_document(a)
    app.show_documents()
    assert app.editor is a_editor
    assert app.editor.value == '# Native preview\nA draft\n'
    from logisticsmobile.workspace import Workspace
    restored = Workspace(app.private_root)
    assert len(restored.sessions) == 2
    assert app.store.open(b).text == 'B draft\n'
    from unittest.mock import AsyncMock, patch
    # Exercise the session decision and await it before continuing native UI
    # work; the old route-based prompt needed no asynchronous dismissal.
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value='cancel')) as decision:
        app.request_close_session(b_session)
        await app._document_close_tasks[b_session]
        decision.assert_awaited_once()
    assert app.close_session(b_session, choice='cancel') is False
    assert b_session in app.workspace.sessions
    app.cancel_close_session(b_session)
    assert app.current.id == b
    app.open_document(a)
    assert app.close_session(b_session, choice='keep')
    assert app.current.id == a
    assert app.store.open(b).text == 'B draft\n'
    app.open_document(b)
    b_session = app.editor_view.session.id
    app.store.path(b, '.data').write_bytes(b'External saved bytes\n')
    assert app.close_session(b_session, choice='save') is False
    assert app.editor.value == 'B draft\n'
    assert app.close_session(b_session, choice='discard')
    # Closing must remain safe after Python releases the editor while native
    # preview replacement callbacks are still queued.
    gc.collect()
    await asyncio.sleep(.1)
    assert app.store.open(b).text == 'External saved bytes\n'
    app.open_document(a)
    app.show_documents()
    app.editor.value = '# Native preview\n'
    missing = app.workspace.open('managed-text', 'f' * 32, 'text')
    app.session_opener(missing.id)()
    assert app.body.children[0].children[0].text == 'Document unavailable'
    assert app.current.id == a
    assert app.close_session(missing.id)
    assert missing.id not in app.workspace.sessions
    app.show_documents()
    passed.append('native_text_workspace')
    app.show_preview()
    await wait_for_text(app.preview, 'Native preview')
    original_preview = app.preview
    a_session = app.editor_view.session.id
    app.new_document()
    app.editor.value = '# Different preview owner\n'
    app.show_documents()
    app.session_opener(a_session)()
    assert app.current.id == a
    assert app.editor_view.session.view['markdown_mode'] == 'preview'
    await wait_for_text(app.preview, 'Native preview', absent='Different preview owner')
    app.show_documents()
    app.show_preview()
    assert app.preview is original_preview
    await wait_for_text(app.preview, 'Native preview')
    passed.append('native_markdown_preview')


async def exercise_loading_progress(app):
    """Real worker reads must drive percentages, then return to preparation."""
    from pathlib import Path
    from threading import Event
    from logisticsmobile.document_sources import opening_status
    from logisticsmobile.loading_progress import reading_stream
    path = Path(app.paths.cache) / 'opening-progress-fixture.bin'
    path.write_bytes(b'x' * (256 * 1024))
    started, released = [Event() for _ in range(4)], [Event() for _ in range(4)]
    def read():
        with path.open('rb') as source, reading_stream(source) as stream:
            for index in range(4):
                assert len(stream.read(64 * 1024)) == 64 * 1024
                started[index].set()
                if not released[index].wait(5):
                    raise RuntimeError('Progress fixture timed out')
    try:
        app.show_home()
        with opening_status(app, dict(key=path.name), destination='home'):
            content = app.routes.body().children[0].children[1]
            bar, status = content.children[2:]
            task = asyncio.create_task(asyncio.to_thread(read))
            try:
                for index in range(4):
                    assert await asyncio.to_thread(started[index].wait, 4)
                    await asyncio.sleep(.15)
                    assert bar.max == 256 * 1024
                    assert abs(bar.value - (index + 1) * 64 * 1024) < 1
                    assert status.text == f'Reading {(index + 1) * 25}%'
                    released[index].set()
                await task
                await asyncio.sleep(.15)
                assert bar.max is None and status.text == 'Preparing document…'
            finally:
                for event in released:
                    event.set()
                await task
    finally:
        path.unlink(missing_ok=True)
