"""Opt-in, long-lived native test host for external resize/recreation checks."""
import asyncio
import json
import os
import toga
from toga.style import Pack
from commonUtils.ui.native.navigation import NativeNavigationHost
from logisticsmobile.navigation import DESTINATION_ITEMS
from commonUtils.persistence import atomic_write_json
from commonUtils.runtime.platform import get_os, OS


async def hold_navigation(app):
    root = app.storage_root
    manifest = root / 'probe.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else {}
    boots = previous.get('boots', 0) + 1
    sequence = previous.get('sequence', 0)
    original = app.main_window.content
    app.adaptive.uninstall()
    app.routes.uninstall()
    app.native_host.uninstall()
    host = NativeNavigationHost(DESTINATION_ITEMS)
    if previous.get('destination') in host.bodies:
        host.activate(previous['destination'])

    def changed(widget, **kwargs):
        app.current.text = widget.value
        app.store.checkpoint(app.current)

    editor = toga.MultilineTextInput(value=app.current.text, on_change=changed, style=Pack(flex=1))
    app.editor = editor  # Existing focus-loss checkpoint must read the visible draft.
    for key, box in host.bodies.items():
        box.add(toga.Label(key.title(), style=Pack(margin=12)))
    host.bodies['documents'].add(editor)
    app.main_window.content = host.root
    host.install(app.main_window)
    try:
        while True:
            await asyncio.sleep(.2)
            command = root / 'control.json'
            data = json.loads(command.read_text()) if command.exists() else {}
            action = None
            if data.get('sequence', 0) > sequence:
                sequence = data['sequence']
                action = data.get('action')
                if action == 'edit':
                    editor.value = data['text']
                    changed(editor)
                elif action == 'select':
                    host.activate(data['destination'])
                elif action == 'focus':
                    editor.focus()
                    if get_os() is OS.ANDROID:
                        from android.content import Context
                        from android.view.inputmethod import InputMethodManager
                        manager = app._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE)
                        manager.showSoftInput(editor._impl.native, InputMethodManager.SHOW_IMPLICIT)
                elif action == 'blur':
                    if get_os() is OS.IOS:
                        editor._impl.native.resignFirstResponder()
                    else:
                        from android.content import Context
                        manager = app._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE)
                        manager.hideSoftInputFromWindow(editor._impl.native.getWindowToken(), 0)
                elif action == 'rotate':
                    if get_os() is not OS.IOS:
                        raise ValueError('Scene geometry requests are Apple operations.')
                    from rubicon.objc import ObjCClass
                    mask = 8 if data['orientation'] == 'landscape' else 2
                    preferences = ObjCClass('UIWindowSceneGeometryPreferencesIOS').alloc().initWithInterfaceOrientations(mask)
                    app.main_window._impl.native.windowScene.requestGeometryUpdateWithPreferences(
                        preferences, errorHandler=None)
            diagnostics = host.diagnostics()
            if get_os() is OS.ANDROID:
                from android.os import Debug
                diagnostics['pss_kib'] = int(Debug.getPss())
                diagnostics['activity'] = int(app._impl.native.hashCode())
                from android.graphics import Rect
                visible, bounds = Rect(), Rect()
                editor._impl.native.getWindowVisibleDisplayFrame(visible)
                editor._impl.native.getGlobalVisibleRect(bounds)
                diagnostics['editor_bottom'] = int(bounds.bottom)
                diagnostics['visible_bottom'] = int(visible.bottom)
            else:
                import resource
                diagnostics['peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            report = diagnostics | dict(schema=1, suite='navigation-lifecycle-probe',
                boots=boots, sequence=sequence, pid=os.getpid(), destination=host.state.destination,
                document_id=app.current.id, text=editor.value,
                recovered_text=app.store.open(app.current.id).text)
            atomic_write_json(manifest, report)
            if action == 'recreate':
                if get_os() is not OS.ANDROID:
                    raise ValueError('Activity recreation is an Android operation.')
                app._impl.native.recreate()
                return
    finally:
        host.dispose()
        app.main_window.content = original
        app.native_host.install(app.main_window)
        app.routes.install()
        app.adaptive.install()
