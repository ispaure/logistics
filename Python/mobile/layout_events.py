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
    from .keyboard import picker_keyboard_visible
    picker_ime = bool(getattr(app, '_editor_picker', None)) and picker_keyboard_visible(app, adapter)
    geometry = (native.getWidth(), native.getHeight(), native.getPaddingLeft(), native.getPaddingTop(),
                native.getPaddingRight(), native.getPaddingBottom(), bar.getWidth(), bar.getVisibility(),
                adapter.mode, app.native_host.state.destination, id(app.body),
                getattr(adapter, 'keyboard_chrome', None) is not None,
                picker_ime,
                getattr(getattr(app, 'workspace', None), 'active', None))
    if geometry == getattr(app, '_android_resize_geometry', None):
        return False
    app._android_resize_geometry = geometry
    return True


def defer_host_resize(app, widget, callback):
    """Keep UIKit toolkit sizing synchronous; defer only host UI mutations."""
    if not type(getattr(app, '_impl', None)).__module__.startswith('toga_iOS.'):
        return False
    app._pending_host_resize = (widget, callback)
    if not getattr(app, '_host_resize_scheduled', False):
        app._host_resize_scheduled = True
        def deliver():
            app._host_resize_scheduled = False
            current, notify = app._pending_host_resize
            app._pending_host_resize = None
            if getattr(app, 'active_host', True) or getattr(app, '_reset_scheduled', False):
                notify(current)
        app.loop.call_soon(deliver)
    return True
