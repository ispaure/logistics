"""Actual retained-editor and conversation drawer checks, using window bounds."""
import asyncio
from commonUtils.runtime.platform import get_os, OS
from .fixtures import capture_window


async def exercise_workspace(app):
    screenshots = []

    def width(widget):
        native = widget._impl.native
        if get_os() is OS.IOS:
            return float(native.bounds.size.width)
        density = app._impl.native.getResources().getDisplayMetrics().density
        return float(native.getWidth()) / density

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
        pair = width(first.document_view._workspace_frame.main), width(frame.main)
        assert abs(pair[0] - pair[1]) <= 2, ('Unequal native document panes', pair)
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
        pair = width(app.chat_sidebar), width(app.chat_messages)
        assert abs(pair[0] - pair[1]) <= 2, ('Unequal native chat panes', pair)
        assert max(pair) <= app.adaptive.content_width('chat') / 2 + 2, ('Chat exceeded its native allocation', pair)
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
