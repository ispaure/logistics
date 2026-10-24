"""Window-modal native decisions for document edits and deletion."""
import asyncio
from toga.dialogs import Dialog


class DocumentDialog(Dialog):
    def __init__(self, title, message, *, delete=False, discard_label='Quit without saving'):
        self.title, self.message = title, message
        self.choices = ([('Delete', 'delete', 2)] if delete else
                        [('Save', 'save', 0), (discard_label, 'discard', 2)])
        self.choices.append(('Cancel', 'cancel', 1))

    def _show(self, window):
        future = asyncio.get_running_loop().create_future()
        def finish(value):
            if not future.done():
                future.set_result(value)
        backend = type(window._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, Block, objc_id
            alert = ObjCClass('UIAlertController').alertControllerWithTitle(
                self.title, message=self.message, preferredStyle=1)
            self.blocks = []
            for label, value, style in self.choices:
                def selected(action, value=value):
                    finish(value)
                block = Block(selected, None, objc_id)
                self.blocks.append(block)
                action = ObjCClass('UIAlertAction').actionWithTitle(label, style=style, handler=block)
                alert.addAction(action)
                if value == 'cancel':
                    alert.preferredAction = action
            self.native = alert
            presenter = window._impl.native.rootViewController
            while presenter.presentedViewController is not None:
                presenter = presenter.presentedViewController
            presenter.presentViewController(alert, animated=True, completion=None)
        elif backend.startswith('toga_android.'):
            from android.app import AlertDialog
            from android.content import DialogInterface
            from java import dynamic_proxy
            class Click(dynamic_proxy(DialogInterface.OnClickListener)):
                def __init__(self, value):
                    super().__init__()
                    self.value = value
                def onClick(self, dialog, which):
                    finish(self.value)
            class Cancel(dynamic_proxy(DialogInterface.OnCancelListener)):
                def onCancel(self, dialog):
                    finish('cancel')
            builder = AlertDialog.Builder(window.app._impl.native)
            builder.setTitle(self.title)
            builder.setMessage(self.message)
            self.listeners = [Click(value) for _, value, _ in self.choices]
            for (label, value, _), listener in zip(self.choices, self.listeners):
                setter = (builder.setNegativeButton if value == 'cancel' else
                          builder.setNeutralButton if value == 'discard' else builder.setPositiveButton)
                setter(label, listener)
            self.cancel_listener = Cancel()
            builder.setOnCancelListener(self.cancel_listener)
            self.native = builder.create()
            self.native.show()
            from android.graphics import Color
            for which, value in ((-1, self.choices[0][1]), (-3, 'discard')):
                if value in ('delete', 'discard'):
                    button = self.native.getButton(which)
                    if button is not None:
                        button.setTextColor(Color.rgb(190, 30, 45))
        else:
            # The dummy backend supplies symbolic responses for host tests.
            from toga.platform import get_factory
            self._impl = get_factory().dialogs.QuestionDialog(title=self.title, message=self.message)
            self._impl.show(window, future)
        # Keep native blocks/listeners alive until the decision completes.
        future.add_done_callback(lambda result: self.__dict__.update(native=None))
        return future
