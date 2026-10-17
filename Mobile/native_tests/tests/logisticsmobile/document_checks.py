"""Native Back, persisted preferences, document drafts and Markdown ownership."""
import asyncio
import gc
from commonUtils.runtime.platform import get_os, OS
from logisticsmobile.preferences import Preferences
from .web_checks import wait_for_text


async def exercise_documents(app, passed):
    app.show_documents()
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
    app.font_choice.value = '18'
    app.save_preferences()
    assert Preferences(app.private_root).values['font_size'] == '18'
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
    app.request_close_session(b_session)
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
