"""One-shot native draw acknowledgement before starting file-opening work."""
import asyncio

_apple_probe_class = None


def _install_draw_probe(panel, drawn):
    backend = type(panel._impl).__module__
    native = getattr(panel._impl, 'native', None)
    if backend.startswith('toga_android.') and native is not None:
        from java import dynamic_proxy
        from io.github.ispaure.logisticsmobile import DrawReady
        class Listener(dynamic_proxy(DrawReady.Listener)):
            def onDrawn(self):
                drawn()
        listener = Listener()
        watch = DrawReady.watch(native, listener)
        def cleanup():
            watch.cancel()
            # Keep the Python proxy alive until removal of the Java listener.
            return listener
        return cleanup
    if backend.startswith('toga_iOS.') and native is not None:
        from rubicon.objc import ObjCClass, objc_method, objc_property
        from rubicon.objc.runtime import send_super
        from toga_iOS.libs import CGRect
        global _apple_probe_class
        if _apple_probe_class is None:
            class LogisticsDrawProbe(ObjCClass('UIView')):
                owner = objc_property(object, weak=True)
                @objc_method
                def drawRect_(self, rect: CGRect) -> None:
                    send_super(LogisticsDrawProbe, self, 'drawRect:', rect, argtypes=[CGRect])
                    if self.owner is not None:
                        self.owner.drawn()
            _apple_probe_class = LogisticsDrawProbe
        class Owner:
            def drawn(self):
                drawn()
        owner = Owner()
        probe = _apple_probe_class.alloc().initWithFrame(CGRect((0, 0), (1, 1)))
        probe.owner = owner
        probe.opaque = False
        probe.userInteractionEnabled = False
        native.addSubview(probe)
        probe.setNeedsDisplay()
        def cleanup():
            probe.removeFromSuperview()
            return owner
        return cleanup
    return None


async def wait_for_draw(panel, *, timeout=.5):
    """Acknowledge native drawing; bound waits for hidden/detached surfaces.

    False means a fallback yield, never a claim that native pixels were painted.
    The caller must recheck route lifetime after either result.
    """
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    def finish():
        if not future.done():
            future.set_result(True)
    def drawn():
        if not loop.is_closed():
            loop.call_soon_threadsafe(finish)
    cleanup = _install_draw_probe(panel, drawn)
    if cleanup is None:
        await asyncio.sleep(0)
        return False
    try:
        return await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError:
        return False
    finally:
        cleanup()
