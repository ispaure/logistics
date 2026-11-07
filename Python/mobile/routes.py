"""Logistics reader gestures and Back policy over destination-local routes."""
import asyncio
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
        self._retired = False
        self._installation = object()
        self.origins = {}
        self._selection_returns = {}
        from .folder_navigation import FolderNavigation
        self.folders = FolderNavigation(self)
        super().__init__(*args, **kwargs)

    def uninstall(self):
        if not self._retired:
            self._retired = True
            task, self.back_task = self.back_task, None
            if (task is not None and not task.done()
                    and not (isinstance(task, asyncio.Task) and task.cancelling())):
                # Cancel once: a repeated native cleanup must not interrupt a
                # feature callback that is still draining its worker in finally.
                task.cancel()
        volume = getattr(self, 'volume_pages', None)
        if volume is not None:
            volume.dispose()
            self.volume_pages = None
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
        self.retire_other_presentations(view, target, route)
        super().show(view, destination=destination, route=route, title=title, root=root)
        if (not root and route is not None and target != origin
                and route not in ('browser', 'remote-browser', 'folder-options', 'workspace-browser')):
            # Opening a file/help page is a navigation action. Merely selecting
            # another tab does not call show and must not create this return edge.
            self.origins[target, route] = origin

    def retire_other_presentations(self, view, target, route):
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
        # iOS Documents keeps readers in a separate secondary stack. Retire
        # that presentation too before moving its widget to another tab.
        if target != 'documents':
            details = getattr(self.app.adaptive, 'detail_routes', ())
            index = next((i for i, (_, panel, _) in enumerate(details)
                          if any(mode in panel.children for mode in presentations)), None)
            if index is not None:
                self.app.adaptive.trim_details(index)
                if view.parent is not None:
                    view.parent.remove(view)

    def retire_destination_picker(self, destination):
        """Retire an earlier form without losing folders opened above it."""
        screens = self.screens[destination]
        removed = [screen for screen in screens if screen[0] == 'text-destination']
        if not removed:
            return
        retained = [screen for screen in screens if screen[0] != 'text-destination']
        changing = self.changing
        self.changing = True
        try:
            if self.apple:
                adapter = self.host.adapter
                root = adapter.containers[self.host.destinations.index(destination)][1]
                adapter.navigation_for(destination).setViewControllers(
                    [root, *(pane.controller for _, _, pane in retained)], animated=False)
            screens[:] = retained
            self.host.state.routes[destination] = [route for route, _, _ in retained]
            for _, _, pane in removed:
                if pane is not None:
                    self.host.adapter.release_pane(pane)
        finally:
            self.changing = changing
        self.origins.pop((destination, 'text-destination'), None)
        self.folders.forget(destination, 'text-destination')
        if any(self._selection_returns.get(destination) is panel for _, panel, _ in removed):
            self._selection_returns[destination] = self.body(destination)
        self.render(destination)

    def trim(self, destination, count, *, native=True):
        library = getattr(self.app, 'vault_browser', None)
        action_view = getattr(library, 'file_action_view', None)
        removed_action = action_view is not None and any(
            contains(panel, action_view) for _, panel, _ in self.screens[destination][count:])
        library_view = getattr(library, 'view', None)
        removed_library = library_view is not None and any(
            contains(panel, library_view) for _, panel, _ in self.screens[destination][count:])
        removed = [screen[0] for screen in self.screens[destination][count:]]
        if 'import-credentials-password' in removed:
            owner = self.app.__dict__.get('_cloud_controller')
            if owner is not None:
                owner.credential_workflow.cancel_import()
        if any(route in ('browser', 'remote-browser', 'workspace-browser')
               or route.startswith(('folder:', 'notes-library:')) for route in removed):
            # A retained browser may reopen the same folder after Back. Its
            # Notes choice belongs to the visit, not the browser's lifetime.
            for name in ('file_browser', 'remote_browser'):
                browser = getattr(self.app, name, None)
                if browser is not None:
                    browser._notes_location = None
        super().trim(destination, count, native=native)
        if removed_action or removed_library:
            library.clear_file_action()
        for route in removed:
            self.origins.pop((destination, route), None)
            self.folders.forget(destination, route)
        if removed:
            self._selection_returns[destination] = self.body(destination)

    def render(self, destination):
        super().render(destination)
        self.flush_return_selection(destination)

    def flush_return_selection(self, destination):
        panel = self._selection_returns.pop(destination, None)
        if panel is self.body(destination):
            self.clear_return_selection(destination)

    def clear_return_selection(self, destination):
        """A returned screen keeps its viewport but starts without a selection."""
        self.clear_view_selection(self.body(destination))

    @staticmethod
    def clear_view_selection(view):
        """Clear only transient selections explicitly owned by this subtree."""
        def clear(view):
            callback = getattr(view, '_clear_return_selection', None)
            if callback is not None:
                callback()
                return
            if isinstance(view, toga.ScrollContainer) and view.content is not None:
                clear(view.content)
            else:
                for child in view.children:
                    clear(child)
        clear(view)

    def return_to(self, destination):
        if self.app.select_destination(destination) is not False:
            self.host.activate(destination)
            adaptive = self.app.adaptive
            if (destination == 'documents' and adaptive.split is not None
                    and adaptive.in_detail and adaptive.detail_routes):
                self.app.route_changed(adaptive.detail_routes[-1][1])
            else:
                self.render(destination)

    def back(self):
        if self._retired:
            return False
        if (self.host.state.destination == 'documents'
                and not self.screens['documents']
                and not getattr(self.app.adaptive, 'in_detail', False)
                and (getattr(self.app, 'documents_search_open', False)
                     or bool(getattr(self.app, 'documents_query', '').strip()))):
            self.app.close_document_search()
            return True
        library = getattr(self.app, 'vault_browser', None)
        if library is not None and contains(self.body(), getattr(library, 'file_action_view', None)):
            if not self.guard():
                return True
            # File forms return to their originating pane for toolbar Back
            # and the Android system-Back fallback alike.
            library.return_from_file_action()
            return True
        picker = getattr(self.app, '_editor_picker', None)
        if picker is not None and picker.visible(self.body()):
            if (picker.location_panel is not None and picker.panel is picker.location_panel and not picker.cloud_busy
                    and not picker.creation_layout.paired):
                picker.show_creation_name()
            else:
                picker.cancel_text_destination()
            return True
        screens = self.screens[self.host.state.destination]
        if screens and screens[-1][0].startswith(('private-close:', 'close:')):
            self.app.keep_reader_editing(screens[-1][0].split(':')[1])
            return True
        tool = self.app.reader_tool_back(self.body())
        if tool is not None:
            tool()
            self.app.adaptive.render()
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
        if len(screens) < count:
            self.folders.restore(destination)
        if origin is not None and len(screens) < count:
            self.return_to(origin)
        if self.apple and len(screens) < count and screens:
            expected = screens[-1][0]
            installation = self._installation
            def restore():
                if not self._retired and self._installation is installation:
                    self.folders.restore_viewport(destination, expected)
            self.app.loop.call_soon(restore)
        return handled

    def install(self):
        self._installation = object()
        self._retired = False
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
        from .android_volume_pages import VolumePages
        self.volume_pages = VolumePages(self.app)
        self.selection_changed()
        if self.on_render is not None:
            self.on_render()

    def native_popped(self, navigation):
        if self._retired or self.changing or self.host.changing:
            return
        destination = self.host.adapter.destination_for_navigation(navigation)
        if destination is None:
            return
        screens = self.screens[destination]
        count = len(screens)
        previous = screens[-1][0] if screens else ''
        library = getattr(self.app, 'vault_browser', None)
        action_view = getattr(library, 'file_action_view', None)
        action_side = (getattr(library, 'file_action_side', None)
                       if action_view is not None and contains(self.body(destination), action_view) else None)
        origin = self.origins.get((destination, screens[-1][0])) if screens else None
        super().native_popped(navigation)
        popped = len(screens) < count
        if (popped and action_side is not None and library.valid()
                and self.host.state.destination == destination and contains(self.body(destination), library.view)):
            library.sidebar.show(action_side)
        if popped and previous == 'text-destination':
            picker = getattr(self.app, '_editor_picker', None)
            if picker is not None:
                picker.cancel_text_destination(dismissed=True)
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
        installation = self._installation
        def reflow():
            if self._retired or self._installation is not installation:
                return
            self.app.adaptive.render()
            if expected is not None:
                # UIKit and the native reader bars can move a retained table's
                # offset during the final layout without changing its bounds.
                self.folders.restore_viewport(destination, expected)
        self.app.loop.call_soon(reflow)

    def sync_back(self, destination=None):
        if not self._retired and self.back_callback is not None:
            destination = destination or self.host.state.destination
            # At Home's root, leave the callback disabled so Android owns exit
            # and its back-to-home preview. Tab selection never creates history.
            video = getattr(self.app, 'video_player', None)
            self.back_callback.setEnabled((video is not None and not video.closed and not video.hidden)
                                          or destination != 'home' or bool(self.screens[destination]))

    def selection_changed(self):
        super().selection_changed()
        self.sync_back()

    def invoke_back(self, callback):
        if self._retired:
            return False
        self.app.mark_navigation()
        result = callback()
        if inspect.isawaitable(result):
            # Schedule the callback itself so cancellation before its first
            # step cannot strand an unawaited coroutine inside a wrapper.
            task = self.back_task = asyncio.ensure_future(result, loop=self.app.loop)
            def complete(completed):
                if self.back_task is completed:
                    self.back_task = None
                    if not self._retired:
                        self.sync_back()
            task.add_done_callback(complete)
        self.sync_back()
        return True

    def system_back(self):
        """Dismiss transient UI, retrace the visible panel, then Home, then OS.

        Toolbar Back/Cancel still call Routes.back directly: cancelling a form
        must pop that form rather than consume a retained browser's history.
        Native dialogs, popup menus and the IME keep Android's own dismissal.
        """
        if self._retired:
            return False
        if self.back_task is not None:
            return True
        video = getattr(self.app, 'video_player', None)
        if video is not None and not video.closed and not video.hidden:
            return self.invoke_back(video.close)
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

        picker = getattr(app, '_editor_picker', None)
        if picker is not None and picker.visible(body) and picker.panel is not picker.name_panel:
            if picker.new_folder_form in picker.save_as_view.children and not picker.cloud_busy:
                return self.invoke_back(picker.hide_new_folder)
            action = picker.editor_browser.back_action()
            if action is not None:
                return self.invoke_back(action)
            if picker.has_parent_folder():
                return self.invoke_back(picker.parent_editor_folder)

        # Search is presentation state, not a reason to leave an editor.
        for owner in app.text_views.values():
            search = owner.search
            if contains(body, search.box):
                return self.invoke_back(owner.toggle_search)

        for name in ('documentation', 'vault_browser'):
            owner = getattr(app, name, None)
            if owner is None or not contains(body, owner.view):
                continue
            action = owner.back_action()
            if action is not None:
                return self.invoke_back(action)

        drawer = adaptive.browsers.get(destination)
        if drawer is not None and contains(body, drawer.browser_widget):
            action = drawer.back_action()
            if action is not None:
                return self.invoke_back(action)

        for browser_name, path_name, parent in (
                ('file_browser', 'file_path', app.parent_file_folder),
                ('remote_browser', 'cloud_path', app.parent_cloud)):
            browser = getattr(app, browser_name, None)
            if browser is None or not contains(body, browser.widget):
                continue
            if (browser_name == 'file_browser' and not browser.search.value and not browser.search_open
                    and (app.file_storage.value, app.file_path)
                    == getattr(app.files_view, '_folder_entry_location', None)
                    and browser.history.current in (None, (app.file_storage.value, app.file_path))):
                return self.invoke_back(app.show_locations)
            action = browser.back_action()
            if action is not None:
                return self.invoke_back(action)
            # A direct Workspaces shortcut may have no earlier folder visit.
            if getattr(app, path_name, ''):
                async def ascend(browser=browser, parent=parent, path_name=path_name):
                    previous = getattr(app, path_name, '')
                    await parent()
                    if getattr(app, path_name, '') != previous:
                        # Ascending from a direct shortcut must not create a
                        # Back entry into the child we have just left.
                        browser.history.locations[:] = browser.history.locations[-1:]
                return self.invoke_back(ascend)

        if (destination == 'documents' and not self.screens[destination]
                and not getattr(adaptive, 'in_detail', False)
                and (getattr(app, 'documents_search_open', False)
                     or bool(getattr(app, 'documents_query', '').strip()))):
            return self.invoke_back(app.close_document_search)

        action = app.reader_back_action(body)
        if action is not None:
            return self.invoke_back(action)

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
