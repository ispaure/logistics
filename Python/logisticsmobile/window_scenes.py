"""Tracked UIKit scene extension; ordinary workspaces own each native window."""
from hashlib import sha256
from pathlib import Path
import json

from .window_owners import WindowOwners


def is_workspace_scene(role):
    return str(role) == 'UIWindowSceneSessionRoleApplication'


class SceneManager:
    def __init__(self, app, *, prepare_only=False):
        self.app = app
        self.owners = WindowOwners()
        if not prepare_only:
            self.owners.attach('primary', app)
            self.bind_workspace('primary', app)
        self.scenes = {}
        self.primary_disconnected = False
        self.primary_disconnects = 0
        self.supported = False
        self.error = ''
        self.delegate = self.old_delegate = None
        if type(app._impl).__module__.startswith('toga_iOS.'):
            self.install_ios()

    def activate(self):
        if type(self.app._impl).__module__.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            application = ObjCClass('UIApplication').sharedApplication
            self.delegate = application.delegate
            self.supported = (ObjCClass('UIDevice').currentDevice.userInterfaceIdiom == 1
                              and bool(application.supportsMultipleScenes))

    def bind_workspace(self, key, host):
        host.window_id = key
        host.scene_manager = self
        host.workspace.window_owners = self.owners
        host.workspace.window_id = key
        for session in host.workspace.sessions.values():
            # Restored manifests carry no live views. The first window to restore
            # a resource retains its writer; another keeps an unavailable entry.
            try:
                self.owners.claim(key, session.identity, private=session.transient)
            except ValueError:
                pass

    def new_window(self, widget=None, *, workspace_id=None, **kwargs):
        if getattr(self.app, '_reset_scheduled', False):
            return False
        self.reconcile_scenes()
        if not self.supported or (not self.primary_disconnected and not self.owners.can_add()):
            self.error = 'Close protected items or another window before opening a new window.'
            self.app.settings_status.text = self.error
            return False
        from rubicon.objc import ObjCClass, Block, objc_id
        existing = self.owners.hosts.get(workspace_id)
        if existing is not None:
            ObjCClass('UIApplication').sharedApplication.requestSceneSessionActivation(
                existing.native_scene.session, userActivity=None, options=None, errorHandler=None)
            return True
        activity = None
        if workspace_id is not None:
            from .workspace import uuid
            if not uuid(workspace_id):
                raise ValueError('Invalid window identity.')
            activity = ObjCClass('NSUserActivity').alloc().initWithActivityType('io.github.ispaure.logistics.workspace')
            activity.userInfo = {'workspace': workspace_id}
        self.request_error = Block(lambda error: self.failed(error), None, objc_id)
        ObjCClass('UIApplication').sharedApplication.requestSceneSessionActivation(
            None, userActivity=activity, options=None, errorHandler=self.request_error)
        return True

    def reconcile_scenes(self):
        if not self.supported:
            return
        from rubicon.objc import ObjCClass
        opened = {str(session.persistentIdentifier) for session in ObjCClass('UIApplication').sharedApplication.openSessions.allObjects()}
        for host in list(self.scenes.values()):
            if str(host.native_scene.session.persistentIdentifier) not in opened:
                self.disconnect(host)

    def failed(self, error):
        self.error = 'The system could not open another window.'
        self.app.settings_status.text = self.error

    def close_window(self, host):
        if host is self.app or not host.checkpoint():
            return False
        from rubicon.objc import ObjCClass, Block, objc_id
        self.close_error = Block(lambda error: self.failed(error), None, objc_id)
        ObjCClass('UIApplication').sharedApplication.requestSceneSessionDestruction(
            host.native_scene.session, options=None, errorHandler=self.close_error)
        return True

    def save_destination(self, host):
        if host.window_id == 'primary':
            return
        from commonUtils.persistence import atomic_write_json
        path = host.workspace.path.with_name('scene-state.json')
        if path.is_symlink():
            raise ValueError('Window state cannot be linked.')
        if path.exists():
            self.read_destination(host)
        atomic_write_json(path, {'schema': 1, 'destination': host.native_host.state.destination}, max_bytes=1024)

    def read_destination(self, host):
        path = Path(host.workspace_root) / 'scene-state.json'
        if not path.exists():
            return 'home'
        if path.is_symlink() or path.stat().st_size > 1024:
            raise ValueError('Window state was preserved; it cannot be restored.')
        value = json.loads(path.read_text())
        if (not isinstance(value, dict) or set(value) != {'schema', 'destination'} or value['schema'] != 1
                or value['destination'] not in ('home', 'files', 'documents', 'chat', 'settings')):
            raise ValueError('Window state was preserved; it cannot be restored.')
        return value['destination']

    def install_ios(self):
        from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, objc_property
        from toga_iOS.app import PythonAppDelegate
        from toga_iOS.window import MainWindow
        import toga
        from toga.types import Size
        manager = self

        class SceneBackend(MainWindow):
            def set_app(self, app):
                pass
            def get_size(self):
                bounds = self.native.bounds.size
                return Size(int(bounds.width), int(bounds.height))

        self.app.factory.LogisticsSceneWindow = SceneBackend

        class SceneWindow(toga.Window):
            _WINDOW_CLASS = 'LogisticsSceneWindow'

        self.window_class = SceneWindow
        # Classes are defined once per process. Their methods use the manager
        # retained by this application rather than the backend's global window.
        class LogisticsSceneDelegate(ObjCClass('UIResponder'),
                                     protocols=(ObjCProtocol('UIWindowSceneDelegate'),)):
            window = objc_property()

            @objc_method
            def scene_willConnectToSession_options_(self, scene, session, options) -> None:
                if not is_workspace_scene(session.role):
                    # AirPlay/external displays must never get an independent
                    # workspace (or a frozen copy of Home) with shared secrets.
                    self.window = ObjCClass('UIWindow').alloc().initWithWindowScene(scene)
                    controller = ObjCClass('UIViewController').alloc().init()
                    from .screen_privacy import native_value
                    controller.view.backgroundColor = native_value(ObjCClass('UIColor'), 'blackColor')
                    controller.view.accessibilityLabel = 'Private content hidden'
                    self.window.rootViewController = controller
                    self.window.hidden = False
                    return
                identifier = sha256(str(session.persistentIdentifier).encode()).hexdigest()[:32]
                from .workspace import uuid
                requested_workspace = False
                activities = list(options.userActivities.allObjects())
                if session.stateRestorationActivity is not None:
                    activities.append(session.stateRestorationActivity)
                for activity in activities:
                    if str(activity.activityType) == 'io.github.ispaure.logistics.workspace':
                        candidate = activity.userInfo['workspace'] if activity.userInfo is not None else None
                        if uuid(str(candidate)):
                            identifier = str(candidate)
                            requested_workspace = True
                            break
                if not requested_workspace and (manager.primary_disconnected or not hasattr(manager.app, 'native_scene')):
                    host = manager.app
                    manager.primary_disconnected = False
                else:
                    if not manager.owners.can_add():
                        manager.failed(None)
                        return
                    host = manager.make_host(identifier)
                self.host = host
                self.window = host.main_window._impl.native
                self.window.windowScene = scene
                manager.scenes[identifier] = host
                host.native_scene = scene
                self.window.makeKeyAndVisible()

            @objc_method
            def stateRestorationActivityForScene_(self, scene):
                if not hasattr(self, 'host') or self.host is manager.app:
                    return None
                activity = ObjCClass('NSUserActivity').alloc().initWithActivityType('io.github.ispaure.logistics.workspace')
                activity.userInfo = {'workspace': self.host.window_id}
                return activity

            @objc_method
            def sceneDidBecomeActive_(self, scene) -> None:
                if hasattr(self, 'host'):
                    self.host.scene_active = True
                    self.host.screen_privacy.reveal()
                    self.host.main_window.on_gain_focus()

            @objc_method
            def sceneWillResignActive_(self, scene) -> None:
                if hasattr(self, 'host'):
                    self.host.scene_active = False
                    self.host.screen_privacy.conceal()
                    self.host.checkpoint()

            @objc_method
            def sceneDidEnterBackground_(self, scene) -> None:
                if hasattr(self, 'host'):
                    self.host.checkpoint()

            @objc_method
            def sceneDidDisconnect_(self, scene) -> None:
                if hasattr(self, 'host'):
                    manager.disconnect(self.host)

        class LogisticsSceneAppDelegate(PythonAppDelegate):
            @objc_method
            def application_didDiscardSceneSessions_(self, application, sessions) -> None:
                discarded = {str(session.persistentIdentifier) for session in sessions.allObjects()}
                for host in list(manager.scenes.values()):
                    if str(host.native_scene.session.persistentIdentifier) in discarded:
                        manager.disconnect(host)

            @objc_method
            def application_configurationForConnectingSceneSession_options_(self, application, session, options):
                manager.reconcile_scenes()
                configuration = ObjCClass('UISceneConfiguration').alloc().initWithName(
                    'Logistics workspace', sessionRole=session.role)
                configuration.delegateClass = LogisticsSceneDelegate
                return configuration

        self.delegate_class = LogisticsSceneAppDelegate

    def make_host(self, identifier):
        from .app import LogisticsMobile
        host = object.__new__(workspace_class())
        # Only application infrastructure is shared. Feature state, callbacks,
        # routes, native containers, preferences and drafts belong to this host.
        for field in ('factory', '_impl', '_paths', '_app_name', 'metadata', '_formal_name',
                      '_app_id', '_author', '_version', '_home_page', '_description', '_windows', '_commands'):
            setattr(host, field, getattr(self.app, field))
        host._main_window = None
        host.storage_root = self.app.private_root
        host.window_id = identifier
        host.workspace_root = Path(host.storage_root) / 'Windows' / identifier
        host.window_class = self.window_class
        host.scene_manager = self
        try:
            destination = self.read_destination(host)
        except (OSError, ValueError):
            destination = 'home'
        LogisticsMobile.startup(host)
        try:
            host.native_host.activate(destination)
            host.body = host.routes.body()
            host.save_workspace()
        except (OSError, ValueError):
            host.recovery_notice.text = 'Window state was preserved; it cannot be restored.'
        return host

    def disconnect(self, host):
        if not host.active_host or (host is self.app and self.primary_disconnected):
            return
        from commonUtils.ui.native.documents import cancel_document_picker
        cancel_document_picker(host.main_window)
        if host is self.app:
            host.checkpoint()
            self.primary_disconnected = True
            self.primary_disconnects += 1
            self.scenes = {key: value for key, value in self.scenes.items() if value is not host}
            return
        host.checkpoint()
        host.release_disposable_resources()
        for view in host.text_views.values():
            view.dispose()
        host.memory_pressure.dispose()
        host.screen_privacy.dispose()
        host.adaptive.uninstall()
        host.routes.uninstall()
        host.native_host.dispose()
        host.navigation.window = None
        host.navigation.app = None
        host.active_host = False
        for session in host.workspace.sessions.values():
            host.workspace.invalidate(session.id)
        self.owners.detach(host.window_id)
        from .app import _active_hosts
        identity = str(host.private_root.resolve()) + ':' + host.window_id
        if _active_hosts.get(identity) is host:
            _active_hosts.pop(identity)
        self.scenes = {key: value for key, value in self.scenes.items() if value is not host}
        self.app.windows.remove(host.main_window)
        if len(self.owners.hosts) == 1 and hasattr(self.app, 'native_scene'):
            from rubicon.objc import ObjCClass
            ObjCClass('UIApplication').sharedApplication.requestSceneSessionActivation(
                None if self.primary_disconnected else self.app.native_scene.session,
                userActivity=None, options=None, errorHandler=None)


def install_scenes(app):
    app.scene_manager = SceneManager(app)


def workspace_class():
    from .app import LogisticsMobile
    class OrdinaryWindowWorkspace(LogisticsMobile):
        def show_cloud(self, widget=None, **kwargs):
            self.show_window_boundary()
        def show_cloud_connections(self, widget=None, **kwargs):
            self.show_window_boundary()
        def show_smb_connection(self, widget=None, **kwargs):
            self.show_window_boundary()
        def show_chat(self, widget=None, **kwargs):
            self.show_window_boundary()
        def show_transfers(self, widget=None, **kwargs):
            self.show_window_boundary()
        async def show_local_location(self, widget=None, **kwargs):
            # The primary host owns local mutations and connection workers.
            self.show_window_boundary()
        def show_window_boundary(self):
            import toga
            from toga.style import Pack
            self.show_view(toga.Label('Use the original window for files, connections and chat.',
                                      style=Pack(margin=16)), title='Original window')
    return OrdinaryWindowWorkspace
