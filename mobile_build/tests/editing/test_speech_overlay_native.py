"""Native popup dismissal contracts, exercised without mobile runtimes."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, NonCallableMagicMock, patch

from mobile.speech_overlay import SpeechOverlay


class NativeSpeechOverlayTests(TestCase):
    def overlay(self):
        panel = SimpleNamespace(_impl=SimpleNamespace(), overlay_height=212,
                                refresh=MagicMock(), hide=MagicMock())
        overlay = SpeechOverlay(panel, None, None)
        panel.hide.side_effect = overlay.close
        return overlay

    def test_android_outside_dismissal_detaches_content_and_listener(self):
        overlay = self.overlay()
        container = MagicMock()
        container.scale_in.side_effect = lambda value: value
        popup_type = MagicMock()
        popup = popup_type.return_value
        context = MagicMock()
        context.getResources().getDisplayMetrics().widthPixels = 400
        owner = SimpleNamespace(_impl=SimpleNamespace(native=MagicMock()))
        owner._impl.native.getContext.return_value = context
        modules = {
            'android.graphics.drawable': SimpleNamespace(ColorDrawable=MagicMock()),
            'android.view': SimpleNamespace(Gravity=SimpleNamespace(TOP=1, END=2)),
            'android.widget': SimpleNamespace(FrameLayout=MagicMock(), PopupWindow=popup_type),
            'android.util': SimpleNamespace(TypedValue=lambda: SimpleNamespace(data=0)),
            'toga_android.container': SimpleNamespace(Container=lambda: container),
            'java': SimpleNamespace(dynamic_proxy=lambda interface: object),
        }
        with patch.dict('sys.modules', modules):
            overlay.android(owner)
        self.assertTrue(popup_type.call_args.args[-1])  # Focusable for outside/Back dismissal.
        popup.setOutsideTouchable.assert_called_once_with(True)
        listener = popup.setOnDismissListener.call_args.args[0]
        listener.onDismiss()
        overlay.panel.hide.assert_called_once()
        popup.setOnDismissListener.assert_called_with(None)
        container.clear_content.assert_called_once()
        self.assertIsNone(overlay.popup)
        self.assertIsNone(overlay.container)
        overlay.close()  # Reader teardown after native dismissal is harmless.
        popup.dismiss.assert_called_once()

    def test_ios_observes_only_outside_taps_and_removes_observer(self):
        overlay = self.overlay()

        class NSObject:
            def __init_subclass__(cls, **kwargs):
                super().__init_subclass__()

            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return self

        gesture_type = MagicMock()
        gesture = gesture_type.alloc.return_value.initWithTarget.return_value
        native = NonCallableMagicMock()
        container = SimpleNamespace(native=native, content=None)
        window = MagicMock()
        window.bounds.size.width = 400
        window.safeAreaInsets.left = window.safeAreaInsets.right = window.safeAreaInsets.top = 0
        app = SimpleNamespace(main_window=SimpleNamespace(_impl=SimpleNamespace(native=window)))
        modules = {
            'rubicon.objc': SimpleNamespace(
                ObjCClass=lambda name: NSObject if name == 'NSObject' else gesture_type if name == 'UITapGestureRecognizer' else MagicMock(),
                ObjCProtocol=lambda name: name, objc_method=lambda method: method,
                SEL=lambda name: name, CGRect=lambda origin, size: (origin, size)),
            'toga_iOS.container': SimpleNamespace(Container=lambda **kwargs: container),
        }
        with patch.dict('sys.modules', modules), patch('mobile.speech_overlay._apple_dismissal', None):
            overlay.apple(app)
            delegate = overlay.dismissal
            child = SimpleNamespace(superview=native)
            outside = SimpleNamespace(superview=None)
            self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(gesture, SimpleNamespace(view=child)))
            self.assertTrue(delegate.gestureRecognizer_shouldReceiveTouch_(gesture, SimpleNamespace(view=outside)))
            overlay.anchor = SimpleNamespace(_impl=SimpleNamespace(native=outside))
            self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(gesture, SimpleNamespace(view=outside)))
            overlay.anchor = None
            self.assertTrue(gesture.cancelsTouchesInView)
            window.addGestureRecognizer.assert_called_once_with(gesture)
            delegate.outsideTap_(gesture)
            overlay.panel.hide.assert_called_once()
            window.removeGestureRecognizer.assert_called_once_with(gesture)
            native.removeFromSuperview.assert_called_once()
            self.assertIsNone(delegate.overlay)
            self.assertIsNone(overlay.container)
            delegate.outsideTap_(gesture)  # No stale callback after teardown.
            overlay.panel.hide.assert_called_once()
