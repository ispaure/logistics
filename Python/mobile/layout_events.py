"""Coalesced reader layout wakeups; no timer and no retained reader owners."""
from commonUtils.runtime.signals import CoalescedSignal


def layout_waiter(app):
    signal = getattr(app, '_reader_layout_signal', None)
    if signal is None:
        app._reader_layout_signal = signal = CoalescedSignal()
    return signal.waiter()


def notify_layout(app):
    signal = getattr(app, '_reader_layout_signal', None)
    if signal is not None:
        signal.notify()


def native_resize_changed(app, widget):
    """Android global-layout notifications also fire for unchanged child text."""
    if widget is not app.main_window or not type(app._impl).__module__.startswith('toga_android.'):
        return True
    adapter = app.native_host.adapter
    if adapter is None:
        return True
    native, bar = adapter.impl.native, adapter.impl.native_navigationview
    geometry = (native.getWidth(), native.getHeight(), native.getPaddingLeft(), native.getPaddingTop(),
                native.getPaddingRight(), native.getPaddingBottom(), bar.getWidth(), bar.getVisibility(),
                adapter.mode, app.native_host.state.destination, id(app.body))
    if geometry == getattr(app, '_android_resize_geometry', None):
        return False
    app._android_resize_geometry = geometry
    return True
