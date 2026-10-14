"""Native controller proof, kept separate from ordinary feature UI cases."""
import asyncio
import json
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.runtime.platform import get_os, OS
from logisticsmobile.native_navigation import NativeNavigationHost


async def exercise_navigation(app):
    original = app.main_window.content
    original_widgets = set(app.widgets.keys())
    original_document = (app.current.id, app.current.text)
    host = NativeNavigationHost()
    editor = toga.MultilineTextInput(value='Native navigation draft', style=Pack(flex=1))
    for key, box in host.bodies.items():
        box.add(toga.Label(key.title(), style=Pack(margin=12)))
    host.bodies['documents'].add(editor)
    app.main_window.content = host.root
    try:
        host.install(app.main_window)
        await asyncio.sleep(.5)
        assert len(host.root.content) == 3
        for destination in ('documents', 'settings', 'files', 'documents'):
            host.activate(destination)
            await asyncio.sleep(.1)
            assert host.state.destination == destination
            assert host.root.current_tab.text.lower() == destination
        assert editor.value == 'Native navigation draft'
        if get_os() is OS.ANDROID:
            host.adapter.impl.native_navigationview.setSelectedItemId(3)
            assert host.state.destination == 'settings'
            assert host.root.current_tab.text == 'Settings'
            host.adapter.impl.native_navigationview.setSelectedItemId(2)
            assert host.state.destination == 'documents'
        else:
            native = host.adapter.controller
            native.selectedViewController = host.adapter.navigation[2]
            native.tabBar_didSelectItem_(native.tabBar, host.adapter.navigation[2].tabBarItem)
            assert host.state.destination == 'settings'
            host.activate('documents')
        editor.value = 'Draft survives native containers'
        diagnostics = host.diagnostics()
        assert diagnostics['main_thread']
        screenshots = []

        def capture(name):
            path = app.storage_root / ('navigation-' + name + '.png')
            if get_os() is OS.IOS:
                # Toga's cropped content image omits presented controllers and
                # assumes the main screen's scale. Capture the complete window.
                from rubicon.objc import Block, objc_id
                from toga_iOS.libs import UIGraphicsImageRenderer
                from toga_iOS.images import nsdata_to_bytes
                native = app.main_window._impl.native
                renderer = UIGraphicsImageRenderer.alloc().initWithSize(native.bounds.size)
                def render(context):
                    native.drawViewHierarchyInRect(native.bounds, afterScreenUpdates=True)
                path.write_bytes(nsdata_to_bytes(renderer.PNGDataWithActions(Block(render, None, objc_id))))
            else:
                app.main_window.as_image().save(path)
            screenshots.append(str(path))

        await asyncio.sleep(.4)
        capture('tabs')
        if get_os() is OS.IOS:
            adapter = host.adapter
            assert diagnostics['contained']
            detail = toga.Box(children=[toga.Label('Native folder detail')],
                              style=Pack(direction=COLUMN, flex=1))
            adapter.push('files', detail, 'Folder')
            host.activate('files')
            await asyncio.sleep(.3)
            assert len(adapter.navigation[0].viewControllers) == 2
            capture('stack')
            adapter.pop('files')
            assert len(adapter.navigation[0].viewControllers) == 1
            leading = toga.Box(children=[toga.Label('Open documents')],
                               style=Pack(direction=COLUMN, flex=1))
            detail = toga.Box(children=[toga.MultilineTextInput(value=editor.value, style=Pack(flex=1))],
                              style=Pack(direction=COLUMN, flex=1))
            panes = adapter.prove_split(leading, detail)
            await asyncio.sleep(.5)
            adapter.split.view.layoutIfNeeded()
            assert len(panes) == 2 and adapter.split.presentingViewController is not None
            assert float(panes[1].native.bounds.size.width) > 0
            collapsed = adapter.split.isCollapsed
            diagnostics['split_collapsed'] = bool(collapsed() if callable(collapsed) else collapsed)
            diagnostics['horizontal_size_class'] = int(adapter.split.traitCollection.horizontalSizeClass)
            diagnostics['split_detail_width'] = float(panes[1].native.bounds.size.width)
            diagnostics['split_usable_detail_width'] = float(panes[1].width)
            capture('split')
            adapter.split.dismissViewControllerAnimated(False, completion=None)
            await asyncio.sleep(.2)
            host.activate('documents')
            editor.focus()
            await asyncio.sleep(.5)
            diagnostics['editor_focused'] = bool(editor._impl.native.isFirstResponder)
            assert diagnostics['editor_focused']
            capture('keyboard')
            editor._impl.native.resignFirstResponder()
            fallback = NativeNavigationHost(prefer_sidebar=False)
            app.main_window.content = fallback.root
            try:
                fallback.install(app.main_window)
                fallback.activate('settings')
                await asyncio.sleep(.2)
                assert fallback.root.current_tab.text == 'Settings'
                assert fallback.diagnostics()['sidebar_used'] is False
                diagnostics['legacy_bar_path_checked'] = True
            finally:
                fallback.dispose()
                app.main_window.content = host.root
        else:
            adapter = host.adapter
            adapter.set_mode('rail')
            assert 'NavigationRailView' in adapter.diagnostics()['native_tabs']
            host.activate('settings')
            assert host.state.destination == 'settings'
            capture('rail')
            adapter.set_mode('bottom')
            assert 'BottomNavigationView' in adapter.diagnostics()['native_tabs']
            host.activate('documents')
            await asyncio.sleep(.3)
            expected = 'rail' if adapter.diagnostics()['width'] >= 600 else 'bottom'
            assert adapter.mode == expected
            assert editor.value == 'Draft survives native containers'
            editor.focus()
            from android.content import Context
            from android.view.inputmethod import InputMethodManager
            manager = adapter.impl._native_activity.getSystemService(Context.INPUT_METHOD_SERVICE)
            manager.showSoftInput(editor._impl.native, InputMethodManager.SHOW_IMPLICIT)
            await asyncio.sleep(.5)
            diagnostics['editor_focused'] = bool(editor._impl.native.hasFocus())
            assert diagnostics['editor_focused']
            capture('keyboard')
            manager.hideSoftInputFromWindow(editor._impl.native.getWindowToken(), 0)
            diagnostics['resize_events'] = adapter.layout_events
            assert adapter.layout_events > 0
        assert editor.value == 'Draft survives native containers'
        print('LOGISTICS_NAVIGATION_PROOF=' + json.dumps(diagnostics | {'screenshots': screenshots}), flush=True)
        result = diagnostics | {'screenshots': screenshots}
    finally:
        host.dispose()
        app.main_window.content = original
        assert (app.current.id, app.current.text) == original_document
        assert set(app.widgets.keys()) == original_widgets
    result['widget_cleanup_verified'] = True
    return result
