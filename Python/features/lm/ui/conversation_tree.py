"""Conversation-only drag routing; persistence remains owned by the page."""
from commonUtils.ui import pyside as qt


class ConversationTree(qt.QTreeWidget):
    move_requested = qt.Signal(object, str)

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(qt.QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(qt.Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        source = self.currentItem()
        target = self.itemAt(event.position().toPoint())
        if event.source() is not self or source is None:
            event.ignore()
            return
        key = source.data(0, qt.Qt.ItemDataRole.UserRole)
        folder = source.data(0, qt.Qt.ItemDataRole.UserRole + 1)
        if not key and not folder:
            event.ignore()
            return
        destination = target.data(0, qt.Qt.ItemDataRole.UserRole + 1) if target is not None else ''
        # Never let QTreeWidget move rows independently of the storage operation.
        event.ignore()
        self.move_requested.emit((key, folder), destination)
