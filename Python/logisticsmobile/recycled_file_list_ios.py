"""Keep Toga's reusable UITableView cells, adding browser row semantics."""
from rubicon.objc import objc_method, ObjCInstance, ObjCBlock
from toga_iOS.widgets.detailedlist import DetailedList, TogaTableViewController
from toga_iOS.libs import UITableViewCell, UITableViewCellStyleSubtitle, UIView
from .appearance import apple_color
from .ui_metrics import TOUCH_TARGET

_row_action_type = None


def _bind_actions(interface, cell, row):
    """A visible contextual control; a normal row tap continues to open."""
    if (not getattr(interface, '_primary_action', None)
            or not getattr(getattr(interface, '_impl', None), 'primary_action_enabled', False)):
        cell.accessoryView = None
        return
    global _row_action_type
    from rubicon.objc import ObjCClass, objc_property, SEL, CGRect
    import weakref
    if _row_action_type is None:
        class FileRowAction(ObjCClass('UIButton')):
            owner = objc_property(object)
            row = objc_property(object)

            @objc_method
            def selectRow_(self, sender) -> None:
                owner, row = self.owner(), self.row
                if (owner is not None and owner.enabled and row is not None
                        and row.index < len(owner.data) and owner.data[row.index] is row):
                    owner.on_primary_action(row=row)
        _row_action_type = FileRowAction
    button = cell.accessoryView
    if button is None:
        button = _row_action_type.alloc().initWithFrame(CGRect((0, 0), (TOUCH_TARGET, TOUCH_TARGET)))
        button.setTitle('⋯', forState=0)
        button.titleLabel.font = ObjCClass('UIFont').systemFontOfSize(24)
        button.addTarget(button, action=SEL('selectRow:'), forControlEvents=1 << 6)
        cell.accessoryView = button
    button.owner, button.row = weakref.ref(interface), row
    button.accessibilityLabel = interface._primary_action + ' ' + row.title
    button.setTitleColor(apple_color('accent'), forState=0)
    button.enabled = interface.enabled
    cell.isAccessibilityElement = False


def _clear_actions(cell):
    button = getattr(cell, 'accessoryView', None)
    if button is not None:
        button.row = None
        button.accessibilityLabel = ''


def _bind_file_cell(interface, cell, index):
    from rubicon.objc import UIEdgeInsets
    row = interface.data[index]
    cell.textLabel.text = row.title
    cell.detailTextLabel.text = row.subtitle
    cell.imageView.image = row.icon._impl.native
    cell.accessoryType = 1 if row.folder else 0
    cell.textLabel.lineBreakMode = 5  # Middle truncation preserves extensions.
    cell.accessibilityLabel = row.title + ('. Folder' if row.folder else '. ' + interface.row_kind)
    cell.backgroundColor = apple_color('surface')
    # Only the outer corners belong to the group; recycled middle cells must
    # lose any corner mask left over from a previous first/last row.
    cell.layer.cornerRadius = 16
    cell.layer.maskedCorners = (3 if index == 0 else 0) | (12 if index == len(interface.data) - 1 else 0)
    cell.layer.masksToBounds = True
    # UIKit also uses the separator's leading inset to lay out cell content.
    # Keep it bounded for every row, including the last and single-row groups.
    cell.separatorInset = UIEdgeInsets(0, 56, 0, 12)
    cell.textLabel.textColor = apple_color('text')
    cell.detailTextLabel.textColor = apple_color('muted')
    _bind_actions(interface, cell, row)
    interface.row_visible(index)
    # A cached visible-row callback may have supplied its image synchronously.
    cell.imageView.image = row.icon._impl.native


