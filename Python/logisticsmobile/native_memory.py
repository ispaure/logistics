"""Isolated native memory-pressure subscriptions with explicit disposal."""
import weakref


class MemoryPressure:
    def __init__(self, app):
        self.app = weakref.ref(app)
        self.observer = self.listener = self.context = self.block = None
        backend = type(app._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, Block, objc_id
            self.center = ObjCClass('NSNotificationCenter').defaultCenter
            self.block = Block(lambda notification: self.release(), None, objc_id)
            self.observer = self.center.addObserverForName('UIApplicationDidReceiveMemoryWarningNotification',
                object=None, queue=None, usingBlock=self.block)
        elif backend.startswith('toga_android.'):
            from android.content import ComponentCallbacks2
            from java import dynamic_proxy
            subscription = self
            class Listener(dynamic_proxy(ComponentCallbacks2)):
                def onConfigurationChanged(self, configuration):
                    pass
                def onLowMemory(self):
                    subscription.release()
                def onTrimMemory(self, level):
                    if level >= 10:
                        subscription.release()
            self.listener = Listener()
            self.context = app._impl.native.getApplicationContext()
            self.context.registerComponentCallbacks(self.listener)

    def release(self):
        app = self.app()
        if app is not None and app.active_host:
            app.loop.call_soon_threadsafe(app.release_disposable_resources)

    def dispose(self):
        if self.observer is not None:
            self.center.removeObserver(self.observer)
            self.observer = self.block = None
        if self.listener is not None:
            self.context.unregisterComponentCallbacks(self.listener)
            self.listener = self.context = None
