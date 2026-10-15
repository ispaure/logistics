"""Native new-document format prompt, with a host-test fallback."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

CHOICES = (('Plain text (.txt)', 'txt'), ('Markdown (.md)', 'md'))


def choose_document_type(app):
    backend = type(app._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass, Block, objc_id
        alert = ObjCClass('UIAlertController').alertControllerWithTitle(
            'New document', message='Choose a file type', preferredStyle=1)
        blocks = []
        for title, extension in CHOICES:
            def choose(action, selected=extension):
                if app.active_host:
                    app.create_chosen_document(selected)
            block = Block(choose, None, objc_id)
            blocks.append(block)
            alert.addAction(ObjCClass('UIAlertAction').actionWithTitle(title, style=0, handler=block))
        alert.addAction(ObjCClass('UIAlertAction').actionWithTitle('Cancel', style=1, handler=None))
        # Keep Python callbacks alive for the lifetime of the native prompt.
        app.document_type_prompt = (alert, blocks)
        controller = app.main_window._impl.native.rootViewController
        while controller.presentedViewController:
            controller = controller.presentedViewController
        controller.presentViewController(alert, animated=True, completion=None)
    elif backend.startswith('toga_android.'):
        from android.app import AlertDialog
        from android.content import DialogInterface
        from java import dynamic_proxy
        class Listener(dynamic_proxy(DialogInterface.OnClickListener)):
            def onClick(self, dialog, index):
                if app.active_host:
                    app.create_chosen_document(CHOICES[index][1])
        listener = Listener()
        dialog = (AlertDialog.Builder(app._impl.native).setTitle('New document')
                  .setItems([title for title, extension in CHOICES], listener)
                  .setNegativeButton('Cancel', None).create())
        app.document_type_prompt = (dialog, listener)
        dialog.show()
    else:
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Choose a file type'))
        for title, extension in CHOICES:
            box.add(toga.Button(title, on_press=lambda widget, selected=extension, **kw:
                app.create_chosen_document(selected), style=Pack(height=44)))
        box.add(toga.Button('Cancel', on_press=lambda widget, **kw: app.routes.back(), style=Pack(height=44)))
        app.show_view(box, destination='documents', route='new-document', title='New document')
