"""Desktop history rows, selection and drag routing."""
from commonUtils.ui import pyside as qt


CONVERSATION_ROLE = qt.Qt.ItemDataRole.UserRole
FOLDER_ROLE = CONVERSATION_ROLE + 1


class ConversationTree(qt.QTreeWidget):
    move_requested = qt.Signal(object, str)

    def __init__(self):
        super().__init__()
        self.folder_items = {}
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(qt.QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(qt.Qt.DropAction.MoveAction)

    def rebuild(self, records, folders, *, mode, searching, current, reveal_current):
        """Project the inventory without dispatching an open request."""
        selected = self.currentItem()
        selected_folder = (selected.data(0, FOLDER_ROLE)
                           if selected is not None and not self.conversation_key(selected) else None)
        expanded = {path: item.isExpanded() for path, item in self.folder_items.items()}
        records = [record for record in records if record.get('mode', 'chat') == mode]
        visible_folders = set() if searching else set(folders)
        for record in records:
            path = record['folder']
            while path:
                visible_folders.add(path)
                path = path.rpartition('/')[0]

        with qt.QSignalBlocker(self):
            self.clear()
            root = qt.QTreeWidgetItem(self, ['Conversations'])
            root.setData(0, FOLDER_ROLE, '')
            self.folder_items = {'': root}
            for path in sorted(visible_folders, key=lambda name: (name.count('/'), name.casefold())):
                parent, _, label = path.rpartition('/')
                item = qt.QTreeWidgetItem(self.folder_items[parent], [label])
                item.setData(0, FOLDER_ROLE, path)
                item.setIcon(0, self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon))
                self.folder_items[path] = item

            for record in records:
                folder = record['folder']
                item = qt.QTreeWidgetItem(self.folder_items[folder], [self.conversation_label(record)])
                item.setData(0, CONVERSATION_ROLE, record['id'])
                item.setData(0, FOLDER_ROLE, folder)
                if record['id'] == current:
                    self.setCurrentItem(item)

            if selected_folder is not None and not reveal_current:
                self.select_folder(selected_folder)
            for path, item in self.folder_items.items():
                item.setExpanded(searching or expanded.get(path, True))
            selected = self.currentItem()
            if reveal_current and selected is not None:
                parent = selected.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()

    def clear_inventory(self):
        with qt.QSignalBlocker(self):
            self.clear()
            self.folder_items = {}

    def items(self):
        iterator = qt.QTreeWidgetItemIterator(self)
        while iterator.value() is not None:
            yield iterator.value()
            iterator += 1

    @staticmethod
    def conversation_key(item):
        return item.data(0, CONVERSATION_ROLE) if item is not None else None

    def first_conversation(self):
        return next((item for item in self.items() if self.conversation_key(item)), None)

    def selected_conversation(self):
        return self.conversation_key(self.currentItem())

    def selected_folder(self):
        item = self.currentItem()
        return item.data(0, FOLDER_ROLE) if item is not None else ''

    def select_folder(self, path):
        item = self.folder_items.get(path)
        if item is not None:
            self.setCurrentItem(item)

    @staticmethod
    def conversation_label(record):
        return ('★ ' if record.get('pinned') else '') + record['title']

    def update_conversation_label(self, record):
        for item in self.items():
            if self.conversation_key(item) == record['id']:
                item.setText(0, self.conversation_label(record))
                return

    def dropEvent(self, event):
        source = self.currentItem()
        target = self.itemAt(event.position().toPoint())
        if event.source() is not self or source is None:
            event.ignore()
            return
        key = self.conversation_key(source)
        folder = source.data(0, FOLDER_ROLE)
        if not key and not folder:
            event.ignore()
            return
        destination = target.data(0, FOLDER_ROLE) if target is not None else ''
        # Never let QTreeWidget move rows independently of the storage operation.
        event.ignore()
        self.move_requested.emit((key, folder), destination)
