"""Native document decisions use explicit destructive and cancel actions."""
import asyncio
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

from logisticsmobile.document_dialogs import DocumentDialog


class DocumentDialogTests(TestCase):
    def test_apple_save_discard_cancel_and_delete_have_native_roles(self):
        async def exercise(delete):
            impl = type('Window', (), {'__module__': 'toga_iOS.window'})()
            presenter = NS(presentedViewController=None, presentViewController=Mock())
            impl.native = NS(rootViewController=presenter)
            alert = NS(addAction=Mock())
            actions = NS(actionWithTitle=lambda title, **kwargs: NS(title=title, **kwargs))
            controller = NS(alertControllerWithTitle=Mock(return_value=alert))
            module = NS(ObjCClass=lambda name: controller if name == 'UIAlertController' else actions,
                        Block=lambda callback, *args: callback, objc_id=object)
            with patch.dict('sys.modules', {'rubicon.objc': module}):
                dialog = DocumentDialog('Title', 'Message', delete=delete)
                result = dialog._show(NS(_impl=impl))
                native_actions = [call.args[0] for call in alert.addAction.call_args_list]
                expected = [('Delete', 2), ('Cancel', 1)] if delete else [
                    ('Save', 0), ('Quit without saving', 2), ('Cancel', 1)]
                self.assertEqual([(action.title, action.style) for action in native_actions], expected)
                self.assertIs(alert.preferredAction, native_actions[-1])
                presenter.presentViewController.assert_called_once_with(alert, animated=True, completion=None)
                native_actions[0].handler(None)
                self.assertEqual(await result, 'delete' if delete else 'save')
        for delete in (False, True):
            asyncio.run(exercise(delete))

    def test_android_buttons_and_system_dismiss_have_explicit_results(self):
        async def exercise(choice):
            impl = type('Window', (), {'__module__': 'toga_android.window'})()
            builder, native = Mock(), Mock()
            builder.create.return_value = native
            modules = {
                'android.app': NS(AlertDialog=NS(Builder=Mock(return_value=builder))),
                'android.content': NS(DialogInterface=NS(OnClickListener=object, OnCancelListener=object)),
                'java': NS(dynamic_proxy=lambda interface: object),
                'android.graphics': NS(Color=NS(rgb=lambda *args: 123)),
            }
            with patch.dict('sys.modules', modules):
                dialog = DocumentDialog('Title', 'Message')
                result = dialog._show(NS(_impl=impl, app=NS(_impl=NS(native=object()))))
                self.assertEqual(builder.setPositiveButton.call_args.args[0], 'Save')
                self.assertEqual(builder.setNeutralButton.call_args.args[0], 'Quit without saving')
                self.assertEqual(builder.setNegativeButton.call_args.args[0], 'Cancel')
                if choice == 'cancel':
                    builder.setOnCancelListener.call_args.args[0].onCancel(native)
                else:
                    setter = builder.setPositiveButton if choice == 'save' else builder.setNeutralButton
                    setter.call_args.args[1].onClick(native, 0)
                self.assertEqual(await result, choice)
        for choice in ('save', 'discard', 'cancel'):
            asyncio.run(exercise(choice))
