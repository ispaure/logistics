"""Actual retained-editor and conversation drawer checks, using window bounds."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from commonUtils.runtime.platform import get_os, OS
from .fixtures import capture_window, ios_toolbar_items


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

    app.show_locations()
    app.choose_folder('All files')
    folder_frame = app.body.children[0]._workspace_frame
    await capture('folder-actions')
    assert folder_frame.header not in folder_frame.view().children
    columns = getattr(app.adaptive, 'file_columns', None)
    if columns is not None:
        # UIKit owns the retained sidebar and navigation column separately;
        # folder_master belongs only to the older in-content split layout.
        assert columns.master.main._impl.container is columns.sidebar
        assert columns.navigation.parentViewController == columns.controller
        assert columns.sidebar.controller.parentViewController == columns.controller
        pair = (float(columns.sidebar.native.bounds.size.width),
                float(columns.navigation.view.bounds.size.width))
        assert min(pair) > 0 and sum(pair) <= app.adaptive.content_width('files', margin=0) + 2, pair
        from mobile.fold_layout import has_fold
        if not has_fold(app, app.main_window):
            assert abs(pair[0] - pair[1]) <= 2, ('Unequal native Workspaces panes', pair)
    elif app.adaptive.wide:
        pair = width(folder_frame.folder_master), width(folder_frame.main)
        assert abs(pair[0] - pair[1]) <= 2, ('Unequal native Workspaces panes', pair)
        assert max(pair) <= app.adaptive.content_width('files') / 2 + 2
    app.show_documents_hub()
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
    assert list(frame.row.children) == [drawer.widget, frame.main]
    if not navigation.wide:
        assert width(drawer.widget) < width(frame.row), 'Drawer must leave the page visible'
        assert width(frame.row) <= navigation.width(), 'Drawer must not widen its viewport'
    if get_os() is OS.IOS:
        assert frame.header not in frame.view().children, 'Menu belongs in the native bar'
        menu_item = frame.menu._ios_action_item
        controller = app.native_host.adapter.content_controller('documents')
        assert menu_item in ios_toolbar_items(controller, leading=True), 'Browse must remain in the native leading toolbar'
        assert menu_item.customView is None, 'UIKit must own menu hit testing'
        parent = frame.menu._impl.native.superview
        parent = parent() if callable(parent) else parent
        assert parent is None, 'Detached Toga target must not intercept touches'
        assert menu_item.target == frame.menu._impl.native
    frame.menu.on_press()
    assert first.editor.value == '# Left\n\nAn independent draft.'
    assert second.editor.value == '# Right\n\nAnother independent draft.'
    navigation.pinned = None
    navigation.render()
    if get_os() is OS.IOS:
        # UIKit may signal its item before updating selectedViewController.
        # A setter-driven test only covers the opposite event order.
        adapter = app.native_host.adapter
        adapter.controller.tabBar_didSelectItem_(adapter.controller.tabBar, adapter.navigation[app.native_host.destinations.index('chat')].tabBarItem)
        adapter.controller.selectedIndex = app.native_host.destinations.index('chat')
        await asyncio.sleep(.3)
        assert app.native_host.state.destination == 'chat', 'Chat must open on the first native item signal'
        assert app.chat_messages in app.chat_workspace.children
        assert width(app.chat_prompt) > 0
    else:
        app.show_chat()
    app.chat_prompt.value = 'Unsent conversation draft'
    key = app.chat_current['id']
    if get_os() is OS.IOS:
        before = app.chat_drawer_open
        app.chat_menu_button._impl.native.sendActionsForControlEvents(1)
        assert app.chat_drawer_open == before, 'Touch-down must not open a drawer'
        app.chat_menu_button._impl.native.sendActionsForControlEvents(1 << 6)
        assert app.chat_drawer_open != before, 'Release inside must toggle the drawer'
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
    if get_os() is OS.IOS:
        window = app.main_window._impl.native
        prompt = app.chat_prompt._impl.native
        rect = prompt.convertRect(prompt.bounds, toView=window)
        tab = app.native_host.adapter.controller.tabBar
        bar = tab.convertRect(tab.bounds, toView=window)
        if not tab.isHidden() and bar.origin.y >= rect.origin.y:
            assert rect.origin.y + rect.size.height <= bar.origin.y - 10, 'Tab bar covers composer'
    app.show_settings()
    await capture('settings')
    assert app.native_host.state.destination == 'settings'
    return dict(workspace_screenshots=screenshots, workspace_drawers_tested=True,
                two_documents_tested=navigation.wide, chat_drawer_tested=True)
