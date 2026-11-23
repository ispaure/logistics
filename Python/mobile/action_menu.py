"""Native Apple button menus and Android anchored popup commands."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import inspect
import weakref
from pathlib import PurePosixPath
from commonUtils.ui.native.menus import NativeMenu as SharedNativeMenu
from .outbound_share import SEND
from .control_icons import ICONS, menu_drawable


_COMMAND_ICONS = {
    SEND.removesuffix('…'): 'send_file',
    'Open': 'forward', 'Open from Files': 'folder_hub', 'Details': 'info', 'Info': 'info',
    'New folder': 'folder_add', 'Change location': 'folder_hub', 'Select items': 'selected_item',
    'Move': 'move_file', 'Duplicate': 'duplicate_file', 'Rename': 'edit', 'Rename document': 'edit',
    'Archive password': 'storage_crypt', 'Create archive': 'archive', 'Extract archive': 'archive',
    'Archive': 'archive', 'Manage archive': 'archive', 'Delete': 'trash_file', 'Delete document': 'trash_file',
    'Add to Favourites': 'favourite', 'Remove from Favourites': 'favourite', 'Favourite file': 'favourite',
    'Show in folder': 'folder_hub', 'Show cached copy in folder': 'folder_hub',
    'All documents': 'view', 'File actions': 'more', 'New document': 'compose',
    'View document': 'view', 'View Markdown': 'view', 'View source text': 'view', 'Edit Markdown': 'edit',
    'Read aloud': 'speaker', 'Find and replace': 'find', 'Find in this page': 'find',
    'Find in chapter': 'find', 'Chapters and bookmarks': 'contents', 'Comic pages': 'file_tiles',
    'Pages and search': 'find', 'Appearance': 'appearance', 'Fullscreen': 'fullscreen',
    'Fit comic page': 'fit', 'Fit image': 'fit', 'Save a copy': 'duplicate_file',
    'Save As': 'duplicate_file', 'Export': 'send_file', 'Close document': 'close',
    'Edit metadata': 'edit', 'Open / Metadata': 'view', 'Reader tools': 'contents',
    'Browse documentation': 'contents', 'Parent folder page': 'up', 'Reading mode': 'fullscreen',
}


def command_icon(title):
    return _COMMAND_ICONS.get(title.removesuffix('…'))


def apple_command_image(title):
    from rubicon.objc import ObjCClass
    name = command_icon(title)
    return ObjCClass('UIImage').systemImageNamed(ICONS[name][0]) if name else None


def android_menu_context(context):
    """Resolve presentation at opening time, including live E Ink changes."""
    if context is None:
        return None
    from android.view import ContextThemeWrapper
    from .palette import eink_enabled
    name = 'LogisticsMenuContrast' if eink_enabled() else 'LogisticsMenu'
    resource = context.getResources().getIdentifier(name, 'style', context.getPackageName())
    return ContextThemeWrapper(context, resource)


def _apple_subviews(view):
    # Rubicon can expose UIKit's getter as a method until its property metadata
    # has been registered. Both forms return the same native child collection.
    children = view.subviews
    return list(children() if callable(children) else children)


class NativeMenu(SharedNativeMenu):
    """Keep platform menu behavior with Logistics' Android popup surfaces."""
    def __init__(self, button, actions, *, context, **kwargs):
        if type(button._impl).__module__.startswith('toga_android.'):
            original_context = context
            context = lambda: android_menu_context(original_context())
        super().__init__(button, actions, context=context, **kwargs)
        if self.actions and type(button._impl).__module__.startswith('toga_iOS.'):
            for (title, _), action in zip(self.actions, button._impl.native.menu.children):
                if command_icon(title):
                    action.image = apple_command_image(title)

    def popup_groups(self):
        return (self.actions,)

    def show(self, widget=None, **kwargs):
        if self.disposed:
            return
        if not type(self.button._impl).__module__.startswith('toga_android.'):
            return super().show(widget, **kwargs)
        from android.widget import PopupMenu
        from java import dynamic_proxy
        context = self.context()
        if context is None:
            return
        self.popup = PopupMenu(context, self.button._impl.native)
        menu = self
        class Listener(dynamic_proxy(PopupMenu.OnMenuItemClickListener)):
            def onMenuItemClick(self, item):
                if not menu.disposed:
                    menu.invoke(menu.actions[item.getItemId()][1])
                return True
        self.listener = Listener()
        native = self.popup.getMenu()
        force_icons = getattr(self.popup, 'setForceShowIcon', None)
        if force_icons:
            force_icons(True)
        index = 0
        groups = self.popup_groups()
        for group_id, group in enumerate(groups):
            for title, _ in group:
                item = native.add(group_id, index, index, android_command_label(title))
                icon = command_icon(title)
                if icon and force_icons:
                    item.setIcon(menu_drawable(icon, context))
                index += 1
        from android.os import Build
        if len(groups) > 1 and Build.VERSION.SDK_INT >= 28:
            native.setGroupDividerEnabled(True)
        self.popup.setOnMenuItemClickListener(self.listener)
        self.popup.show()


