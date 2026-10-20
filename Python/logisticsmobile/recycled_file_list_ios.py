"""Keep Toga's reusable UITableView cells, adding browser row semantics."""
from rubicon.objc import objc_method, ObjCInstance, ObjCBlock
from toga_iOS.widgets.detailedlist import DetailedList, TogaTableViewController
from toga_iOS.libs import UITableViewCell, UITableViewCellStyleSubtitle


class FileTableController(TogaTableViewController):
    @objc_method
    def tableView_didEndDisplayingCell_forRowAtIndexPath_(self, tableView, cell, indexPath):
        cell.textLabel.text = ''
        cell.detailTextLabel.text = ''
        cell.imageView.image = None
        cell.accessibilityLabel = ''

    @objc_method
    def tableView_cellForRowAtIndexPath_(self, tableView, indexPath):
        cell = tableView.dequeueReusableCellWithIdentifier('file-row')
        if cell is None:
            cell = UITableViewCell.alloc().initWithStyle(
                UITableViewCellStyleSubtitle, reuseIdentifier='file-row')
        row = self.interface.data[indexPath.row]
        cell.textLabel.text = row.title
        cell.detailTextLabel.text = row.subtitle
        cell.imageView.image = row.icon._impl.native
        cell.accessoryType = 1 if row.folder else 0
        cell.textLabel.lineBreakMode = 5  # Middle truncation preserves extensions.
        cell.accessibilityLabel = row.title + ('. Folder' if row.folder else '. ' + self.interface.row_kind)
        from .appearance import apple_color
        cell.backgroundColor = apple_color('surface')
        cell.textLabel.textColor = apple_color('text')
        cell.detailTextLabel.textColor = apple_color('muted')
        self.interface.row_visible(indexPath.row)
        # A cached visible-row callback may have supplied its image synchronously.
        cell.imageView.image = row.icon._impl.native
        return cell


class IOSFileList(DetailedList):
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
        self.native.delegate = self.native_controller
        self.native.rowHeight = 56
        self.native.keyboardDismissMode = 1
        from .appearance import apple_color
        self.native.backgroundColor = apple_color('surface')
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
        selected = self.native.indexPathForSelectedRow
        if selected is not None:
            self.native.deselectRowAtIndexPath(selected, animated=False)
