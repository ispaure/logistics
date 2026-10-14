"""Shared state and dummy-host contracts; actual adapters have native cases."""
import unittest
import toga
from logisticsmobile.navigation import NavigationState
from logisticsmobile.native_navigation import NativeNavigationHost


class NavigationTests(unittest.TestCase):
    def test_destination_routes_are_independent_and_back_does_not_switch_tabs(self):
        state = NavigationState()
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
        self.assertEqual(host.root.current_tab.text, 'Files')
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
