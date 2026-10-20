"""Logistics reader gestures and Back policy over destination-local routes."""
import inspect
import weakref

import toga

from commonUtils.ui.native.routes import Routes


def contains(root, widget):
    if widget is None:
        return False
    if root is widget:
        return True
    if isinstance(root, toga.ScrollContainer) and root.content is not None:
        return contains(root.content, widget)
    return any(contains(child, widget) for child in root.children)


class MobileRoutes(Routes):
    def __init__(self, app, *args, **kwargs):
        self.app = app
        self.back_task = None
        self.origins = {}
        from .folder_navigation import FolderNavigation
        self.folders = FolderNavigation(self)
        super().__init__(*args, **kwargs)

    def uninstall(self):
        task = self.folders.task
        if task is not None and not task.done():
            task.cancel()
        for destination, route in list(self.folders.screens):
            self.folders.forget(destination, route)
        super().uninstall()

    def show(self, view, *, destination=None, route=None, title='', root=False):
        # Preview and Edit are modes of the retained document screen.
        route = 'editor' if route == 'preview' else route
        origin = self.host.state.destination
        target = destination or origin
        folder = getattr(view, '_folder_screen', None)
        if self.apple and target in ('files', 'home') and not root and folder is not None and route in ('browser', 'remote-browser', 'workspace-browser'):
            self.folders.present(folder, target)
            return
        if self.apple and not root:
            # Capture before removing a loading route. Replacing that route
            # must not overwrite the folder's original retained viewport.
            self.folders.capture_viewport(target)
        screens = self.screens[target]
        if screens and screens[-1][0].startswith('file-loading:'):
            # The ready reader replaces its loading route. Back goes straight
            # to the retained Home, Documents or workspace screen.
            self.trim(target, len(screens) - 1)
        presentations = [view]
        owner = getattr(self.app, 'editor_view', None)
        if route == 'editor' and owner is not None:
            modes = [getattr(owner, 'document_view', None), getattr(owner, 'preview_box', None)]
            if view in modes:
                presentations = [mode for mode in modes if mode is not None]
        # Session widgets have one native parent. Moving a retained document
        # between tabs retires its old presentation, preserving the screens
        # underneath rather than leaving an empty route behind.
        for previous, screens in self.screens.items():
            if previous == target:
                continue
            index = next((index for index, (_, panel, _) in enumerate(screens)
                          if any(mode in panel.children for mode in presentations)), None)
            if index is not None:
                self.trim(previous, index)
                if view.parent is not None:
                    view.parent.remove(view)
                self.render(previous)
        super().show(view, destination=destination, route=route, title=title, root=root)
        if (not root and route is not None and target != origin
                and route not in ('browser', 'remote-browser', 'folder-options', 'workspace-browser')):
            # Opening a file/help page is a navigation action. Merely selecting
            # another tab does not call show and must not create this return edge.
            self.origins[target, route] = origin

    def trim(self, destination, count, *, native=True):
        removed = [screen[0] for screen in self.screens[destination][count:]]
        super().trim(destination, count, native=native)
        for route in removed:
            self.origins.pop((destination, route), None)
            self.folders.forget(destination, route)

    def return_to(self, destination):
        if self.app.select_destination(destination) is not False:
            self.host.activate(destination)
            self.render(destination)

    def back(self):
        screens = self.screens[self.host.state.destination]
        if screens and screens[-1][0].startswith(('private-close:', 'close:')):
            self.app.keep_reader_editing(screens[-1][0].split(':')[1])
            return True
        key = self.app.visible_reader()
        if key is not None:
            self.app.request_reader_close(key)
            return True
        destination = self.host.state.destination
        screens = self.screens[destination]
        count = len(screens)
        origin = self.origins.get((destination, screens[-1][0])) if screens else None
        handled = super().back()
        if self.apple and len(screens) < count:
            self.folders.restore(destination)
        if origin is not None and len(screens) < count:
            self.return_to(origin)
        if self.apple and len(screens) < count and screens:
            self.app.loop.call_soon(self.folders.restore_viewport, destination, screens[-1][0])
        return handled

    def install(self):
        if self.apple or self.host.adapter is None:
            return super().install()
        from java import dynamic_proxy
        from io.github.ispaure.commonutils import NavigationBack

        class Listener(dynamic_proxy(NavigationBack.Listener)):
            def __init__(self, owner):
                super().__init__()
                self.owner = weakref.ref(owner)

            def onBackRequested(self):
                owner = self.owner()
                return owner.system_back() if owner is not None else False

        self.listener = Listener(self)
        self.back_callback = NavigationBack.install(self.host.adapter.impl._native_activity, self.listener)
        self.selection_changed()
        if self.on_render is not None:
            self.on_render()

    def native_popped(self, navigation):
        destination = self.host.destinations[self.host.adapter.navigation.index(navigation)]
        screens = self.screens[destination]
        count = len(screens)
        previous = screens[-1][0] if screens else ''
        origin = self.origins.get((destination, screens[-1][0])) if screens else None
        super().native_popped(navigation)
        popped = len(screens) < count
        if (len(screens) == count - 1
                and previous.startswith(('private-close:', 'close:'))):
            # UIKit's own Back button bypasses back(); cancelling a close
            # prompt must retire the pending exit intent through the same path.
            self.app.keep_reader_editing(previous.split(':')[1])
        if popped:
            self.folders.restore(destination)
        if origin is not None and len(screens) < count:
            self.return_to(origin)
        # UIKit can re-enable its pop recognizers when a push completes too.
        # Reapply reader ownership after the navigation delegate has returned.
        expected = screens[-1][0] if popped and screens else None
        def reflow():
            self.app.adaptive.render()
            if expected is not None:
                # UIKit and the native reader bars can move a retained table's
                # offset during the final layout without changing its bounds.
                self.folders.restore_viewport(destination, expected)
        self.app.loop.call_soon(reflow)

    def sync_back(self, destination=None):
        if self.back_callback is not None:
            destination = destination or self.host.state.destination
            # At Home's root, leave the callback disabled so Android owns exit
            # and its back-to-home preview. Tab selection never creates history.
            self.back_callback.setEnabled(destination != 'home' or bool(self.screens[destination]))

    def selection_changed(self):
        super().selection_changed()
        self.sync_back()

    def invoke_back(self, callback):
        self.app.mark_navigation()
        result = callback()
        if inspect.isawaitable(result):
            async def complete():
                try:
                    await result
                finally:
                    self.back_task = None
                    self.sync_back()
            self.back_task = self.app.loop.create_task(complete())
        self.sync_back()
        return True

    def system_back(self):
        """Dismiss transient UI, retrace the visible panel, then Home, then OS.

        Toolbar Back/Cancel still call Routes.back directly: cancelling a form
        must pop that form rather than consume a retained browser's history.
        Native dialogs, popup menus and the IME keep Android's own dismissal.
        """
        if self.back_task is not None:
            return True
        if not self.guard():
            return True
        app, destination = self.app, self.host.state.destination
        body = self.body()

        for overlay in tuple(getattr(app, '_speech_overlays', ())):
            if overlay.panel.overlay is overlay:
                overlay.panel.hide()
                return True

        adaptive = app.adaptive
        view = body.children[0] if body.children else None
        if (not adaptive.wide and adaptive.menu_open.get(destination, False)
                and getattr(view, '_workspace_frame', None) is not None):
            return self.invoke_back(lambda: adaptive.toggle(destination))
        if (destination == 'chat' and contains(body, getattr(app, 'chat_view', None))
                and adaptive.width() < 640 and app.chat_drawer_open):
            return self.invoke_back(app.toggle_chat_conversations)

        # Search is presentation state, not a reason to leave an editor.
        for owner in app.text_views.values():
            search = owner.search
            if contains(body, search.box):
                return self.invoke_back(search.toggle)

        for name in ('documentation', 'vault_browser'):
            owner = getattr(app, name, None)
            if owner is None or not contains(body, owner.view):
                continue
            sidebar = owner.sidebar
            if not sidebar.expanded and sidebar.sidebar_open and owner.path is not None:
                def close_sidebar():
                    sidebar.show_detail()
                    if name == 'documentation':
                        owner.reading = True
                return self.invoke_back(close_sidebar)
            if owner.history_index > 0:
                return self.invoke_back(lambda: owner.navigate_history(-1))

        for browser_name, path_name, parent in (
                ('file_browser', 'file_path', app.parent_file_folder),
                ('remote_browser', 'cloud_path', app.parent_cloud)):
            browser = getattr(app, browser_name, None)
            if browser is None or not contains(body, browser.widget):
                continue
            if browser.search.value:
                return self.invoke_back(lambda: setattr(browser.search, 'value', ''))
            if browser.search_open:
                return self.invoke_back(browser.close_search)
            if browser.history.previous() is not None:
                return self.invoke_back(browser.go_back)
            # A direct Workspaces shortcut may have no earlier folder visit.
            if getattr(app, path_name, ''):
                return self.invoke_back(parent)

        readers = getattr(app, 'readers', None)
        reader = readers.active if readers is not None else None
        if reader is not None and contains(body, getattr(reader, 'library_view', None)):
            chapters = getattr(reader, 'chapter_sidebar', None)
            if chapters is not None and not chapters.expanded and chapters.sidebar_open:
                return self.invoke_back(chapters.show_detail)

        private = getattr(app, 'private_sessions', None)
        reader = private.active if private is not None else None
        if reader is not None and contains(body, getattr(reader, 'crypt_view', None)):
            epub = getattr(reader, 'provider_epub_view', None)
            if epub is not None and contains(body, getattr(epub, 'find_box', None)):
                return self.invoke_back(epub.close_find)
            chapters = getattr(epub, 'sidebar', None)
            if chapters is not None and not chapters.expanded and chapters.sidebar_open:
                return self.invoke_back(chapters.show_detail)
            tools = getattr(epub, 'tools', None)
            if chapters is None and tools is not None and contains(body, tools.panel):
                return self.invoke_back(tools.close)
            tools = getattr(reader, 'pdf_tools', None)
            if tools is not None and contains(body, tools.panel):
                return self.invoke_back(tools.close)

        key = app.visible_reader()
        if key is not None:
            return self.invoke_back(lambda: app.request_reader_close(key))

        if self.screens[destination]:
            cancel = getattr(app, '_cancel_transfer_review', None)
            if cancel is not None and contains(body, getattr(app, '_transfer_review_view', None)):
                cancel()
            return self.back()
        if destination != 'home':
            return self.invoke_back(lambda: self.return_to('home'))
        return False