class FileTableController(TogaTableViewController):
    @objc_method
    def tableView_didEndDisplayingCell_forRowAtIndexPath_(self, tableView, cell, indexPath):
        # A delayed retirement notification can arrive after UIKit has already
        # associated this reusable cell with a live row. Never erase that row.
        if tableView.indexPathForCell(cell) is not None:
            return
        cell.textLabel.text = ''
        cell.detailTextLabel.text = ''
        cell.imageView.image = None
        cell.accessibilityLabel = ''
        _clear_actions(cell)

    @objc_method
    def tableView_willDisplayCell_forRowAtIndexPath_(self, tableView, cell, indexPath):
        # Restoring the window root after unlocking can redisplay a retained
        # cell without asking cellForRowAtIndexPath to populate it again.
        _bind_file_cell(self.interface, cell, indexPath.row)

    @objc_method
    def tableView_cellForRowAtIndexPath_(self, tableView, indexPath):
        cell = tableView.dequeueReusableCellWithIdentifier('file-row')
        if cell is None:
            cell = UITableViewCell.alloc().initWithStyle(
                UITableViewCellStyleSubtitle, reuseIdentifier='file-row')
            selection = UIView.alloc().init()
            selection.backgroundColor = apple_color('hover')
            cell.selectedBackgroundView = selection
        _bind_file_cell(self.interface, cell, indexPath.row)
        return cell


class IOSFileList(DetailedList):
    def change_source(self, source):
        # UIKit queries row count when the footer is assigned. Wait until Toga
        # has published its initial data source instead of doing this in create.
        if self.native.tableFooterView is None:
            self.native.tableFooterView = UIView.alloc().init()
        super().change_source(source)

    def set_enabled(self, enabled):
        self.native.userInteractionEnabled = bool(enabled)

    def source_change(self, *, item):
        if item.index >= len(self.interface.data) or self.interface.data[item.index] is not item:
            return
        from toga_iOS.libs import NSIndexPath
        cell = self.native.cellForRowAtIndexPath(NSIndexPath.indexPathForRow(item.index, inSection=0))
        if cell is not None:
            cell.imageView.image = item.icon._impl.native
            cell.setNeedsLayout()

    def get_vertical_position(self):
        return max(0, float(self.native.contentOffset.y + self.native.adjustedContentInset.top))

    def get_max_vertical_position(self):
        self.native.layoutIfNeeded()
        return max(0, float(self.native.contentSize.height - self.native.bounds.size.height
                            + self.native.adjustedContentInset.top + self.native.adjustedContentInset.bottom))

    def set_vertical_position(self, value):
        from rubicon.objc import CGPoint
        self.native.layoutIfNeeded()
        position = min(max(0, value), self.get_max_vertical_position())
        self.native.setContentOffset(CGPoint(self.native.contentOffset.x,
            position - self.native.adjustedContentInset.top), animated=False)

    def primary_action_handler(self, index):
        row = self.interface.data[index]
        def selected(action: ObjCInstance, view: ObjCInstance, completion: ObjCInstance) -> None:
            self.interface.on_primary_action(row=row)
            ObjCBlock(completion, None, bool)(True)
        return selected

    def create(self):
        # Same Toga backend contract, with a UITableViewController subclass.
        self.native_controller = FileTableController.alloc().init()
        self.native_controller.interface = self.interface
        self.native_controller.impl = self
        self.native = self.native_controller.tableView
        # The destination container already lays out below the navigation bar.
        # A retained parent table can inherit UIKit's full bar inset during a
        # pop, briefly shifting its rows down before the live browser returns.
        self.native.contentInsetAdjustmentBehavior = 2  # Never
        self.native.delegate = self.native_controller
        self.native.rowHeight = TOUCH_TARGET
        self.native.keyboardDismissMode = 1
        from rubicon.objc import UIEdgeInsets
        self.native.backgroundColor = apple_color('transparent')
        self.native.separatorColor = apple_color('border')
        self.native.separatorInset = UIEdgeInsets(0, 56, 0, 12)
        self.primary_action_enabled = self.secondary_action_enabled = False
        self.add_constraints()

    def prepare_source_change(self):
        # Inspect visible cells before the interface replaces its source. Asking
        # UIKit for them afterward can bind old indexes against the new source.
        if self.native.window is None:
            return
        for cell in self.native.visibleCells:
            cell.textLabel.text = ''
            cell.detailTextLabel.text = ''
            cell.imageView.image = None
            cell.accessibilityLabel = ''
            _clear_actions(cell)
        selected = self.native.indexPathForSelectedRow
        if selected is not None:
            self.native.deselectRowAtIndexPath(selected, animated=False)
