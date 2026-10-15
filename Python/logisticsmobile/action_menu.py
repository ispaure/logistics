"""Native Apple button menus and Android anchored popup commands."""
import inspect
import weakref
from commonUtils.ui.native.menus import NativeMenu


class ActionMenu:
    def __init__(self, button, owner, actions):
        self.button, self.owner, self.actions = button, weakref.ref(owner), actions
        self.menu = NativeMenu(button, actions, invoke=self.invoke,
                               context=self.native_context, fallback=self.show_fallback)

    def native_context(self):
        owner = self.owner()
        return owner.app._impl.native if owner is not None else None

    def dispose(self):
        self.menu.dispose()

    def invoke(self, callback):
        owner = self.owner()
        if owner is None or not owner.app.active_host or owner.session is None or owner.session.id not in owner.app.workspace.sessions:
            return
        if owner.app.editor_view is not owner:
            if not owner.app.checkpoint():
                return
            owner.app.editor_view.capture()
            owner.bind()
            owner.app.workspace.activate(owner.session.id)
            owner.app.show_documents()
        result = callback()
        if inspect.isawaitable(result):
            owner.app.loop.create_task(result)

    def show_fallback(self):
        owner = self.owner()
        if owner is not None:
            return owner.app.show_editor_actions(owner)


class FeatureOwner:
    def __init__(self, app):
        self.app = app


class FeatureCommands(ActionMenu):
    """Feature-owned native commands without editor rebinding."""
    def __init__(self, button, app, actions, fallback):
        self.feature_owner = FeatureOwner(app)
        self.fallback = fallback
        super().__init__(button, self.feature_owner, actions)

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
        return self.fallback()
