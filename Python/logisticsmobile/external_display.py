"""Picture-only external comic output; no workspace, credentials or disk copies."""
import weakref
import json
import os


def comic_canvas(view):
    if getattr(view, '_external_comic_page', False) and getattr(view, 'image', None) is not None:
        return view
    for child in view.children:
        found = comic_canvas(child)
        if found is not None:
            return found
    return None


class ExternalComicDisplay:
    def __init__(self, manager):
        self.manager = manager
        self.source = None
        self._diagnostic_state = None
        self.ios = {}
        self.ios_registration = None
        self.android = None
        self.android_refresh = None

    def select(self, app):
        self.source = weakref.ref(app)
        self.trace_ios(app, 'select')
        if type(app._impl).__module__.startswith('toga_iOS.'):
            try:
                self.register_ios(app)
            except Exception as error:
                self.trace_ios(app, type(error).__name__ + ': ' + str(error))
                raise
        self.refresh()

    def trace_ios(self, app, stage):
        # Explicit opt-in tracing contains no page data or credential contents.
        if (os.environ.get('LOGISTICS_DISPLAY_DIAGNOSTICS') != '1'
                or not type(app._impl).__module__.startswith('toga_iOS.')):
            return
        from pathlib import Path
        Path(app.paths.cache, 'external-display-trace.json').write_text(json.dumps(dict(
            stage=stage, backend=type(app._impl).__module__,
            diagnostics=os.environ.get('LOGISTICS_DISPLAY_DIAGNOSTICS'))))

    def register_ios(self, app):
        """iOS 27 requires an accessory registration before offering a TV scene."""
        from rubicon.objc import ObjCClass
        try:
            accessory_class = ObjCClass('UISceneAccessory')
        except NameError:  # iOS 26 and earlier use the scene manifest automatically.
            return
        controller = app.main_window._impl.native.rootViewController
        if controller is None:
            return
        if self.ios_registration is not None and self.ios_registration[0] == controller:
            return
        self.unregister_ios()
        configuration = ObjCClass('UISceneConfiguration').alloc().initWithName(
            'Logistics comic display', sessionRole='UIWindowSceneSessionRoleExternalDisplayNonInteractive')
        configuration.delegateClass = self.manager.external_scene_delegate
        accessory = accessory_class.externalNonInteractiveSceneAccessoryWithConfiguration(configuration)
        registration = controller.registerSceneAccessory(accessory)
        self.ios_registration = controller, registration

    def unregister_ios(self):
        if self.ios_registration is not None:
            controller, registration = self.ios_registration
            self.ios_registration = None
            controller.unregisterSceneAccessory(registration)

    def allowed_canvas(self):
        app = self.source() if self.source is not None else None
        if app is None or not getattr(app, 'active_host', False):
            return None
        privacy = getattr(app, 'screen_privacy', None)
        if privacy is None or privacy.inactive or privacy.saved_content is not None:
            return None
        # Gates cover the process and retained protected views, even when the
        # displayed comic itself is an ordinary local file. Unlocking a gate
        # does not grant permission to transmit its content to another screen.
        from features.rclone.mobile.cloud import CloudClient
        observers = tuple(CloudClient._credential_observers)
        if privacy.gates() or any(not owner.disposed and owner.gates() for owner in observers):
            return None
        if getattr(privacy, 'shield', None) is not None:
            return None
        return comic_canvas(app.body)

    def refresh(self):
        if not self.ios and self.android is None:
            self.diagnose_ios()
            return
        canvas = self.allowed_canvas()
        for window, picture in self.ios.values():
            picture.image = canvas._impl.picture.image if canvas is not None else None
        if self.android is not None:
            self.android.setImage(canvas._impl.native.getDrawable() if canvas is not None else None)
        self.diagnose_ios()

    def diagnose_ios(self):
        if os.environ.get('LOGISTICS_DISPLAY_DIAGNOSTICS') != '1':
            return
        try:
            app = self.source() if self.source is not None else None
            if app is None or not type(app._impl).__module__.startswith('toga_iOS.'):
                return
            from rubicon.objc import ObjCClass
            application = ObjCClass('UIApplication').sharedApplication
            scenes = list(application.connectedScenes.allObjects())
            screens = list(ObjCClass('UIScreen').screens)
            privacy = getattr(app, 'screen_privacy', None)
            state = dict(
                os=str(ObjCClass('UIDevice').currentDevice.systemVersion),
                roles=[str(scene.session.role) for scene in scenes],
                screens=[dict(width=float(screen.bounds.size.width), height=float(screen.bounds.size.height),
                              mirrored=screen.mirroredScreen is not None) for screen in screens],
                output_windows=len(self.ios), registration=self.ios_registration is not None,
                outputs=[dict(
                    window_bounds=[float(window.bounds.size.width), float(window.bounds.size.height)],
                    screen_bounds=[float(window.screen.bounds.size.width), float(window.screen.bounds.size.height)],
                    scene_bounds=[float(window.windowScene.coordinateSpace.bounds.size.width), float(window.windowScene.coordinateSpace.bounds.size.height)],
                    scene_state=int(window.windowScene.activationState),
                    hidden=bool(window.isHidden()), alpha=float(window.alpha),
                    picture_bounds=[float(picture.bounds.size.width), float(picture.bounds.size.height)],
                    image=picture.image is not None,
                    image_size=([float(picture.image.size.width), float(picture.image.size.height)]
                                if picture.image is not None else None),
                ) for window, picture in self.ios.values()],
                source_active=bool(getattr(app, 'active_host', False)),
                source_comic=comic_canvas(app.body) is not None,
                allowed=self.allowed_canvas() is not None,
                foreground=int(application.applicationState),
                gates=len(privacy.gates()) if privacy is not None else -1,
                manifest_roles=[str(role) for role in ObjCClass('NSBundle').mainBundle.infoDictionary['UIApplicationSceneManifest']['UISceneConfigurations']],
            )
            rendered = json.dumps(state, sort_keys=True)
            if rendered != self._diagnostic_state:
                self._diagnostic_state = rendered
                from pathlib import Path
                from commonUtils.persistence import atomic_write_json
                atomic_write_json(Path(app.paths.cache) / 'external-display-diagnostics.json', state)
                print('LOGISTICS_EXTERNAL_DISPLAY=' + rendered, flush=True)
        except Exception as error:
            message = type(error).__name__ + ': ' + str(error)
            self.trace_ios(app, message)
            if self._diagnostic_state != message:
                self._diagnostic_state = message
                print('LOGISTICS_EXTERNAL_DISPLAY_ERROR=' + message, flush=True)

    def connect_ios(self, scene):
        from rubicon.objc import ObjCClass
        from .screen_privacy import native_value
        window = ObjCClass('UIWindow').alloc().initWithWindowScene(scene)
        controller = ObjCClass('UIViewController').alloc().init()
        picture = ObjCClass('UIImageView').alloc().init()
        picture.backgroundColor = native_value(ObjCClass('UIColor'), 'blackColor')
        picture.contentMode = 1  # scaleAspectFit, including letterboxing
        picture.clipsToBounds = True
        picture.userInteractionEnabled = False
        picture.accessibilityLabel = 'Comic on external display'
        controller.view = picture
        window.rootViewController = controller
        window.frame = scene.coordinateSpace.bounds
        picture.frame = window.bounds
        picture.autoresizingMask = 18  # flexible width and height
        self.ios[str(scene.session.persistentIdentifier)] = window, picture
        # Rubicon's attribute assignment does not reliably dispatch this UIKit
        # property with its custom isHidden getter. Use the native selector.
        window.setHidden(False)
        self.refresh()
        return window

    def disconnect_ios(self, scene):
        target = self.ios.pop(str(scene.session.persistentIdentifier), None)
        if target is not None:
            window, picture = target
            picture.image = None
            window.setHidden(True)

    def install_android(self, app):
        if self.android is None:
            from java import jclass, dynamic_proxy
            output = self
            class Refresh(dynamic_proxy(jclass('java.lang.Runnable'))):
                def run(self):
                    output.refresh()
            self.android_refresh = Refresh()
            self.android = jclass('io.github.ispaure.logisticsmobile.ComicDisplay')(
                app._impl.native, self.android_refresh)

    def dispose(self):
        self.unregister_ios()
        for window, picture in self.ios.values():
            picture.image = None
            window.setHidden(True)
        self.ios.clear()
        if self.android is not None:
            self.android.dispose()
            self.android = None
        self.android_refresh = None
        self.source = None


def sync(app, *, select=False):
    output = getattr(getattr(app, 'scene_manager', None), 'external_comics', None)
    if output is None:
        return
    if type(app._impl).__module__.startswith('toga_android.'):
        output.install_android(app)
    if select:
        output.select(app)
    else:
        output.refresh()
