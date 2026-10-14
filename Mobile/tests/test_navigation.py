"""Shared state and dummy-host contracts; actual adapters have native cases."""
import unittest
import toga
from logisticsmobile.navigation import NavigationState
from logisticsmobile.native_navigation import NativeNavigationHost
from logisticsmobile.routing import Routes


class NavigationTests(unittest.TestCase):
    def test_back_is_destination_local_and_preserves_screen_and_guard(self):
        host = NativeNavigationHost()
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
        host = NativeNavigationHost(on_select=lambda key: key != 'settings')
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
