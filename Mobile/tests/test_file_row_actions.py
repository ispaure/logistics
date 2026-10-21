"""Contextual row buttons never activate a file or act on replaced sources."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


class Button:
    @classmethod
    def alloc(cls):
        return cls()

    def initWithFrame(self, frame):
        self.titleLabel = NS()
        self.setTitle = Mock()
        self.setTitleColor = Mock()
        self.addTarget = Mock()
        return self


class Interface:
    pass


class FileRowActionTests(unittest.TestCase):
    def setUp(self):
        modules = {
            'rubicon.objc': NS(objc_method=lambda method: method, ObjCInstance=object,
                ObjCBlock=Mock(), Block=Mock(), objc_id=object, ns_from_py=lambda value: value,
                objc_property=lambda *args, **kw: None,
                ObjCClass=lambda name: Button if name == 'UIButton' else NS(systemFontOfSize=lambda size: size),
                SEL=lambda value: value, CGRect=lambda *args: args),
            'toga_iOS.widgets.detailedlist': NS(DetailedList=object, TogaTableViewController=object),
            'toga_iOS.libs': NS(UITableViewCell=Mock(), UITableViewCellStyleSubtitle=1, UIView=Mock()),
        }
        self.enterContext(patch.dict('sys.modules', modules))
        path = Path(__file__).parents[2] / 'Python/logisticsmobile/recycled_file_list_ios.py'
        spec = importlib.util.spec_from_file_location('logisticsmobile._row_action_test', path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.module.apple_color = lambda role: role
        self.row = NS(index=0, title='Example.md')
        self.interface = Interface()
        self.interface.__dict__.update(_primary_action='Select', _impl=NS(primary_action_enabled=True),
                                      data=[self.row], enabled=True, on_primary_action=Mock())
        self.cell = NS(accessoryView=None)
        self.module._bind_actions(self.interface, self.cell, self.row)

    def test_visible_button_selects_current_row_and_has_filename_label(self):
        button = self.cell.accessoryView
        self.assertEqual(button.accessibilityLabel, 'Select Example.md')
        button.selectRow_(button)
        self.interface.on_primary_action.assert_called_once_with(row=self.row)

    def test_source_replacement_and_disabled_table_reject_old_row_actions(self):
        button = self.cell.accessoryView
        self.interface.data = [NS(index=0, title='Replacement.md')]
        button.selectRow_(button)
        self.interface.data = [self.row]
        self.interface.enabled = False
        button.selectRow_(button)
        self.interface.on_primary_action.assert_not_called()

    def test_retired_private_cell_clears_button_reference_and_accessibility_name(self):
        button = self.cell.accessoryView
        self.module._clear_actions(self.cell)
        self.assertIsNone(button.row)
        self.assertEqual(button.accessibilityLabel, '')
        button.selectRow_(button)
        self.interface.on_primary_action.assert_not_called()

    def test_lists_without_contextual_handler_have_no_ellipsis(self):
        self.interface._impl.primary_action_enabled = False
        self.module._bind_actions(self.interface, self.cell, self.row)
        self.assertIsNone(self.cell.accessoryView)
