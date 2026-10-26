"""Native file action sheets retain full names above guarded commands."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from mobile.action_menu import BrowserActions


class BrowserActionSheetTests(unittest.TestCase):
    def setUp(self):
        self.filename = 'Report_' + 'long_name_' * 20 + 'final.pdf'
        self.browser = Mock(epoch=3, selected='file', closed=False, navigation_busy=False)
        self.browser.tree.entries = {'file': NS(label=self.filename, payload={})}
        self.callback = Mock()
        self.menu = BrowserActions(self.browser, [('Open', self.callback), ('Delete…', Mock())])

    def backend(self, name):
        self.browser.native_list.factory.DetailedList = type('DetailedList', (), {'__module__': name})

    def test_android_custom_title_wraps_full_name_above_actions(self):
        self.backend('toga_android.widgets.detailedlist')
        builder, title, context = Mock(), Mock(), Mock()
        builder.setCustomTitle.return_value = builder
        builder.setItems.return_value = builder
        builder.setNegativeButton.return_value = builder
        context.getResources().getDisplayMetrics().density = 1
        modules = {'android.app': NS(AlertDialog=NS(Builder=Mock(return_value=builder))),
                   'android.content': NS(DialogInterface=NS(OnClickListener=object)),
                   'android.widget': NS(TextView=Mock(return_value=title)),
                   'java': NS(dynamic_proxy=lambda interface: object)}
        with patch.dict('sys.modules', modules), patch('mobile.action_menu.android_menu_context', return_value=context):
            self.menu.show()
        title.setText.assert_called_once_with(self.filename)
        title.setSingleLine.assert_called_once_with(False)
        title.setTextIsSelectable.assert_called_once_with(True)
        builder.setCustomTitle.assert_called_once_with(title)
        self.assertEqual(builder.setItems.call_args.args[0], ['Open', 'Delete…'])
        self.callback.assert_not_called()
        self.menu.listener.onClick(None, 0)
        self.callback.assert_called_once_with()
        self.menu.dispose()
        builder.create.return_value.dismiss.assert_called_once_with()

    def test_ios_sheet_has_full_title_and_separate_destructive_action(self):
        self.backend('toga_iOS.widgets.detailedlist')
        alert, actions = Mock(), Mock()
        self.browser._list_rows = {}
        controller = self.browser._app.main_window._impl.native.rootViewController
        controller.presentedViewController = None
        bridge = NS(ObjCClass=lambda name: {'UIAlertController': alert, 'UIAlertAction': actions}[name],
                    Block=lambda callback, *args: callback, objc_id=object)
        with patch.dict('sys.modules', {'rubicon.objc': bridge}):
            self.menu.show()
        alert.alertControllerWithTitle.assert_called_once_with(self.filename, message=None, preferredStyle=0)
        self.assertEqual([(call.args[0], call.kwargs['style']) for call in actions.actionWithTitle.call_args_list],
                         [('Open', 0), ('Delete…', 2), ('Cancel', 1)])
        self.callback.assert_not_called()
        self.menu.blocks[0](None)
        self.callback.assert_called_once_with()
        self.menu.dispose()
        alert.alertControllerWithTitle.return_value.dismissViewControllerAnimated.assert_called_once_with(
            False, completion=None)
