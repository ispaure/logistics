"""Compact Logistics presentation over the shared native browser."""
import asyncio
from threading import Event
import toga
from .control_icons import apply_icon
from toga.style import Pack
from commonUtils.ui.native_browser.recycled import RecycledBrowser, BrowserPresentation
from .appearance import list_button
from .appearance import surface, template_icon, selection_row
from .browser_location import (
    BrowserStatusLabel as BrowserStatusLabel,
    FolderLocationHeader as FolderLocationHeader,
    FolderNameLabel as FolderNameLabel,
    browser_command as browser_command,
    provider_session_only as provider_session_only,
)
from .hub_icons import icon
from .folder_hub_style import (
    ENTRY_ICON_SIZE, ENTRY_ICON_MARGIN,
)


def middle_filename(button):
    """Let the native label fit the middle ellipsis without changing identity."""
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        button._impl.native.titleLabel.lineBreakMode = 5  # NSLineBreakByTruncatingMiddle
        button._impl.native.accessibilityLabel = button.text
    elif backend.startswith('toga_android.'):
        from android.text import TextUtils
        button._impl.native.setSingleLine(True)
        button._impl.native.setEllipsize(TextUtils.TruncateAt.MIDDLE)
        button._impl.native.setContentDescription(button.text)


def entry_icon(directory, *, landing_page=False):
    """A consistent folder/file glyph for ordinary and Notes Library rows."""
    kind = 'folder_document' if directory and landing_page else 'files' if directory else 'documents'
    image = template_icon(toga.ImageView(icon(kind),
        style=Pack(width=ENTRY_ICON_SIZE, height=ENTRY_ICON_SIZE,
                   margin_left=ENTRY_ICON_MARGIN, margin_right=ENTRY_ICON_MARGIN)))
    image.browser_entry_kind = 'folder_document' if directory and landing_page else 'folder' if directory else 'file'
    surface(image, radius=0, background='transparent', foreground='file_icon',
            outlined=False, eink_outlined=False)
    return image


def breadcrumb_separator():
    """A passive, theme-tinted File Browser chevron."""
    image = template_icon(toga.ImageView(icon('breadcrumb_chevron'), style=Pack(width=14, height=14)))
    surface(image, radius=0, background='transparent', foreground='muted',
            outlined=False, eink_outlined=False)
    backend = type(image._impl).__module__
    if backend.startswith('toga_iOS.'):
        image._impl.native.isAccessibilityElement = False
    elif backend.startswith('toga_android.'):
        from android.view import View
        image._impl.native.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO)
    return image


def highlight_entry(widget, selected):
    if not isinstance(widget, toga.Button):
        selection_row(widget, selected)
        return
    surface(widget, radius=8, background='hover' if selected else 'surface',
            foreground='muted' if getattr(widget, 'browser_hidden', False) else 'text',
            outlined=False, eink_outlined=selected, eink_selected=selected)


def sync_browser_population(app, body=None):
    """Compatibility hook for retained route/privacy lifecycle callers."""
    # Native lists own their viewport; there is no Python population timer.
    return


class LogisticsBrowserPresentation(BrowserPresentation):
    command = staticmethod(apply_icon)
    command_style = staticmethod(browser_command)
    entry_icon = staticmethod(entry_icon)
    style_button = staticmethod(list_button)
    middle_filename = staticmethod(middle_filename)
    highlight = staticmethod(highlight_entry)

    def file_icon(self, folder):
        from .recycled_file_list import file_list_icon
        return file_list_icon(folder)

