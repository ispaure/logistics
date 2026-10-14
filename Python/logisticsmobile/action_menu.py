"""Native Apple button menus and Android anchored popup commands."""
import inspect
import weakref


class ActionMenu:
    def __init__(self, button, owner, actions):
        self.button, self.owner, self.actions = button, weakref.ref(owner), actions
        self.blocks = []
        backend = type(button._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, Block, objc_id
            native_actions = []
            for title, callback in actions:
                def dispatch(action, target=callback):
                    self.invoke(target)
                block = Block(dispatch, None, objc_id)
                self.blocks.append(block)
                native_actions.append(ObjCClass('UIAction').actionWithTitle(title,
                    image=None, identifier=None, handler=block))
            button._impl.native.menu = ObjCClass('UIMenu').menuWithTitle('', children=native_actions)
            button._impl.native.showsMenuAsPrimaryAction = True
        else:
            button.on_press = self.show

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

    def show(self, widget=None, **kwargs):
        owner = self.owner()
        if owner is None:
            return
        if type(self.button._impl).__module__.startswith('toga_android.'):
            from android.widget import PopupMenu
            from java import dynamic_proxy
            self.popup = PopupMenu(owner.app._impl.native, self.button._impl.native)
            menu = self
            class Listener(dynamic_proxy(PopupMenu.OnMenuItemClickListener)):
                def onMenuItemClick(self, item):
                    menu.invoke(menu.actions[item.getItemId()][1])
                    return True
            self.listener = Listener()
            for index, (title, callback) in enumerate(self.actions):
                self.popup.getMenu().add(0, index, index, title)
            self.popup.setOnMenuItemClickListener(self.listener)
            self.popup.show()
        else:
            owner.app.show_editor_actions(owner)


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

    def show(self, widget=None, **kwargs):
        if type(self.button._impl).__module__.startswith('toga_android.'):
            return super().show(widget, **kwargs)
        return self.fallback()
