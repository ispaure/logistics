"""UIKit row lifecycle checks without requiring an iOS runtime."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class IOSFileListLifecycleTests(unittest.TestCase):
    def setUp(self):
        # Run the production delegate methods; only the Objective-C bridge and
        # native cell objects are replaced for host-side lifecycle simulation.
        path = Path(__file__).parents[2] / 'Python/logisticsmobile/recycled_file_list_ios.py'
        modules = {
            'rubicon.objc': SimpleNamespace(objc_method=lambda method: method, ObjCInstance=object, ObjCBlock=Mock(),
                                          UIEdgeInsets=lambda *values: values),
            'toga_iOS.widgets.detailedlist': SimpleNamespace(DetailedList=object, TogaTableViewController=object),
            'toga_iOS.libs': SimpleNamespace(UITableViewCell=Mock(), UITableViewCellStyleSubtitle=1, UIView=Mock()),
        }
        spec = importlib.util.spec_from_file_location('logisticsmobile._ios_list_lifecycle_test', path)
        module = importlib.util.module_from_spec(spec)
        bridge = patch.dict('sys.modules', modules)
        bridge.start()
        self.addCleanup(bridge.stop)
        spec.loader.exec_module(module)
        module.apple_color = lambda role: role
        self.controller = module.FileTableController()
        self.icon = object()
        self.row = SimpleNamespace(title='Documents', subtitle='Folder details', folder=True,
                                   icon=SimpleNamespace(_impl=SimpleNamespace(native=self.icon)))
        self.interface = self.controller.interface = SimpleNamespace(
            data=[self.row], row_kind='File', row_visible=Mock())
        self.cell = SimpleNamespace(textLabel=SimpleNamespace(text=''), detailTextLabel=SimpleNamespace(text=''),
                                    imageView=SimpleNamespace(image=None), accessibilityLabel='', layer=SimpleNamespace())
        self.table = Mock()
        self.table.dequeueReusableCellWithIdentifier.return_value = self.cell
        self.table.indexPathForCell.return_value = None
        self.index = SimpleNamespace(row=0)

    def bind(self):
        return self.controller.tableView_cellForRowAtIndexPath_(self.table, self.index)

    def test_detached_cell_is_rebound_on_display_without_new_cell_request(self):
        self.bind()
        self.controller.tableView_didEndDisplayingCell_forRowAtIndexPath_(self.table, self.cell, self.index)
        self.assertEqual(self.cell.textLabel.text, '')
        self.assertIsNone(self.cell.imageView.image)
        # UIKit can retain the cell when the lock screen replaces the window
        # root, then display it again without cellForRowAtIndexPath.
        self.controller.tableView_willDisplayCell_forRowAtIndexPath_(self.table, self.cell, self.index)
        self.assertEqual(self.cell.textLabel.text, 'Documents')
        self.assertEqual(self.cell.detailTextLabel.text, 'Folder details')
        self.assertIs(self.cell.imageView.image, self.icon)
        self.assertEqual(self.cell.accessibilityLabel, 'Documents. Folder')
        self.assertEqual(self.cell.accessoryType, 1)
        self.table.dequeueReusableCellWithIdentifier.assert_called_once()
        self.table.reloadData.assert_not_called()

    def test_late_retirement_does_not_blank_a_cell_already_associated_with_a_row(self):
        self.bind()
        self.table.indexPathForCell.return_value = self.index
        self.controller.tableView_didEndDisplayingCell_forRowAtIndexPath_(self.table, self.cell, self.index)
        self.assertEqual(self.cell.textLabel.text, 'Documents')
        self.assertIs(self.cell.imageView.image, self.icon)
        self.assertEqual(self.cell.accessibilityLabel, 'Documents. Folder')

    def test_display_rebinds_current_source_and_cached_thumbnail(self):
        self.bind()
        new_icon = object()
        current = SimpleNamespace(title='New.md', subtitle='', folder=False, icon=self.row.icon)
        self.interface.data = [current]
        self.interface.row_visible.side_effect = lambda index: setattr(
            current, 'icon', SimpleNamespace(_impl=SimpleNamespace(native=new_icon)))
        self.controller.tableView_willDisplayCell_forRowAtIndexPath_(self.table, self.cell, self.index)
        self.assertEqual(self.cell.textLabel.text, 'New.md')
        self.assertEqual(self.cell.detailTextLabel.text, '')
        self.assertEqual(self.cell.accessoryType, 0)
        self.assertEqual(self.cell.accessibilityLabel, 'New.md. File')
        self.assertIs(self.cell.imageView.image, new_icon)
        self.assertEqual(self.cell.backgroundColor, 'surface')

    def test_reused_cells_keep_only_the_groups_outer_corners(self):
        self.interface.data = [self.row] * 3
        for index, corners in ((0, 3), (2, 12), (1, 0)):
            self.index.row = index
            self.bind()
            self.assertEqual(self.cell.layer.maskedCorners, corners)
            self.assertEqual(self.cell.layer.cornerRadius, 16)
        self.interface.data = [self.row]
        self.index.row = 0
        self.bind()
        self.assertEqual(self.cell.layer.maskedCorners, 15)

    def test_last_and_single_rows_keep_the_same_content_insets_as_other_rows(self):
        # UITableViewCell uses the leading separator inset for content layout;
        # a huge inset to hide the final separator pushes its title offscreen.
        for count in (3, 1):
            self.interface.data = [self.row] * count
            for index in reversed(range(count)):
                self.index.row = index
                self.bind()
                self.assertEqual(self.cell.separatorInset, (0, 56, 0, 12))
                self.assertEqual(self.cell.textLabel.text, 'Documents')