class FileBrowser(RecycledBrowser):
    def __init__(self, *, folder_visible=None, local_search=None, **kwargs):
        self._resource_provider = None
        self._release_resource = lambda: None
        from functools import partial
        from .recycled_file_list import RecycledFileList
        self.folder_visible = folder_visible
        if local_search is None and getattr(toga.App.app, 'private_root', None) is not None:
            from .local_search import LocalSearch
            local_search = LocalSearch(toga.App.app.private_root / 'Cache' / 'directory-index.sqlite3')
        self.local_search = local_search
        self._index_cancel = Event()
        self._index_error = None
        self._index_started = False
        if local_search is not None:
            kwargs['resource_search'] = local_search.search
        super().__init__(presentation=LogisticsBrowserPresentation(),
                         list_factory=partial(RecycledFileList, title_lines=2), inline_details=False, **kwargs)
        self.widget._clear_return_selection = self.clear_selection

    def clear_selection(self):
        """Retire contextual selection without rebuilding the retained listing."""
        self.selected = None
        for child in list(self.info.children):
            self.info.remove(child)
        self.highlight_selection()
        if self.on_selected is not None:
            result = self.on_selected(None)
            if asyncio.iscoroutine(result):
                self._spawn(result)

    def back_action(self):
        """Choose one browser-local Back step; the route owns invoking it."""
        if self.search.value:
            return lambda: setattr(self.search, 'value', '')
        if self.search_open:
            return self.close_search
        if self.history.previous() is not None:
            return self.go_back
        return None

    def set_entries(self, provider, directory, rows, *, location=None):
        changed = provider is not self._resource_provider
        release = (provider.acquire() if hasattr(provider, 'acquire') else lambda: None) if changed else None
        self._index_cancel.set()
        self._index_cancel = Event()
        self._index_error = None
        self._index_started = False
        try:
            super().set_entries(provider, directory, rows, location=location)
        except BaseException:
            if release is not None:
                release()
            raise
        if changed:
            previous = self._release_resource
            self._resource_provider, self._release_resource = provider, release
            previous()
        if self.search_open:
            self._start_local_index()

    async def _search_subfolders(self, epoch, cancelled):
        # Online search filters the loaded listing; recursive I/O is explicit.
        if getattr(self.search_provider, 'remote_storage', False):
            return
        await super()._search_subfolders(epoch, cancelled)

    def _start_local_index(self):
        provider = self.search_provider
        if (not self._index_started and provider is not None and self.local_search is not None
                and self.local_search.supports(provider)):
            self._index_started = True
            self._index_cancel = Event()
            self._spawn(self._prepare_local_search(provider, self.search_directory, self._index_cancel))

    async def _prepare_local_search(self, provider, directory, cancelled):
        from commonUtils.runtime.operations import OperationCancelled
        try:
            await asyncio.to_thread(self.local_search.prepare, provider, directory,
                                    cancelled=cancelled.is_set)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except OperationCancelled:
            return
        except Exception as error:
            if not cancelled.is_set():
                self._index_error = str(error)
                self.page_label.text = 'Search index update failed: ' + self._index_error[:80]
            return
        if not self.closed and not cancelled.is_set() and self.search.value:
            # Replace partial/cached results after reconciliation, including
            # updates which keep the same number of matching files.
            self.query_changed()

    def stop(self):
        header = getattr(self, 'location_bar', None)
        if header is not None:
            header.clear_location()
        self.stop_local_search()
        super().stop()
        self._release_resource()
        self._resource_provider = None
        self._release_resource = lambda: None

    def stop_local_search(self):
        self._index_cancel.set()
        self.search_cancelled.set()

    location_header = FolderLocationHeader

    status_label = BrowserStatusLabel

    def attach_location_header(self, status, parent_button):
        for action in (self.search_button,):
            if action.parent is not None:
                action.parent.remove(action)
        self.location_bar = self.location_header(status, parent_button,
            actions=(self.search_button,))
        # The visible control follows the same state history as Android Back.
        fallback = parent_button.on_press
        def back(widget=None, **kwargs):
            routes = getattr(parent_button.app or toga.App.app, 'routes', None)
            if routes is not None and not routes.apple:
                return routes.system_back()
            # Toga's retained handler already binds this button as its first
            # argument; forwarding it again breaks native Apple callbacks.
            return fallback(**kwargs)
        parent_button.on_press = back
        # The explicit Back control replaces the generic browser history row.
        if self.navigation_controls in self.widget.children:
            self.widget.remove(self.navigation_controls)
        return self.location_bar

    @property
    def entries(self):
        if self._render_entries is not None:
            return self._render_entries
        rows = super().entries
        if self.folder_visible is None:
            return rows
        provider = getattr(self, 'search_provider', None)
        remote = getattr(getattr(provider, 'provider', provider), 'remote', '')
        if not self.folder_visible(remote):
            return []
        return [entry for entry in rows if self.folder_visible(
            entry.payload.get('path', entry.label), directory=entry.container)]

    @property
    def search_open(self):
        return self.search_panel.parent is not None

    def toggle_search(self, widget=None, **kwargs):
        if self.search_open:
            self.close_search()
        else:
            self.open_search()

    def open_search(self, widget=None, **kwargs):
        if not self.search_open:
            header = getattr(self, 'location_bar', None)
            if header is None or getattr(header, 'native_actions', None) is None:
                # Inline folder titles/status remain above the expanding search.
                # The browser body is mounted immediately beneath that header.
                self.widget.insert(0, self.search_panel)
            else:
                toolbar = getattr(header, 'native_actions', header)
                if toolbar is not header and toolbar.parent is None:
                    header.add(toolbar)
                self.search_panel.style.flex = 1
                self._search_toolbar = toolbar
                self._search_toolbar_children = list(toolbar.children)
                for child in self._search_toolbar_children:
                    toolbar.remove(child)
                # UIKit keeps the folder title and actions in its native bar.
                toolbar.add(self.search_panel)
                for child in self._search_toolbar_children:
                    if child not in (header.parent_button, header.caption, self.search_button) and not (
                            type(child) is toga.Box and not child.children):
                        toolbar.add(child)
        if self.page_label not in self.widget.children:
            self.widget.insert(0 if hasattr(self, '_search_toolbar') else 1, self.page_label)
        self.search.focus()
        self._start_local_index()

    def close_search(self, widget=None, **kwargs):
        if type(self.search._impl).__module__.startswith('toga_iOS.'):
            # Release keyboard ownership before detaching the focused field.
            self.search._impl.native.resignFirstResponder()
        self._index_cancel.set()
        self._index_started = False
        self.search.value = ''
        if self.search_open:
            self.search_panel.parent.remove(self.search_panel)
        toolbar = getattr(self, '_search_toolbar', None)
        if toolbar is not None:
            for child in list(toolbar.children):
                toolbar.remove(child)
            toolbar.add(*self._search_toolbar_children)
            if not toolbar.children and toolbar.parent is not None:
                toolbar.parent.remove(toolbar)
            self.search_panel.style.flex = 0
            del self._search_toolbar, self._search_toolbar_children
        if self.page_label in self.widget.children:
            self.widget.remove(self.page_label)

    def show_item_menu(self, actions):
        from .action_menu import show_browser_actions
        return show_browser_actions(self, actions)
