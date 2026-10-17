"""Native controller proof, kept separate from ordinary feature UI cases."""
import asyncio
import json
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.runtime.platform import get_os, OS
from commonUtils.ui.native.navigation import NativeNavigationHost
from logisticsmobile.navigation import DESTINATION_ITEMS
from .fixtures import capture_window


def assert_navigation_contrast(view):
    background = view.getBackground().getFillColor().getDefaultColor()
    def luminance(color):
        values = [((int(color) >> shift) & 255) / 255 for shift in (16, 8, 0)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055)**2.4 for value in values]
        return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    for colors in (view.getItemIconTintList(), view.getItemTextColor()):
        assert colors is not None
        foreground = colors.getDefaultColor()
        high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
        assert (high + .05) / (low + .05) >= 3, 'Inactive navigation items need visible contrast'


def assert_cold_iphone_tab_labels(app):
    """Inspect rendered labels before selection can repair their cached geometry."""
    from rubicon.objc import ObjCClass
    if ObjCClass('UIDevice').currentDevice.userInterfaceIdiom != 0:
        return
    tab = app.native_host.adapter.controller.tabBar
    tab.layoutIfNeeded()
    expected, seen = set(app.native_host.labels), set()
    content_views = [navigation.view for navigation in app.native_host.adapter.navigation]
    def value(obj, name):
        result = getattr(obj, name)
        return result() if callable(result) else result
    def inspect(view):
        if view in content_views:
            return  # Document/page labels must not satisfy navigation checks.
        if view.isKindOfClass(ObjCClass('UILabel')):
            text = str(value(view, 'text'))
            if text in expected:
                seen.add(text)
                natural = value(view, 'intrinsicContentSize')
                assert view.bounds.size.width >= natural.width - 1, ('Truncated tab', text, str(view.bounds), str(natural))
                assert view.bounds.size.height >= value(value(view, 'font'), 'pointSize'), ('Clipped tab', text)
        for child in value(view, 'subviews'):
            inspect(child)
    # Newer UIKit versions render floating/vertical tab labels beside the
    # UITabBar placeholder. Inspect the owning controller's complete hierarchy.
    inspect(app.native_host.adapter.controller.view)
    assert seen == expected, ('Missing cold-start tab labels', seen)


async def exercise_navigation(app):
    original = app.main_window.content
    original_widgets = set(app.widgets.keys())
    def descendants(widget):
        result = {widget.id}
        for child in getattr(widget, 'children', ()):
            result.update(descendants(child))
        if isinstance(widget, toga.OptionContainer):
            for item in widget.content:
                result.update(descendants(item.content))
        return result
    original_document = (app.current.id, app.current.text)
    app.adaptive.uninstall()
    app.routes.uninstall()
    app.native_host.uninstall()
    host = NativeNavigationHost(DESTINATION_ITEMS)
    editor = toga.MultilineTextInput(value='Native navigation draft', style=Pack(flex=1))
    for key, box in host.bodies.items():
        box.add(toga.Label(key.title(), style=Pack(margin=12)))
    host.bodies['documents'].add(editor)
    app.main_window.content = host.root
    proof_widgets = descendants(host.root)
    try:
        host.install(app.main_window)
        await asyncio.sleep(.5)
        assert len(host.root.content) == len(DESTINATION_ITEMS)
        for destination in ('documents', 'chat', 'settings', 'files', 'documents'):
            host.activate(destination)
            await asyncio.sleep(.1)
            assert host.state.destination == destination
            assert host.root.current_tab.text == host.labels[host.destinations.index(destination)]
        assert editor.value == 'Native navigation draft'
        if get_os() is OS.ANDROID:
            assert_navigation_contrast(host.adapter.impl.native_navigationview)
            host.adapter.impl.native_navigationview.setSelectedItemId(5)
            assert host.state.destination == 'settings'
            assert host.root.current_tab.text == 'Settings'
            host.adapter.impl.native_navigationview.setSelectedItemId(3)
            assert host.state.destination == 'documents'
        else:
            native = host.adapter.controller
            native.selectedViewController = host.adapter.navigation[4]
            native.tabBar_didSelectItem_(native.tabBar, host.adapter.navigation[4].tabBarItem)
            assert host.state.destination == 'settings'
            host.activate('documents')
        editor.value = 'Draft survives native containers'
        diagnostics = host.diagnostics()
        assert diagnostics['main_thread']
        screenshots = []

        async def capture(name):
            path = app.storage_root / ('navigation-' + name + '.png')
            await capture_window(app, path)
            screenshots.append(str(path))

        await asyncio.sleep(.4)
        await capture('tabs')
        if get_os() is OS.IOS:
            adapter = host.adapter
            assert diagnostics['contained']
            detail = toga.Box(children=[toga.Label('Native folder detail')],
                              style=Pack(direction=COLUMN, flex=1))
            adapter.push('files', detail, 'Folder')
            host.activate('files')
            await asyncio.sleep(.3)
            assert len(adapter.navigation[1].viewControllers) == 2
            await capture('stack')
            adapter.pop('files')
            assert len(adapter.navigation[1].viewControllers) == 1
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
            await capture('split')
            adapter.split.dismissViewControllerAnimated(False, completion=None)
            await asyncio.sleep(.2)
            host.activate('documents')
            editor.focus()
            await asyncio.sleep(.5)
            diagnostics['editor_focused'] = bool(editor._impl.native.isFirstResponder)
            assert diagnostics['editor_focused']
            await capture('keyboard')
            editor._impl.native.resignFirstResponder()
            fallback = NativeNavigationHost(DESTINATION_ITEMS, prefer_sidebar=False)
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
            assert_navigation_contrast(adapter.impl.native_navigationview)
            assert 'NavigationRailView' in adapter.diagnostics()['native_tabs']
            host.activate('settings')
            assert host.state.destination == 'settings'
            await capture('rail')
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
            await capture('keyboard')
            manager.hideSoftInputFromWindow(editor._impl.native.getWindowToken(), 0)
            diagnostics['resize_events'] = adapter.layout_events
            assert adapter.layout_events > 0
        assert editor.value == 'Draft survives native containers'
        print('LOGISTICS_NAVIGATION_PROOF=' + json.dumps(diagnostics | {'screenshots': screenshots}), flush=True)
        result = diagnostics | {'screenshots': screenshots}
    finally:
        host.dispose()
        app.main_window.content = original
        app.native_host.install(app.main_window)
        app.routes.install()
        app.adaptive.install()
        assert (app.current.id, app.current.text) == original_document
        # Home can legitimately refresh on restoring the selected native tab.
        # Verify disposal of the temporary proof hierarchy itself.
        assert not proof_widgets.intersection(app.widgets.keys())
    result['widget_cleanup_verified'] = True
    return result
