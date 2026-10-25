"""UIKit pop callbacks return to the retained origin within the selected tab."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import toga

from commonUtils.ui.native.navigation import NativeNavigationHost
from mobile.navigation import DESTINATION_ITEMS
from mobile.routes import MobileRoutes


class Navigation:
    def __init__(self):
        self.viewControllers = [object()]

    def popToViewController(self, controller, *, animated):
        self.viewControllers = self.viewControllers[:self.viewControllers.index(controller) + 1]


class NativeReaderReturnTests(unittest.TestCase):
    def setUp(self):
        self.host = NativeNavigationHost(DESTINATION_ITEMS)
        self.app = SimpleNamespace(select_destination=Mock(return_value=True),
            loop=Mock(), adaptive=SimpleNamespace(render=Mock()), visible_reader=Mock(return_value=None),
            reader_tool_back=Mock(return_value=None))
        self.guard = Mock(return_value=True)
        self.routes = MobileRoutes(self.app, self.host, guard=self.guard, changed=Mock())
        self.navigation = [Navigation() for _ in self.host.destinations]

        def push(destination, panel, title):
            controller = SimpleNamespace(title=title)
            self.navigation[self.host.destinations.index(destination)].viewControllers.append(controller)
            return SimpleNamespace(controller=controller)

        self.host.adapter = SimpleNamespace(navigation=self.navigation, push=push,
            navigation_for=lambda destination: self.navigation[self.host.destinations.index(destination)],
            destination_for_navigation=lambda nav: self.host.destinations[self.navigation.index(nav)],
            route_depth=lambda nav: len(nav.viewControllers) - 1,
            containers=[(None, nav.viewControllers[0]) for nav in self.navigation], release_pane=Mock())
        self.browser = toga.Label('Retained browser with its scroll and query')
        self.routes.show(self.browser, destination='files', root=True)

    def pop(self):
        nav = self.navigation[self.host.destinations.index(self.host.state.destination)]
        nav.viewControllers.pop()
        self.routes.native_popped(nav)

    def test_native_document_mode_switch_reuses_controller_and_one_back_returns_to_origin(self):
        self.routes.show(toga.Label('Editor'), route='editor', title='Note.md')
        controller = self.routes.screens['files'][-1][2].controller
        preview = toga.Label('Preview')
        self.routes.show(preview, route='preview', title='Note.md')
        self.assertEqual(len(self.routes.screens['files']), 1)
        self.assertIs(self.routes.screens['files'][-1][2].controller, controller)
        self.assertIs(self.routes.body().children[0], preview)
        self.pop()
        self.assertIs(self.routes.body().children[0], self.browser)

    def test_native_tools_back_keeps_reader_then_returns_to_browser(self):
        reader = toga.Label('Reader')
        self.routes.show(reader, route='reader:fixture')
        self.routes.show(toga.Label('Tools'), route='reader-tools:fixture')
        self.pop()
        self.assertEqual(self.host.state.destination, 'files')
        self.assertIs(self.routes.body().children[0], reader)
        self.pop()
        self.assertEqual(self.host.state.destination, 'files')
        self.assertIs(self.routes.body().children[0], self.browser)
        self.assertFalse(self.routes.origins)

    def test_explicit_back_obeys_guard_and_returns_to_origin(self):
        self.routes.show(toga.Label('Reader'), route='reader:fixture')
        self.guard.return_value = False
        self.assertTrue(self.routes.back())
        self.assertEqual(self.host.state.destination, 'files')
        self.guard.return_value = True
        self.assertTrue(self.routes.back())
        self.assertEqual(self.host.state.destination, 'files')
        self.assertIs(self.routes.body().children[0], self.browser)

    def test_reader_opened_in_documents_returns_to_documents_root(self):
        self.host.activate('documents')
        self.routes.show(toga.Label('Reader'), route='reader:fixture')
        self.pop()
        self.assertEqual(self.host.state.destination, 'documents')
        self.assertFalse(self.routes.origins)

    def test_native_back_from_close_prompt_cancels_the_pending_reader_exit(self):
        self.app.keep_reader_editing = Mock()
        self.routes.show(toga.Label('Reader'), route='reader:fixture')
        self.routes.show(toga.Label('Close prompt'), route='close:fixture')
        self.pop()
        self.app.keep_reader_editing.assert_called_once_with('fixture')
        self.assertEqual(self.routes.screens['files'][-1][0], 'reader:fixture')

    def test_native_swipe_pop_restores_same_origin_panel_in_each_tab(self):
        for destination in ('home', 'files', 'documents'):
            with self.subTest(destination=destination):
                source = toga.TextInput(value='Retained search')
                self.routes.show(source, destination=destination, root=True)
                panel = self.routes.body()
                self.routes.show(toga.Label('Document'), route='reader:any-kind')
                self.assertEqual(self.host.state.destination, destination)
                self.pop()
                self.assertEqual(self.host.state.destination, destination)
                self.assertIs(self.routes.body(), panel)
                self.assertEqual(source.value, 'Retained search')
                self.assertFalse(self.routes.origins)
