"""Actual retained-editor and conversation drawer checks, using window bounds."""
import asyncio
from .fixtures import capture_window


async def exercise_workspace(app):
    screenshots = []

    async def capture(name):
        await asyncio.sleep(.4)
        path = app.storage_root / ('workspace-' + name + '.png')
        await capture_window(app, path)
        screenshots.append(str(path))

    app.create_chosen_document('md')
    app.name.value = 'Left draft.md'
    first = app.editor_view
    first.editor.value = '# Left\n\nAn independent draft.'
    app.create_chosen_document('md')
    app.name.value = 'Right draft.md'
    second = app.editor_view
    second.editor.value = '# Right\n\nAnother independent draft.'
    navigation = app.adaptive
    navigation.pinned = first.session.id
    navigation.render()
    frame = second.document_view._workspace_frame
    await capture('documents')
    if navigation.wide:
        assert list(frame.row.children) == [first.document_view._workspace_frame.main, frame.main]
        assert abs(first.document_view._workspace_frame.main.layout.width - frame.main.layout.width) <= 2
    else:
        assert list(frame.row.children) == [frame.main]
    frame.menu.on_press()
    drawer = navigation.browser('documents')
    await drawer.task
    await capture('document-browser')
    assert list(frame.row.children) == ([drawer.widget, frame.main] if navigation.wide else [drawer.widget])
    frame.menu.on_press()
    assert first.editor.value == '# Left\n\nAn independent draft.'
    assert second.editor.value == '# Right\n\nAnother independent draft.'
    navigation.pinned = None
    navigation.render()
    app.show_chat()
    app.chat_prompt.value = 'Unsent conversation draft'
    key = app.chat_current['id']
    app.chat_drawer_open = True
    app.render_chat_workspace()
    await capture('conversations')
    assert list(app.chat_workspace.children) == ([app.chat_sidebar, app.chat_messages] if navigation.wide else [app.chat_sidebar])
    if navigation.wide:
        assert abs(app.chat_sidebar.layout.width - app.chat_messages.layout.width) <= 2
    app.open_chat(key)
    assert app.chat_prompt.value == 'Unsent conversation draft'
    app.chat_drawer_open = False
    app.render_chat_workspace()
    await capture('chat')
    app.show_settings()
    await capture('settings')
    assert app.native_host.state.destination == 'settings'
    return dict(workspace_screenshots=screenshots, workspace_drawers_tested=True,
                two_documents_tested=navigation.wide, chat_drawer_tested=True)
