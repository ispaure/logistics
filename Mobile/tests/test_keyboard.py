import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from logisticsmobile import keyboard


class AppleKeyboardTests(unittest.TestCase):
    def delegate(self):
        class NativeObject:
            def __init_subclass__(cls, protocols=()):
                pass

            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return self

        gesture = NS()
        def objc_class(name):
            if name == 'NSObject':
                return NativeObject
            if name == 'UITapGestureRecognizer':
                return NS(alloc=lambda: NS(initWithTarget=lambda *args, **kwargs: gesture))
            return name

        native = NS(addGestureRecognizer=Mock())
        implementation = type('Window', (), {'__module__': 'toga_iOS.window'})()
        implementation.native = native
        app = NS(main_window=NS(_impl=implementation))
        objc = NS(ObjCClass=objc_class, ObjCProtocol=lambda name: name,
                  objc_method=lambda method: method, SEL=lambda name: name)
        with patch.object(keyboard, '_apple_delegate', None), patch.dict(sys.modules, {'rubicon.objc': objc}):
            keyboard.install(app)
        self.assertFalse(gesture.cancelsTouchesInView)
        return app._keyboard_delegate

    def view(self, kind, parent=None, *, editable=True, getters=False, window=None):
        value = lambda item: (lambda: item) if getters else item
        return NS(isKindOfClass=lambda name: name == kind,
                  superview=value(parent), editable=value(editable), window=value(window))

    def test_outside_tap_handles_properties_and_getters_without_consuming_touch(self):
        delegate = self.delegate()
        for getters in (False, True):
            with self.subTest(getters=getters):
                window = NS(endEditing=Mock())
                parent = self.view('UIView', getters=getters)
                leaf = self.view('UIButton', parent, getters=getters, window=window)
                touch = NS(view=(lambda: leaf) if getters else leaf)
                self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(None, touch))
                window.endEditing.assert_called_once_with(True)

    def test_text_controls_and_web_content_keep_keyboard_and_selection(self):
        delegate = self.delegate()
        for kind, editable in (('UITextField', True), ('UITextView', True), ('WKWebView', False)):
            for getters in (False, True):
                with self.subTest(kind=kind, getters=getters):
                    window = NS(endEditing=Mock())
                    parent = self.view(kind, editable=editable, getters=getters)
                    leaf = self.view('UIView', parent, getters=getters, window=window)
                    self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(None, NS(view=leaf)))
                    window.endEditing.assert_not_called()

    def test_detached_or_missing_touch_view_is_safe(self):
        delegate = self.delegate()
        for leaf in (None, self.view('UIView')):
            self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(None, NS(view=leaf)))