def android_command_label(title, *, icon_context=None):
    icon = command_icon(title) if icon_context is not None else None
    destructive = title.startswith('Delete')
    if not icon and not destructive:
        return title
    from android.text import SpannableString
    prefix = '  ' if icon else ''
    label = SpannableString(prefix + title)
    if icon:
        from android.text.style import ImageSpan
        label.setSpan(ImageSpan(menu_drawable(icon, icon_context), 1), 0, 1, 33)
    if destructive:
        from android.text.style import ForegroundColorSpan
        from android.graphics import Color
        from .palette import eink_enabled
        color = Color.rgb(0, 0, 0) if eink_enabled() else Color.rgb(190, 30, 45)
        label.setSpan(ForegroundColorSpan(color), len(prefix), len(prefix) + len(title), 33)
    return label


def ios_menu_actions(actions, invoke, blocks):
    """Retain Objective-C callbacks for the lifetime of their native menu."""
    from rubicon.objc import ObjCClass, Block, objc_id
    children = []
    for title, callback in actions:
        def selected(action, target=callback):
            invoke(target)
        block = Block(selected, None, objc_id)
        blocks.append(block)
        image = apple_command_image(title)
        action = ObjCClass('UIAction').actionWithTitle(title, image=image, identifier=None, handler=block)
        if title.startswith('Delete'):
            action.attributes = 2
        children.append(action)
    return children


class WorkspaceMenu(NativeMenu):
    """Resolve workspace commands when opening, including current busy guards."""
    def __init__(self, button, load_actions, **kwargs):
        self.load_actions = load_actions
        super().__init__(button, (), **kwargs)
        if type(button._impl).__module__.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, Block, ObjCBlock, objc_id, ns_from_py
            def provide(completion):
                self.blocks[:] = [provider]
                actions = () if self.disposed else self.load_actions()
                ObjCBlock(completion, None, objc_id)(ns_from_py(ios_menu_actions(actions, self.invoke, self.blocks)))
            provider = Block(provide, None, objc_id)
            self.blocks.append(provider)
            deferred = ObjCClass('UIDeferredMenuElement').elementWithUncachedProvider(provider)
            button._impl.native.menu = ObjCClass('UIMenu').menuWithTitle('', children=[deferred])

    def show(self, widget=None, **kwargs):
        if not self.disposed:
            self.actions = tuple(self.load_actions())
        return super().show(widget, **kwargs)


