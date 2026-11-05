"""Owned compiled UIWindow factory; no Python callback on the native input path."""
_classes = None


def _native_class():
    try:
        from importlib.metadata import version
        if version('toga-iOS') != '0.5.7':
            return None
        from rubicon.objc import ObjCClass
        return ObjCClass('LogisticsNotebookInputWindow')
    except Exception:
        return None


def initialize_backend(backend, interface, title, position, size):
    """Pinned initializer on an actual SDK backend or existing SceneBackend.

    Only the native UIWindow allocation changes. Never replace toolkit classes,
    reclassify an object, or construct/transfer a second window/controller tree.
    """
    from toga_iOS.window import MainWindow
    from toga_iOS.libs import UIScreen, UIColor
    native_class = _native_class()
    try:
        native = native_class.alloc().initWithFrame(UIScreen.mainScreen.bounds) if native_class else None
    except Exception:
        native = None
    if native is None:
        MainWindow.__init__(backend, interface, title, position, size)
        return
    try:
        # Exact pinned Window.__init__ order. Virtual create_container retains
        # MainWindow NavigationContainer and existing SceneBackend overrides.
        backend.interface = interface
        interface._impl = backend
        backend.native = native
        backend.create_container()
        backend.last_refreshed_size = (0, 0)
        backend.container.native.frame = backend.native.bounds
        backend.native.rootViewController = backend.container.controller
        try:
            backend.native.backgroundColor = UIColor.systemBackgroundColor()
        except AttributeError:
            backend.native.backgroundColor = UIColor.whiteColor
        backend.set_title(title)
    except Exception:
        # Preserve the product failure while detaching the partial native tree.
        # Never hide a real container/toolbar error behind a second constructor.
        try:
            native.hidden = True
            native.rootViewController = None
        except Exception:
            pass
        raise


def _main_window_backend(interface, title, position, size):
    from toga_iOS.window import MainWindow
    backend = MainWindow.__new__(MainWindow)
    initialize_backend(backend, interface, title, position, size)
    return backend


def window_classes():
    global _classes
    import toga
    from toga_iOS.window import MainWindow
    if _classes is not None:
        return _classes
    if _native_class() is None:
        return MainWindow, toga.MainWindow

    class NativeNotebookMainWindow(toga.MainWindow):
        _WINDOW_CLASS = 'LogisticsNotebookNativeInputMainWindow'

    _classes = _main_window_backend, NativeNotebookMainWindow
    return _classes


def main_window_class(app):
    from commonUtils.ui.native.text_size import native_backend
    import toga
    if not native_backend(app).startswith('toga_iOS.'):
        return toga.MainWindow
    backend, interface = window_classes()
    if interface is not toga.MainWindow:
        app.factory.LogisticsNotebookNativeInputMainWindow = backend
    return interface
