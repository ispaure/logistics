"""UIKit row lifecycle checks without requiring an iOS runtime."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Separator:
    # UIKit exposes setHidden/isHidden, not a Python `hidden` field.
    __slots__ = ('_hidden', 'frame', 'backgroundColor')

    def setHidden(self, value):
        self._hidden = value

    def isHidden(self):
        return self._hidden


class IOSFileListLifecycleTests(unittest.TestCase):
    def setUp(self):
        # Run the production delegate methods; only the Objective-C bridge and
        # native cell objects are replaced for host-side lifecycle simulation.
        path = Path(__file__).parents[2] / 'Python/logisticsmobile/recycled_file_list_ios.py'
        modules = {
            'rubicon.objc': SimpleNamespace(objc_method=lambda method: method, ObjCInstance=object, ObjCBlock=Mock(),
                                          UIEdgeInsets=lambda *values: values, CGRect=lambda *values: values),
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
        self.separator = Separator()
        self.cell.contentView = Mock()
        self.cell.contentView.bounds.size = SimpleNamespace(width=320, height=48)
        self.cell.contentView.viewWithTag.return_value = self.separator
        self.table = Mock()
        self.table.dequeueReusableCellWithIdentifier.return_value = self.cell
        self.table.indexPathForCell.return_value = None
        self.index = SimpleNamespace(row=0)

    def bind(self):
        return self.controller.tableView_cellForRowAtIndexPath_(self.table, self.index)

    def test_row_dropdown_resolves_current_row_and_rejects_retired_accessory(self):
        import asyncio
        import sys
        from unittest.mock import AsyncMock
        namespace = self.controller.tableView_cellForRowAtIndexPath_.__globals__
        bind, clear = namespace['_bind_actions'], namespace['_clear_actions']
        interface = type('Interface', (), {})()
        interface._primary_action = 'Actions'
        interface._impl = SimpleNamespace(primary_action_enabled=True)
        interface.enabled = True
        row = SimpleNamespace(index=0, title='Current.md')
        interface.data = [row]
        interface.menu_provider = AsyncMock(return_value=['native action'])
        button = Mock()
        cell = SimpleNamespace(accessoryView=button)
        classes = {name: Mock() for name in ('UIMenu', 'UIDeferredMenuElement')}
        completion = Mock()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        bridge = SimpleNamespace(objc_property=Mock(), SEL=Mock(), CGRect=Mock(),
            ObjCClass=lambda name: classes[name], Block=lambda callback, *args: callback,
            objc_id=object, ns_from_py=lambda value: value)
        with patch.dict('sys.modules', {'rubicon.objc': bridge}), \
                patch.dict(namespace, {'_row_action_type': Mock(),
                    'ObjCInstance': lambda value: SimpleNamespace(copy=lambda: value),
                    'ObjCBlock': lambda value, *args: value}), \
                patch('toga.App.app', SimpleNamespace(loop=loop)):
            bind(interface, cell, row)
            self.assertTrue(button.showsMenuAsPrimaryAction)
            provider = button.menu_provider_block
            provider(completion)
            loop.run_until_complete(asyncio.sleep(0))
            interface.menu_provider.assert_awaited_once_with(row)
            completion.assert_called_once_with(['native action'])
            clear(cell)
            provider(completion)
            loop.run_until_complete(asyncio.sleep(0))
            self.assertEqual(completion.call_args.args[0], [])
            interface.menu_provider.assert_awaited_once()
            self.assertIsNone(button.menu)

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
                self.assertEqual(self.separator.isHidden(), index == count - 1)
                self.assertEqual(self.separator.frame, ((12, 47), (296, 1)))

    def test_recycled_last_row_gets_its_separator_back_when_moved_to_middle(self):
        self.bind()
        self.assertTrue(self.separator.isHidden())
        self.interface.data = [self.row] * 3
        self.index.row = 1
        self.bind()
        self.assertFalse(self.separator.isHidden())


class IOSRowImageScaleTests(unittest.TestCase):
    def test_retina_pixels_keep_a_28_point_row_image_on_reload(self):
        from logisticsmobile.recycled_file_list import thumbnail_image
        for scale in (2, 3):
            with self.subTest(scale=scale):
                backend = type('Image', (), {'__module__': 'toga_iOS.images'})()
                backend.native = Mock(size=SimpleNamespace(width=100, height=200))
                image = SimpleNamespace(_impl=backend)
                decoded = SimpleNamespace(_impl=SimpleNamespace(native=SimpleNamespace(
                    CGImage='pixels', size=SimpleNamespace(width=28 * scale, height=28 * scale))))
                renderer = Mock(format=SimpleNamespace(scale=scale))
                def render(draw):
                    draw(None)
                    return b'png'
                renderer.PNGDataWithActions.side_effect = render
                renderer_class = Mock()
                renderer_class.alloc.return_value.initWithSize.return_value = renderer
                uiimage = Mock()
                uiimage.imageWithCGImage.side_effect = lambda pixels, scale, orientation: SimpleNamespace(
                    size=SimpleNamespace(width=decoded._impl.native.size.width / scale,
                                         height=decoded._impl.native.size.height / scale))
                with patch.dict('sys.modules', {
                        'rubicon.objc': SimpleNamespace(Block=lambda draw, *args: draw, objc_id=object,
                            CGRect=lambda *values: values, ObjCClass=lambda name: uiimage),
                        'toga_iOS.libs': SimpleNamespace(UIGraphicsImageRenderer=renderer_class,
                            CGSize=lambda *values: values),
                        'toga_iOS.images': SimpleNamespace(nsdata_to_bytes=lambda data: data)}), \
                        patch('toga.Image', return_value=decoded):
                    result = thumbnail_image(image)
                self.assertEqual(result._impl.native.size.width, 28)
                self.assertEqual(result._impl.native.size.height, 28)
                backend.native.drawInRect.assert_called_once()
                origin, size = backend.native.drawInRect.call_args.args[0]
                for actual, expected in zip((*origin, *size), (7, 0, 14, 28)):
                    self.assertAlmostEqual(actual, expected)
