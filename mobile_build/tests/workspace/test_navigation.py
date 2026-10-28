"""Shared state and dummy-host contracts; actual adapters have native cases."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import toga
from mobile.navigation import NavigationState, DESTINATION_ITEMS
from commonUtils.ui.native.navigation import NativeNavigationHost
from commonUtils.ui.native.routes import Routes


class NavigationTests(unittest.TestCase):
    def test_apple_destination_items_follow_late_bar_traits_without_navigation(self):
        import asyncio
        from mobile.navigation import install_apple_destination_layout
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        native = SimpleNamespace(window=None,
            bounds=SimpleNamespace(size=SimpleNamespace(width=1000, height=700)))
        container = SimpleNamespace(on_native_layout=Mock())
        host = SimpleNamespace(changing=False, adapter=SimpleNamespace(
            controller=SimpleNamespace(view=native)), window=SimpleNamespace(
            _impl=SimpleNamespace(container=container), app=SimpleNamespace(loop=loop)))
        original = container.on_native_layout
        edge = [0]
        async def exercise():
            with patch('mobile.ios_toolbar.vertical_edge', side_effect=lambda controller: edge[0]), \
                    patch('mobile.navigation.refresh_apple_tab_items') as refresh:
                install_apple_destination_layout(host)
                await asyncio.sleep(0)
                refresh.assert_not_called()
                # Rubicon exposes UIView.window as a callable on this backend.
                native.window = lambda: SimpleNamespace(ptr=SimpleNamespace(value=1))
                def native_relayout(value):
                    self.assertTrue(host.changing)
                    container.on_native_layout(container)
                refresh.side_effect = native_relayout
                container.on_native_layout(container)
                container.on_native_layout(container)
                await asyncio.sleep(0)
                self.assertEqual(refresh.call_count, 1)
                # Inner landscape traits can settle without changing dimensions.
                edge[0] = 2
                container.on_native_layout(container)
                await asyncio.sleep(0)
                self.assertEqual(refresh.call_count, 2)
                container.on_native_layout(container)
                await asyncio.sleep(0)
                self.assertEqual(refresh.call_count, 2)
                edge[0] = 0
                container.on_native_layout(container)
                host.adapter = None  # Queued layout must not resurrect a closed host.
                await asyncio.sleep(0)
                self.assertEqual(refresh.call_count, 2)
                self.assertFalse(host.changing)
        loop.run_until_complete(exercise())
        self.assertGreater(original.call_count, 1)

    def test_android_rotation_rebinds_tab_without_selecting_or_retiring_its_reader(self):
        from commonUtils.ui.native.navigation import AndroidNavigation
        selected = Mock()
        host = NativeNavigationHost(DESTINATION_ITEMS, on_select=selected)
        routes = Routes(host, guard=lambda: True, changed=lambda body: None)
        routes.show(toga.Label('Workspaces'), destination='files', root=True)
        reader = toga.Label('Markdown remains open')
        routes.show(reader, destination='files', route='private:note')
        selected.reset_mock()
        adapter = object.__new__(AndroidNavigation)
        adapter.host, adapter.mode = host, 'rail'
        adapter.keyboard_chrome = None
        adapter.bottom, adapter.rail = Mock(), Mock()
        adapter.impl = SimpleNamespace(native_navigationview=adapter.rail,
            native=Mock(), native_content=Mock(), options=[Mock() for _ in host.destinations],
            onItemSelectedListener=Mock(), _native_activity=Mock(),
            set_current_tab_index=Mock(side_effect=lambda index: host._selected(host.root)))
        layout = Mock(HORIZONTAL=0, VERTICAL=1)
        with patch.dict('sys.modules', {
            'android.widget': SimpleNamespace(LinearLayout=layout),
            'android.view': SimpleNamespace(ContextThemeWrapper=Mock()),
            'com.google.android.material.navigationrail': SimpleNamespace(NavigationRailView=Mock()),
            'com.google.android.material': SimpleNamespace(R=Mock()),
        }):
            adapter.set_mode('bottom')
            adapter.set_mode('rail')
        selected.assert_not_called()
        self.assertFalse(host.changing)
        self.assertIs(routes.body('files').children[0], reader)
        self.assertEqual(host.state.routes['files'], ['private:note'])

    def test_apple_tab_rebuild_preserves_titles_glyphs_and_selection(self):
        from mobile.navigation import refresh_apple_tab_items
        selected = Mock()
        host = NativeNavigationHost(DESTINATION_ITEMS, on_select=selected)
        images = [object() for _ in host.destinations]
        navigation = [SimpleNamespace(tabBarItem=SimpleNamespace(image=image)) for image in images]
        refresh = Mock()
        host.adapter = SimpleNamespace(navigation=navigation, impl=SimpleNamespace(refresh_tabs=refresh))
        factory = Mock()
        factory.alloc.return_value.initWithTitle.side_effect = lambda title, image, tag: SimpleNamespace(
            title=title, image=image, tag=tag)
        bridge = SimpleNamespace(ObjCClass=Mock(return_value=factory))
        with patch.dict('sys.modules', {'rubicon.objc': bridge}):
            refresh_apple_tab_items(host)
        self.assertEqual([item.tabBarItem.title for item in navigation], list(host.labels))
        self.assertEqual([item.tabBarItem.image for item in navigation], images)
        self.assertEqual([item.tabBarItem.tag for item in navigation], list(range(5)))
        self.assertEqual([item.tabBarItem.accessibilityLabel for item in navigation], list(host.labels))
        self.assertEqual(host.state.destination, 'home')
        self.assertEqual(host.root.current_tab.text, 'Home')
        selected.assert_not_called()
        refresh.assert_called_once_with()

    def test_back_is_destination_local_and_preserves_screen_and_guard(self):
        host = NativeNavigationHost(DESTINATION_ITEMS)
        allowed = [True]
        routes = Routes(host, guard=lambda: allowed[0], changed=lambda body: None)
        root = toga.Label('Open documents')
        editor = toga.MultilineTextInput(value='unsaved draft')
        routes.show(root, destination='documents', root=True)
        routes.show(editor, route='editor', title='Editor')
        routes.show(toga.Label('Preview'), route='preview', title='Preview')
        routes.show(toga.Label('Locations'), destination='files', root=True)
        routes.show(toga.Label('Folder'), route='browser', title='Folder')
        self.assertTrue(routes.back())
        self.assertFalse(routes.back())
        host.activate('documents')
        allowed[0] = False
        self.assertTrue(routes.back())
        self.assertEqual(host.state.routes['documents'], ['editor', 'preview'])
        allowed[0] = True
        self.assertTrue(routes.back())
        self.assertIs(routes.body().children[0], editor)
        self.assertEqual(editor.value, 'unsaved draft')
        routes.show(editor, route='editor')
        self.assertEqual(host.state.routes['documents'], ['editor'])
        routes.show(root, root=True)
        routes.show(editor, route='editor')
        self.assertEqual(editor.value, 'unsaved draft')

    def test_destination_routes_are_independent_and_back_does_not_switch_tabs(self):
        state = NavigationState(destination='files')
        state.push('folder')
        state.select('documents')
        state.push('editor')
        state.select('files')
        self.assertEqual(state.back(), 'folder')
        self.assertIsNone(state.back())
        self.assertEqual(state.destination, 'files')
        state.select('documents')
        self.assertEqual(state.back(), 'editor')
        with self.assertRaises(ValueError):
            state.select('unknown')

    def test_native_selection_guard_and_programmatic_activation(self):
        host = NativeNavigationHost(DESTINATION_ITEMS, on_select=lambda key: key != 'settings')
        self.assertEqual(host.root.current_tab.text, 'Home')
        host.activate('documents')
        self.assertEqual(host.state.destination, 'documents')
        host.root.current_tab = 'Settings'
        host._selected(host.root)
        self.assertEqual(host.root.current_tab.text, 'Documents')
        editor = toga.MultilineTextInput(value='draft')
        host.bodies['documents'].add(editor)
        host.activate('files')
        host.activate('documents')
        self.assertEqual(editor.value, 'draft')
        host.dispose()
