"""UIKit pop callbacks retain the browser origin across the Documents tab."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import toga

from commonUtils.ui.native.navigation import NativeNavigationHost
from logisticsmobile.navigation import DESTINATION_ITEMS
from logisticsmobile.routes import MobileRoutes


class Navigation:
    def __init__(self):
        self.viewControllers = [object()]

    def popToViewController(self, controller, *, animated):
        self.viewControllers = self.viewControllers[:self.viewControllers.index(controller) + 1]


class NativeReaderReturnTests(unittest.TestCase):
    def setUp(self):
        self.host = NativeNavigationHost(DESTINATION_ITEMS)
        self.app = SimpleNamespace(select_destination=Mock(return_value=True),
            loop=Mock(), adaptive=SimpleNamespace(render=Mock()))
        self.guard = Mock(return_value=True)
        self.routes = MobileRoutes(self.app, self.host, guard=self.guard, changed=Mock())
        self.navigation = [Navigation() for _ in self.host.destinations]

        def push(destination, panel, title):
            controller = SimpleNamespace(title=title)
            self.navigation[self.host.destinations.index(destination)].viewControllers.append(controller)
            return SimpleNamespace(controller=controller)

        self.host.adapter = SimpleNamespace(navigation=self.navigation, push=push,
            containers=[(None, nav.viewControllers[0]) for nav in self.navigation], release_pane=Mock())
        self.browser = toga.Label('Retained browser with its scroll and query')
        self.routes.show(self.browser, destination='files', root=True)

    def pop(self):
        nav = self.navigation[self.host.destinations.index('documents')]
        nav.viewControllers.pop()
        self.routes.native_popped(nav)

    def test_native_tools_back_keeps_reader_then_returns_to_browser(self):
        reader = toga.Label('Reader')
        self.routes.show(reader, destination='documents', route='reader:fixture')
        self.routes.show(toga.Label('Tools'), route='reader-tools:fixture')
        self.pop()
        self.assertEqual(self.host.state.destination, 'documents')
        self.assertIs(self.routes.body().children[0], reader)
        self.pop()
        self.assertEqual(self.host.state.destination, 'files')
        self.assertIs(self.routes.body().children[0], self.browser)
        self.assertFalse(self.routes.origins)

    def test_explicit_back_obeys_guard_and_returns_to_origin(self):
        self.routes.show(toga.Label('Reader'), destination='documents', route='reader:fixture')
        self.guard.return_value = False
        self.assertTrue(self.routes.back())
        self.assertEqual(self.host.state.destination, 'documents')
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
