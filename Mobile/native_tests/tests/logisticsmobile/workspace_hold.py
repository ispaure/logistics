"""Long-lived actual app workspace with synthetic ordinary documents only."""
import asyncio
import json
import os
from pathlib import Path
from commonUtils.persistence import atomic_write_json
from commonUtils.runtime.platform import get_os, OS


async def hold_workspace(app):
    root = app.storage_root
    previous = json.loads((root / 'probe.json').read_text()) if (root / 'probe.json').exists() else {}
    boots, sequence = previous.get('boots', 0) + 1, previous.get('sequence', 0)
    if previous.get('document_id'):
        app.open_document(previous['document_id'])
    app.show_documents()
    while True:
        await asyncio.sleep(.2)
        control = root / 'control.json'
        command = json.loads(control.read_text()) if control.exists() else {}
        action = None
        if command.get('sequence', 0) > sequence:
            sequence, action = command['sequence'], command.get('action')
            if action == 'edit':
                app.show_documents()
                app.editor.value = command['text']
            elif action == 'type':
                if get_os() is not OS.IOS:
                    raise ValueError('Native insertText probe is an Apple operation.')
                app.editor._impl.native.insertText(command['text'])
            elif action == 'create':
                app.new_document()
                app.name.value = command['name']
                app.editor.value = command['text']
                app.show_documents()
            elif action == 'new_prompt':
                app.choose_document_type()
            elif action == 'chat':
                app.show_chat()
            elif action == 'activate':
                app.open_document(command['resource'])
                app.show_documents()
            elif action == 'select':
                if app.select_destination(command['destination']):
                    app.native_host.activate(command['destination'])
            elif action == 'focus':
                app.editor.focus()
                if get_os() is OS.ANDROID:
                    from android.content import Context
                    from android.view.inputmethod import InputMethodManager
                    manager = app._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE)
                    manager.showSoftInput(app.editor._impl.native, InputMethodManager.SHOW_IMPLICIT)
            elif action == 'blur':
                if get_os() is OS.IOS:
                    app.editor._impl.native.resignFirstResponder()
                else:
                    from android.content import Context
                    manager = app._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE)
                    manager.hideSoftInputFromWindow(app.editor._impl.native.getWindowToken(), 0)
            elif action == 'rotate':
                from rubicon.objc import ObjCClass
                preferences = ObjCClass('UIWindowSceneGeometryPreferencesIOS').alloc().initWithInterfaceOrientations(
                    8 if command['orientation'] == 'landscape' else 2)
                app.main_window._impl.native.windowScene.requestGeometryUpdateWithPreferences(preferences, errorHandler=None)
        app.save_workspace()
        diagnostics = app.native_host.diagnostics()
        diagnostics['workspace'] = app.adaptive.diagnostics()
        if get_os() is OS.ANDROID:
            from android.graphics import Rect
            from android.os import Debug
            own, visible = Rect(), Rect()
            app.editor._impl.native.getGlobalVisibleRect(own)
            app.editor._impl.native.getWindowVisibleDisplayFrame(visible)
            diagnostics.update(activity=int(app._impl.native.hashCode()), pss_kib=int(Debug.getPss()),
                               editor_bottom=own.bottom, visible_bottom=visible.bottom)
        documents = {session.resource: app.store.open(session.resource).text
                     for session in app.workspace.sessions.values()
                     if session.provider == 'managed-text' and not session.transient}
        report = diagnostics | dict(boots=boots, sequence=sequence, pid=os.getpid(),
            destination=app.native_host.state.destination, document_id=app.current.id,
            text=app.current.text, recovered_text=app.store.open(app.current.id).text,
            documents=documents, source=json.loads(Path(__import__('logisticsmobile').__file__).with_name('source.json').read_text()))
        atomic_write_json(root / 'probe.json', report)
        if action == 'recreate':
            app._impl.native.recreate()
            return