class BrowserActions:
    """Transient native row commands, scoped to the current browser selection."""
    def __init__(self, browser, actions):
        self.browser = weakref.ref(browser)
        self.actions = tuple(actions)
        self.epoch, self.selected = browser.epoch, browser.selected
        entry = browser.tree.entries[self.selected]
        from services.documents.storage import display_path, document_display_name
        path = entry.payload.get('path')
        self.location = display_path(browser.search_provider, path) if path else None
        self.filename = entry.payload.get('display_name') or (
            document_display_name(browser.search_provider, path) if path else PurePosixPath(entry.label).name)
        self.disposed = False
        self.native = None
        self.android = False
        self.listener = None
        self.blocks = []

    def invoke(self, callback):
        browser = self.browser()
        if (self.disposed or browser is None or browser.closed or not browser._app.active_host
                or browser.epoch != self.epoch or browser.selected != self.selected
                or browser.navigation_busy):
            return
        result = callback()
        if inspect.isawaitable(result):
            # Commands may already schedule their work (Move opens its picker
            # this way). create_task accepts coroutines, not existing Tasks.
            async def complete():
                return await result
            browser._spawn(complete())

    def show(self):
        browser = self.browser()
        backend = browser.native_list.factory.DetailedList.__module__
        if not backend.startswith(('toga_android.', 'toga_iOS.')):
            return
        native = browser.native_list._impl.native
        if backend.startswith('toga_android.'):
            from android.app import AlertDialog
            from android.content import DialogInterface
            from android.widget import TextView
            from java import dynamic_proxy
            self.android = True
            context = android_menu_context(browser._app._impl.native)
            title = TextView(context)
            title.setText(self.filename)
            title.setSingleLine(False)
            title.setTextIsSelectable(True)
            if self.location:
                from android.view import View
                menu = self
                class TitleHold(dynamic_proxy(View.OnLongClickListener)):
                    def onLongClick(self, widget):
                        widget.setText(menu.location)
                        return True
                self.title_hold = TitleHold()
                title.setOnLongClickListener(self.title_hold)
            title.setTextSize(18)
            padding = round(24 * context.getResources().getDisplayMetrics().density)
            title.setPadding(padding, padding, padding, padding // 2)
            menu = self
            class Listener(dynamic_proxy(DialogInterface.OnClickListener)):
                def onClick(self, dialog, index):
                    if 0 <= index < len(menu.actions):
                        menu.invoke(menu.actions[index][1])
            self.listener = Listener()
            labels = [android_command_label(label, icon_context=context) for label, _ in self.actions]
            self.native = (AlertDialog.Builder(context).setCustomTitle(title)
                .setItems(labels, self.listener)
                .setNegativeButton('Cancel', None).create())
            self.native.show()
        elif backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, Block, objc_id
            self.native = ObjCClass('UIAlertController').alertControllerWithTitle(
                self.filename, message=None, preferredStyle=0)
            for label, callback in self.actions:
                def selected(action, target=callback):
                    self.invoke(target)
                block = Block(selected, None, objc_id)
                self.blocks.append(block)
                self.native.addAction(ObjCClass('UIAlertAction').actionWithTitle(label,
                    style=2 if label.startswith('Delete') else 0, handler=block))
            self.native.addAction(ObjCClass('UIAlertAction').actionWithTitle('Cancel', style=1, handler=None))
            popover = self.native.popoverPresentationController
            if popover is not None:
                tile = browser.buttons.get(self.selected) if browser.mode == 'Tiles' else None
                anchor = tile._impl.native if tile is not None else native
                popover.sourceView = anchor
                popover.sourceRect = anchor.bounds
                row = browser._list_rows.get(self.selected) if tile is None else None
                if row is not None:
                    from toga_iOS.libs import NSIndexPath
                    popover.sourceRect = native.rectForRowAtIndexPath(
                        NSIndexPath.indexPathForRow(row.index, inSection=0))
            controller = browser._app.main_window._impl.native.rootViewController
            while controller.presentedViewController:
                controller = controller.presentedViewController
            controller.presentViewController(self.native, animated=True, completion=None)
            if self.location:
                from .document_location import bind_apple_hold
                labels = _apple_subviews(self.native.view)
                while labels:
                    label = labels.pop()
                    if label.isKindOfClass(ObjCClass('UILabel')) and str(label.text) == self.filename:
                        bind_apple_hold(self, label, BrowserActions.reveal_location)
                        break
                    labels.extend(_apple_subviews(label))

    def reveal_location(self):
        if not self.disposed:
            self.native.message = self.location

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        if self.native is not None and self.android:
            self.native.dismiss()
        elif self.native is not None:
            self.native.dismissViewControllerAnimated(False, completion=None)
        self.native = None
        self.listener = None
        self.actions = ()
        self.blocks.clear()


def show_browser_actions(browser, actions):
    browser.dismiss_item_menu()
    menu = browser._item_menu = BrowserActions(browser, actions)
    menu.show()
    return menu


# Reading, presentation, file operations, navigation, then destructive actions.
DOCUMENT_GROUPS = (
    ('View document', 'View Markdown', 'Edit Markdown', 'View source text',
     'Chapters and bookmarks…', 'Comic pages…', 'Pages and search',
     'Find and replace…', 'Find in this page…', 'Find in chapter…', 'Read aloud…'),
    ('Appearance…', 'Fullscreen', 'Reading mode', 'Fit comic page', 'Fit image'),
    ('File actions…', 'Reader tools…', 'Open / Metadata…', 'Rename document…',
     'Edit metadata…', 'Info…', 'Save', 'Save a copy', 'Save As…', 'Export…'),
    ('Open beside another document', 'Show in folder', 'Show cached copy in folder', 'All documents',
     'New document', 'Open from Files…', 'Import…'),
    ('Close document', 'Delete document…'),
)
_COMMAND_ORDER = {title: (group, index) for group, titles in enumerate(DOCUMENT_GROUPS)
                  for index, title in enumerate(titles)}


def command_groups(actions):
    groups = []
    previous = None
    for action in actions:
        group = _COMMAND_ORDER.get(action[0], (2, 0))[0]
        if group != previous:
            groups.append([])
            previous = group
        groups[-1].append(action)
    return groups


def can_pair_document(app, session):
    adaptive = getattr(app, 'adaptive', None)
    return (session is not None and adaptive is not None and adaptive.width() >= 640
            and adaptive.session_view(session.id) is not None)


class DocumentNativeMenu(NativeMenu):
    """Present document command groups as native separators on each platform."""
    def __init__(self, button, actions, **kwargs):
        super().__init__(button, actions, **kwargs)
        if type(button._impl).__module__.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            native = button._impl.native
            children = list(native.menu.children)
            for (title, _), action in zip(actions, children):
                if title == 'Delete document…':
                    action.attributes = 2  # UIMenuElementAttributesDestructive
            sections, offset = [], 0
            for group in command_groups(actions):
                sections.append(ObjCClass('UIMenu').menuWithTitle('', image=None,
                    identifier=None, options=1, children=children[offset:offset + len(group)]))
                offset += len(group)
            native.menu = ObjCClass('UIMenu').menuWithTitle('', children=sections)

    def popup_groups(self):
        return command_groups(self.actions)


def refresh_document_menus(app):
    for menu in tuple(getattr(app, '_document_menus', ())):
        menu.refresh()


class ActionMenu:
    def __init__(self, button, owner, actions, *, document=True):
        self.button, self.owner = button, weakref.ref(owner)
        self.raw_actions, self.document = list(actions), document
        self.menu = None
        self.disposed = False
        if document:
            host = getattr(owner, 'app', owner)
            app = getattr(host, 'app', host)
            if not hasattr(app, '_document_menus'):
                app._document_menus = weakref.WeakSet()
            app._document_menus.add(self)
        self.refresh()

    def refresh(self):
        if self.disposed or self.owner() is None:
            return
        actions = list(self.raw_actions)
        favourite_session = None
        if self.document:
            owner = self.owner()
            host = owner.app if isinstance(owner, FeatureOwner) else owner
            app = getattr(host, 'app', host)
            session = getattr(host, 'session', None)
            from .favourites import favourite, reference
            if session is not None:
                try:
                    reference(app, host, session=session)
                except (OSError, ValueError):
                    pass
                else:
                    favourite_session = session
                    actions.append(('Favourite file', lambda: favourite(app, host, session=favourite_session)))
            from .document_sources import folder_action
            folder_titles = {'Show in folder', 'Show cached copy in folder'}
            if session is not None and session.provider == 'library':
                actions = [item for item in actions if item[0] not in folder_titles]
            if not any(title in folder_titles for title, _ in actions):
                actions.extend(folder_action(app, session, host))
            aliases = {'Close private document': 'Close document', 'Close comic': 'Close document'}
            paired = can_pair_document(app, session)
            actions = [(aliases.get(title, title), callback) for title, callback in actions
                       if title != 'Open beside another document' or paired]
            if paired and not any(title == 'Open beside another document' for title, _ in actions):
                actions.append(('Open beside another document', app.adaptive.show_pair_picker))
            redundant = {'New document', 'Open from Files…', 'Import…', 'Close document',
                         'All documents', 'Open documents'}
            actions = [item for item in actions if item[0] not in redundant]
            actions.sort(key=lambda item: _COMMAND_ORDER.get(item[0], (2, 0)))
        if (self.menu is not None and favourite_session is self._favourite_session
                and [item[0] for item in actions] == [item[0] for item in self.actions]):
            return
        if self.menu is not None:
            self.menu.dispose()
        self.actions = actions
        self._favourite_session = favourite_session
        menu_type = DocumentNativeMenu if self.document else NativeMenu
        self.menu = menu_type(self.button, actions, invoke=self.invoke,
                              context=self.native_context, fallback=self.show_fallback)

    def native_context(self):
        owner = self.owner()
        if owner is None:
            return None
        host = owner.app
        app = getattr(host, 'app', host)
        return app._impl.native

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        self.menu.dispose()
        self.actions.clear()
        self.raw_actions.clear()

    def invoke(self, callback):
        owner = self.owner()
        if owner is None or not owner.app.active_host or owner.session is None or owner.session.id not in owner.app.workspace.sessions:
            return
        if owner.app.editor_view is not owner:
            if not owner.app.checkpoint():
                return
            owner.app.editor_view.capture()
            owner.app.adaptive.focus_session(owner.session.id)
            owner.bind()
            owner.app.workspace.activate(owner.session.id)
            owner.app.show_documents()
        result = callback()
        if inspect.isawaitable(result):
            owner.app.loop.create_task(result)

    def show_fallback(self):
        owner = self.owner()
        if owner is not None:
            return owner.app.show_editor_actions(owner, menu=self)


class FeatureOwner:
    def __init__(self, app):
        self.app = app


class FeatureCommands(ActionMenu):
    """Feature-owned native commands without editor rebinding."""
    def __init__(self, button, app, actions, fallback, *, document=False):
        self.feature_owner = FeatureOwner(app)
        self.fallback = fallback
        super().__init__(button, self.feature_owner, actions, document=document)

    def invoke(self, callback):
        app = self.feature_owner.app
        if not app.active_host:
            return
        session = getattr(app, 'session', None)
        if session is not None and session.id not in app.workspace.sessions:
            return
        result = callback()
        if inspect.isawaitable(result):
            app.loop.create_task(result)

    def show_fallback(self):
        if self.document:
            host = self.feature_owner.app
            app = getattr(host, 'app', host)
            return app.show_editor_actions(self.feature_owner, menu=self)
        return self.fallback()
