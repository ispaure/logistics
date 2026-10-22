"""Lazy controller assembly and explicit read/write host capabilities."""
from types import SimpleNamespace
import unittest
from services.workflow_host import HostService, HostAttribute, StateAttribute
from mobile.composition.assembly import composed_workflow


class CompositionContractTests(unittest.TestCase):
    def test_explicit_factory_remains_authoritative_for_compatibility_access(self):
        class Controller:
            METHODS = ('invoke',)
            FIELDS = ()

        @composed_workflow('controller', Controller)
        class App:
            def controller(self):
                return SimpleNamespace(invoke=lambda: 'explicit owner')

        self.assertEqual(App().invoke(), 'explicit owner')

    def test_readonly_capabilities_and_writable_state_are_distinct(self):
        class Consumer:
            capability = HostService('value')
            compatibility = HostAttribute('value')
            own = StateAttribute('state', 'value')
        app = SimpleNamespace(value=1)
        consumer = Consumer()
        consumer.app, consumer.state = app, SimpleNamespace(value=2)
        with self.assertRaises(AttributeError):
            consumer.capability = 3
        with self.assertRaises(AttributeError):
            del consumer.capability
        consumer.compatibility = 3
        consumer.own = 4
        self.assertEqual((app.value, consumer.state.value), (3, 4))

    def test_compatibility_access_constructs_once_and_never_copies_owner_state(self):
        created = []
        class Controller:
            METHODS = ('invoke',)
            FIELDS = ('state',)
            def __init__(self, app):
                created.append(app)
                self.state = 1
            def invoke(self):
                return self.state
        @composed_workflow('controller', Controller)
        class App:
            pass
        app = App()
        self.assertEqual(created, [])
        self.assertEqual(app.invoke(), 1)
        app.state = 7
        self.assertEqual(app.controller().state, 7)
        self.assertEqual(app.invoke(), 7)
        self.assertEqual(created, [app])
        replacement = App()
        self.assertEqual(replacement.state, 1)
        self.assertEqual(app.state, 7)
