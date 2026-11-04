"""UIKit hover observer lifecycle and capability checks, without hardware claims."""
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from commonUtils.testing.stages import TestStage
from features.notebooks.mobile import ios_input

TEST_STAGE = TestStage.REGRESSION


class PencilHoverTests(unittest.TestCase):
    def test_install_observes_only_pencil_without_cancelling_other_gestures(self):
        native, target, gesture, recognizer = Mock(), Mock(), Mock(), Mock()
        target_type = Mock()
        target_type.alloc.return_value.init.return_value = target
        recognizer.alloc.return_value.initWithTarget.return_value = gesture
        web = SimpleNamespace(_impl=SimpleNamespace(native=native))
        fake = SimpleNamespace(SEL=lambda value: value, ns_from_py=lambda value: value)
        with patch.dict(sys.modules, {'rubicon.objc': fake}), patch.object(ios_input, '_target_class', return_value=target_type):
            observer = ios_input.PencilHover(web, recognizer)
        self.assertEqual(gesture.allowedTouchTypes, [2])
        self.assertTrue(gesture.requiresExclusiveTouchType)
        self.assertFalse(gesture.cancelsTouchesInView)
        self.assertFalse(gesture.delaysTouchesBegan)
        self.assertFalse(gesture.delaysTouchesEnded)
        self.assertIs(gesture.delegate, target)
        self.assertIs(target.owner(), observer)
        native.addGestureRecognizer.assert_called_once_with(gesture)

    def observer(self):
        observer = object.__new__(ios_input.PencilHover)
        observer.closed = False
        observer.native = Mock(bounds=SimpleNamespace(size=SimpleNamespace(width=400., height=700.)))
        observer.target = Mock()
        observer.gesture = Mock()
        return observer

    def test_hover_begin_change_and_all_terminal_states_are_forwarded(self):
        observer = self.observer()
        for state, expected in [(1, True), (2, True), (3, False), (4, False), (5, False)]:
            gesture = SimpleNamespace(state=state, locationInView=lambda native: SimpleNamespace(x=100., y=200.))
            observer.hover(gesture)
            script = observer.native.evaluateJavaScript.call_args.args[0]
            values = json.loads('[' + script.rsplit('(', 1)[1][:-1] + ']')
            self.assertEqual(values, [expected, 100., 200., 400., 700.])
        observer.emit(True, float('nan'), 0)
        self.assertEqual(observer.native.evaluateJavaScript.call_count, 5)

    def test_close_releases_proximity_and_recognizer_exactly_once(self):
        observer = self.observer()
        observer.close()
        observer.close()
        observer.hover(SimpleNamespace(state=1, locationInView=lambda native: SimpleNamespace(x=10., y=20.)))
        self.assertEqual(observer.native.evaluateJavaScript.call_count, 1)
        self.assertIn('(false,', observer.native.evaluateJavaScript.call_args.args[0])
        observer.native.removeGestureRecognizer.assert_called_once_with(observer.gesture)
        self.assertIsNone(observer.gesture.delegate)
        self.assertIsNone(observer.target.owner)

    def test_attach_requires_ios_ipad_and_available_hover_class(self):
        backend = type('Backend', (), {'__module__': 'toga_iOS.widgets.webview'})
        web = SimpleNamespace(_impl=backend())
        def classes(name):
            if name == 'UIDevice':
                return SimpleNamespace(currentDevice=SimpleNamespace(userInterfaceIdiom=idiom))
            if name == 'UIHoverGestureRecognizer' and available:
                return 'hover recognizer'
            raise NameError(name)
        fake = SimpleNamespace(ObjCClass=classes)
        for idiom, available, expected in [(0, True, False), (1, False, False), (1, True, True)]:
            with self.subTest(idiom=idiom, available=available), patch.dict(sys.modules, {'rubicon.objc': fake}), \
                 patch.object(ios_input, 'PencilHover') as observer:
                result = ios_input.attach(web)
                self.assertEqual(observer.called, expected)
                if expected:
                    observer.assert_called_once_with(web, 'hover recognizer')
                    self.assertIs(result, observer.return_value)
                else:
                    self.assertIsNone(result)
