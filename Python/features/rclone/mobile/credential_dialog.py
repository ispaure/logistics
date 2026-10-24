"""Window-modal, explicit session/persistent choice before credential publication."""
import asyncio
from toga.dialogs import Dialog
from features.rclone.credential_storage import (
    SESSION_TITLE, SESSION_DESCRIPTION, PERSISTENT_TITLE, PERSISTENT_DESCRIPTION,
    SAVED_COPY_NOTE, SHARED_NOTE,
)


class CredentialStorageDialog(Dialog):
    def __init__(self, package, *, saved=False, content_factory=None):
        self.package, self.saved = package, saved
        self.content_factory = content_factory
        self.title = 'Unlock credential ZIP'
        self.message = (f'How should Logistics keep credentials from {package}?\n\n'
                        f'{SESSION_TITLE}\n{SESSION_DESCRIPTION}\n\n'
                        f'{PERSISTENT_TITLE}\n{PERSISTENT_DESCRIPTION}\n'
                        'Saved credentials use device-protected encrypted storage.\n\n'
                        + (SAVED_COPY_NOTE + '\n\n' if saved else '') + SHARED_NOTE)

    def _show(self, window):
        future = asyncio.get_running_loop().create_future()
        def finish(value):
            if not future.done():
                future.set_result(value)
        backend = type(window._impl).__module__
        if self.content_factory is not None:
            self.content = self.content_factory(self.package, self.saved, finish)
            self.content.app = window.app
            self.content.window = window
        if backend.startswith('toga_iOS.'):
            from toga_iOS.container import ControlledContainer
            def layout(container):
                insets = container.native.safeAreaInsets
                container.top_inset, container.bottom_inset = insets.top, insets.bottom
                size = (container.width, container.height)
                if size != getattr(self, '_size', None):
                    self._size = size
                    self.content.reflow(container.width)
                    self.content.refresh()
            self.container = ControlledContainer(on_refresh=lambda container: None,
                                                 on_native_layout=layout)
            self.container.content = self.content._impl
            self.native = self.container.controller
            # Full-screen containment prevents a swipe dismissal from leaving
            # the awaiting credential operation unresolved. Cancel stays visible.
            self.native.modalPresentationStyle = 0
            presenter = window._impl.native.rootViewController
            while presenter.presentedViewController is not None:
                presenter = presenter.presentedViewController
            presenter.presentViewController(self.native, animated=True, completion=None)
        elif backend.startswith('toga_android.'):
            from android.app import Dialog as AndroidDialog
            from android.content import DialogInterface
            from android.view import View, Window
            from android.widget import FrameLayout
            from java import dynamic_proxy
            from toga_android.container import Container
            owner = self
            class Layout(dynamic_proxy(View.OnLayoutChangeListener)):
                def onLayoutChange(self, view, left, top, right, bottom, *old):
                    width, height = right - left, bottom - top
                    owner.content.reflow(owner.container.scale_out(width))
                    owner.container.resize_content(width, height)
            class Cancel(dynamic_proxy(DialogInterface.OnCancelListener)):
                def onCancel(self, dialog):
                    finish(None)
            context = window.app._impl.native
            self.native = AndroidDialog(context)
            self.native.requestWindowFeature(Window.FEATURE_NO_TITLE)
            frame = FrameLayout(context)
            self.container = Container()
            self.container.init_container(frame)
            self.container.set_content(self.content._impl)
            self.layout_listener, self.cancel_listener = Layout(), Cancel()
            frame.addOnLayoutChangeListener(self.layout_listener)
            self.native.setContentView(frame)
            self.native.setOnCancelListener(self.cancel_listener)
            self.native.show()
            metrics = context.getResources().getDisplayMetrics()
            self.native.getWindow().setLayout(
                min(int(metrics.widthPixels * .94), self.container.scale_in(560)),
                int(metrics.heightPixels * .85))
        else:
            from toga.platform import get_factory
            self._impl = get_factory().dialogs.QuestionDialog(title=self.title, message=self.message)
            self._impl.show(window, future)
        def cleanup(result):
            if getattr(self, 'native', None) is not None:
                if backend.startswith('toga_iOS.'):
                    self.native.dismissViewControllerAnimated(True, completion=None)
                    self.container.content = None
                else:
                    self.native.dismiss()
                    self.container.clear_content()
                self.native = None
        future.add_done_callback(cleanup)
        return future
