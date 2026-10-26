"""Compact Logistics presentation over the shared native browser."""
import weakref
import asyncio
from threading import Event
from pathlib import PurePosixPath
import toga
from .control_icons import apply_icon
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from commonUtils.ui.native_browser.recycled import RecycledBrowser, BrowserPresentation
from .appearance import list_button
from .appearance import accessible_name, surface, template_icon, selection_row
from .hub_icons import icon
from .folder_hub_style import (
    ENTRY_ICON_SIZE, ENTRY_ICON_MARGIN,
)


def browser_command(button):
    """Use normal accent navigation, retaining outlines for Android E Ink."""
    return surface(button, radius=8, background='transparent', foreground='accent',
                   outlined=False, eink_outlined=True)


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
    surface(image, radius=0, background='transparent', foreground='accent',
            outlined=False, eink_outlined=False)
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


class BrowserStatusLabel(toga.Label):
    """Plain browser text with the value interface used by workflow status."""
    def __init__(self, value='', *, shrink=True, **kwargs):
        super().__init__(value, **kwargs)
        self.style.flex = 1
        self.style.margin_left = 6
        self.style.margin_right = 8
        backend = type(self._impl).__module__
        if backend.startswith('toga_iOS.'):
            self._impl.native.lineBreakMode = 5  # Middle ellipsis for long folder names.
        elif backend.startswith('toga_android.'):
            from android.text import TextUtils
            self._impl.native.setSingleLine(True)
            self._impl.native.setEllipsize(TextUtils.TruncateAt.MIDDLE)
        surface(self, radius=0, background='transparent', foreground='text',
                outlined=False, eink_outlined=False)
        if not shrink:
            return
        # Native labels measure the whole single-line string. Let Pack shrink
        # that text so the adjacent parent/search controls stay on screen.
        from travertino.size import at_least
        self.intrinsic.width = at_least(0)
        native_rehint = getattr(type(self._impl), 'rehint', None)
        if native_rehint is not None:
            reference = weakref.ref(self)
            def rehint():
                target = reference()
                if target is not None:
                    native_rehint(target._impl)
                    target.intrinsic.width = at_least(0)
            self._impl.rehint = rehint

    @property
    def value(self):
        return self.text

    @value.setter
    def value(self, value):
        self.text = value
        changed = getattr(self, 'status_changed', None)
        if changed is not None:
            changed()


