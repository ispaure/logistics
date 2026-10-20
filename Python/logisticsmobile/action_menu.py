"""Native Apple button menus and Android anchored popup commands."""
import inspect
import weakref
from commonUtils.ui.native.menus import NativeMenu


# Reading, presentation, file operations, navigation, then destructive actions.
DOCUMENT_GROUPS = (
    ('View document', 'View Markdown', 'Edit Markdown', 'View source text',
     'Chapters and bookmarks…', 'Comic pages…', 'Pages and search',
     'Find and replace…', 'Find in chapter…', 'Read aloud…'),
    ('Appearance…', 'Fullscreen', 'Reading mode', 'Fit comic page', 'Fit image'),
    ('File actions…', 'Reader tools…', 'Open / Metadata…', 'Rename document…',
     'Edit metadata…', 'Info…', 'Save', 'Save a copy', 'Save As…', 'Export…'),
    ('Open beside another document', 'Show in folder', 'All documents',
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
            sections, offset = [], 0
            for group in command_groups(actions):
                sections.append(ObjCClass('UIMenu').menuWithTitle('', image=None,
                    identifier=None, options=1, children=children[offset:offset + len(group)]))
                offset += len(group)
            native.menu = ObjCClass('UIMenu').menuWithTitle('', children=sections)

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
                menu.invoke(menu.actions[item.getItemId()][1])
                return True
        self.listener = Listener()
        native = self.popup.getMenu()
        index = 0
        for group_id, group in enumerate(command_groups(self.actions)):
            for title, callback in group:
                native.add(group_id, index, index, title)
                index += 1
        from android.os import Build
        if Build.VERSION.SDK_INT >= 28:
            native.setGroupDividerEnabled(True)
        self.popup.setOnMenuItemClickListener(self.listener)
        self.popup.show()


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
        if self.document:
            owner = self.owner()
            host = owner.app if isinstance(owner, FeatureOwner) else owner
            app = getattr(host, 'app', host)
            session = getattr(host, 'session', None)
            from .document_sources import folder_action
            if not any(title == 'Show in folder' for title, _ in actions):
                actions.extend(folder_action(app, session, host))
            aliases = {'Open documents': 'All documents', 'Close private document': 'Close document',
                       'Close comic': 'Close document'}
            paired = can_pair_document(app, session)
            actions = [(aliases.get(title, title), callback) for title, callback in actions
                       if title != 'Open beside another document' or paired]
            if paired and not any(title == 'Open beside another document' for title, _ in actions):
                actions.append(('Open beside another document', app.adaptive.show_pair_picker))
            if not any(title == 'All documents' for title, _ in actions):
                actions.append(('All documents', app.show_documents_hub))
            if session is not None and not any(title == 'Close document' for title, _ in actions):
                actions.append(('Close document', lambda: app.request_close_session(session.id)))
            actions.sort(key=lambda item: _COMMAND_ORDER.get(item[0], (2, 0)))
        if self.menu is not None and [item[0] for item in actions] == [item[0] for item in self.actions]:
            return
        if self.menu is not None:
            self.menu.dispose()
        self.actions = actions
        menu_type = DocumentNativeMenu if self.document else NativeMenu
        self.menu = menu_type(self.button, actions, invoke=self.invoke,
                              context=self.native_context, fallback=self.show_fallback)

    def native_context(self):
        owner = self.owner()
        return owner.app._impl.native if owner is not None else None

    def dispose(self):
        self.disposed = True
        self.menu.dispose()

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
        if not app.active_host or getattr(app, 'cloud_busy', False):
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
