"""Normal notebook acceptance requires native linkage and a live iOS canvas binding."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


def load_owner():
    path = Path(__file__).resolve().parents[2] / 'native_tests/tests/logisticsmobile/notebook_checks.py'
    package = ModuleType('notebook_gate_fixture'); package.__path__ = []
    checks = ModuleType('notebook_gate_fixture.web_checks'); checks.wait_for_text = Mock()
    name = 'notebook_gate_fixture.notebook_checks'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'notebook_gate_fixture': package, 'notebook_gate_fixture.web_checks': checks, name: module}):
        spec.loader.exec_module(module)
    return module


class NativeNotebookReleaseGateTests(unittest.TestCase):
    def fixture(self):
        self.owner = load_owner()
        class MainWindow: pass
        class SceneBackend(MainWindow): pass
        window = NS(isKindOfClass=Mock(return_value=True))
        backend = SceneBackend(); backend.native = window
        app = NS(main_window=NS(_impl=backend))
        panel = NS(web=NS(_impl=NS(native=NS(window=window))), pen_input=NS(enabled=True, view_id='a' * 32))
        state = {'native_pen': True, 'native_nonce': 'a' * 32, 'input_view': 'a' * 32}
        objc = ModuleType('rubicon.objc'); objc.ObjCClass = Mock(return_value=object())
        toga = ModuleType('toga_iOS.window'); toga.MainWindow = MainWindow
        return app, panel, state, {'rubicon.objc': objc, 'toga_iOS.window': toga}

    def verify(self, app, panel, state, frameworks):
        with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.app'), patch.dict(sys.modules, frameworks):
            self.owner.verify_native_pencil_binding(app, panel, state)

    def test_scene_backend_with_live_compiled_binding_passes(self):
        self.verify(*self.fixture())

    def test_missing_compiled_class_or_disabled_binding_cannot_pass_via_dom(self):
        for failure in ('window', 'binding'):
            with self.subTest(failure=failure):
                app, panel, state, frameworks = self.fixture()
                if failure == 'window': app.main_window._impl.native.isKindOfClass.return_value = False
                else: panel.pen_input.enabled = False
                with self.assertRaises(AssertionError): self.verify(app, panel, state, frameworks)

    def test_stale_or_missing_nonce_fails_the_release_gate(self):
        for update in ({'native_nonce': None}, {'input_view': 'b' * 32}, {'native_pen': False}):
            with self.subTest(update=update):
                app, panel, state, frameworks = self.fixture(); state.update(update)
                with self.assertRaises(AssertionError): self.verify(app, panel, state, frameworks)

    def test_android_does_not_import_or_require_uikit(self):
        owner = load_owner()
        with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_android.app'), patch.dict(sys.modules, {'rubicon.objc': None, 'toga_iOS.window': None}):
            owner.verify_native_pencil_binding(NS(), NS(), {})