class FolderLocationHeader(toga.Box):
    """Current storage identity and a Back control."""
    def __init__(self, status, parent_button, *, actions=()):
        self.parent_button = parent_button
        self.folder_name = BrowserStatusLabel('Root', style=Pack(font_size=18, font_weight='normal'))
        self.status = status
        self.folder_name.style.flex = self.status.style.flex = 0
        self.folder_name.style.margin_left = self.status.style.margin_left = 0
        self.status.style.font_size = self.folder_name.style.font_size * .75
        # Let native font metrics (including Android font scaling/padding)
        # determine text height. Only the decorative icons have a fixed size.
        del self.status.style.height
        self.status.style.margin = 0
        surface(self.status, radius=0, background='transparent', foreground='muted',
                outlined=False, eink_outlined=False)
        self.storage_icons = toga.Box(style=Pack(direction=ROW, align_items=CENTER, height=18))
        self.storage_identity = toga.Box(style=Pack(direction=ROW, align_items=CENTER))
        self.caption = toga.Box(children=[self.folder_name],
                                style=Pack(direction=COLUMN, flex=1, margin_left=6))
        self.status.status_changed = self.refresh_status
        self.refresh_status()
        super().__init__(children=[parent_button, self.caption, *actions],
                         style=Pack(direction=ROW, align_items=CENTER, margin_top=0))
        if type(self._impl).__module__.startswith('toga_android.'):
            self.use_android_title()
        self.update('')

    def use_android_title(self):
        """Match the compact centered iOS identity without changing touch targets."""
        self._android_title = True
        self.folder_name.style.font_size = 17
        self.status.style.font_size = 17 * .75
        self.folder_name.style.text_align = self.status.style.text_align = CENTER
        self.folder_name.style.margin_right = 0
        self.storage_icons.style.height = 15
        self.balance_android_title()

    def balance_android_title(self):
        if self.caption not in self.children:
            return
        if not hasattr(self, '_title_gutters'):
            self._title_gutters = [toga.Box(style=Pack(width=0)), toga.Box(style=Pack(width=0))]
            super().insert(1, self._title_gutters[0])
            super().add(self._title_gutters[1])
        def action_width(child):
            width = child.style.width
            # Drawer buttons can use Pack's 'none' width. Use the standard
            # touch target when there is no explicit numeric action width.
            return width if isinstance(width, (int, float)) and width > 0 else 48
        trailing = sum(action_width(child) for child in self.children
                       if child not in (self.parent_button, self.caption, *self._title_gutters))
        leading = action_width(self.parent_button)
        self.caption.style.margin_left = self.caption.style.margin_right = 0
        self._title_gutters[0].style.width = max(0, trailing - leading)
        self._title_gutters[1].style.width = max(0, leading - trailing)

    def add(self, *children):
        super().add(*children)
        if getattr(self, '_android_title', False):
            self.balance_android_title()

    def remove(self, *children):
        super().remove(*children)
        if getattr(self, '_android_title', False):
            self.balance_android_title()

    def use_native_title(self):
        """Let UIKit own the title/actions; reserve content space only for search."""
        if getattr(self, 'native_actions', None) is not None:
            return
        self.title_actions = tuple(child for child in self.children
                                   if child not in (self.parent_button, self.caption))
        for child in list(self.children):
            self.remove(child)
        self.caption.remove(self.folder_name)
        self.caption.style.flex = 0
        self.caption.style.margin_left = 0
        self.status.style.text_align = CENTER
        self.style.margin_top = 0
        self.center_storage_identity()
        self.style.direction = COLUMN
        del self.style.align_items
        self.native_actions = toga.Box(style=Pack(direction=ROW, align_items=CENTER))
        self.add(self.caption)

    def center_storage_identity(self):
        # Equal flexible gutters center the icon/text group within the row.
        if not hasattr(self, '_identity_gutters'):
            self._identity_gutters = [toga.Box(style=Pack(flex=1)), toga.Box(style=Pack(flex=1))]
        for gutter in self._identity_gutters:
            if gutter in self.storage_identity.children:
                self.storage_identity.remove(gutter)
        self.storage_identity.children[-1].style.flex = 0
        del self.storage_identity.children[-1].style.width
        self.storage_identity.insert(0, self._identity_gutters[0])
        self.storage_identity.add(self._identity_gutters[1])

    def refresh_status(self):
        """Use one secondary line for operation text or passive storage identity."""
        if getattr(self, '_native_title_mounted', False):
            if self.status.text and self.caption not in self.children:
                self.insert(0, self.caption)
            elif not self.status.text and self.caption in self.children:
                self.remove(self.caption)
        visible = self.status if self.status.text else self.storage_identity
        for child in (self.status, self.storage_identity):
            if child is not visible and child in self.caption.children:
                self.caption.remove(child)
        if visible not in self.caption.children:
            self.caption.add(visible)

    def update(self, path, *, remote=False, encrypted=False, unlocked=False, name=None, session_only=False):
        self.folder_name.value = name if name is not None else PurePosixPath(path).name if path else 'Root'
        apply_icon(self.parent_button, 'back', 'Back')
        browser_command(self.parent_button)
        kinds = [('storage_remote', 'Online folder')] if remote else [('storage_local', 'On-device folder')]
        if encrypted:
            state = 'unlocked' if unlocked else 'locked'
            kinds.append(('folder_' + state, 'Encrypted folder, ' + state))
        identity_key = (remote, encrypted, unlocked, session_only)
        if identity_key == getattr(self, '_identity_key', None):
            return
        for child in list(self.storage_icons.children):
            self.storage_icons.remove(child)
        for child in list(self.storage_identity.children):
            self.storage_identity.remove(child)
        self.storage_identity.add(self.storage_icons)
        for name, label in kinds:
            size = 12 if type(self._impl).__module__.startswith('toga_android.') else 18
            indicator = template_icon(toga.ImageView(icon(name), style=Pack(width=size, height=size, margin_right=4)))
            indicator.control_icon = name
            accessible_name(indicator, label)
            surface(indicator, radius=0, background='transparent',
                    foreground=name if name.startswith('folder_') else 'accent',
                    outlined=False, eink_outlined=False)
            self.storage_icons.add(indicator)
        identity = 'Cloud' if remote else 'On-device'
        if encrypted:
            state = 'Unlocked (Session Only)' if unlocked and session_only else 'Unlocked' if unlocked else 'Locked'
            identity += ' · ' + state
            if not remote:
                identity += ' · LocalCrypt'
        self.storage_identity.add(BrowserStatusLabel(identity, style=Pack(
            font_size=self.folder_name.style.font_size * .75, margin=0)))
        surface(self.storage_identity.children[-1], radius=0, background='transparent', foreground='muted',
                outlined=False, eink_outlined=False)
        if type(self._impl).__module__.startswith('toga_android.'):
            self.center_android_identity(identity)
        elif getattr(self, 'native_actions', None) is not None:
            self.center_storage_identity()
        self._storage_kinds = kinds
        self._identity_key = identity_key

    def center_android_identity(self, identity):
        """Center icons with their caption as one ellipsizing native text run."""
        from android.text import SpannableString
        from android.text.style import ImageSpan
        label = self.storage_identity.children[-1]
        label.style.margin = 0
        label.style.text_align = CENTER
        # Inline spans keep the complete icon/text group centered. Separate
        # flexible labels either strand icons at the edge or hide long text.
        text = SpannableString('\ufffc ' * len(self.storage_icons.children) + identity)
        for index, image in enumerate(self.storage_icons.children):
            drawable = image._impl.native.getDrawable()
            size = round(image._impl.scale_in(12))
            drawable.setBounds(0, 0, size, size)
            text.setSpan(ImageSpan(drawable, 1), index * 2, index * 2 + 1, 33)
        self.storage_identity.remove(self.storage_icons)
        label._impl.native.setText(text)
        label._impl.native.setContentDescription(', '.join(
            image.accessible_name for image in self.storage_icons.children) + '. ' + identity)

    def update_provider(self, path, provider, *, name=None):
        provider = getattr(provider, 'provider', provider)
        remote = getattr(provider, 'remote_storage', False)
        encrypted = bool(getattr(provider, 'private', False))
        if not path and encrypted and not remote:
            name = getattr(provider, 'remote', name)
        self.update(path, remote=remote, encrypted=encrypted, unlocked=True,
                    name=name, session_only=provider_session_only(provider))


def provider_session_only(provider):
    """Read the loaded credential publication without querying the bridge."""
    provider = getattr(provider, 'provider', provider)
    remote = getattr(provider, 'remote', None)
    records = getattr(getattr(provider, 'client', None), 'package_records', ())
    return any(remote in record.get('remotes', ()) and not record.get('saved', False)
               for record in records)


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
                         list_factory=RecycledFileList, inline_details=False, **kwargs)
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
