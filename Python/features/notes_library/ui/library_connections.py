"""Per-document connection presentation, independent of library navigation."""
import posixpath
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress


class LibraryConnections:
    def init_connections(self):
        self.connections_progress = OperationProgress(self)
        self.connections_progress.completed.connect(self.connections_completed)
        self.connections_generation = 0
        self.connections_pending = None
        self.links_tree = qt.QTreeWidget()
        self.links_tree.setHeaderHidden(True)
        self.links_tree.setMinimumWidth(220)
        self.links_tree.itemClicked.connect(self.choose_connection)
        self.links_tree.hide()
        self.links_button = qt.QPushButton('Links')
        self.links_button.setAccessibleName('Backlinks and outgoing links')
        self.links_button.setCheckable(True)
        self.links_button.clicked.connect(self.toggle_links)
        self.viewer.navigation_toolbar.addWidget(self.links_button)

    def toggle_links(self, checked=None):
        visible = self.links_tree.isHidden() if checked is None else checked
        self.links_button.setChecked(visible)
        self.links_tree.setVisible(visible and self.document_stack.currentWidget() is self.viewer)
        if visible and self.document_stack.currentWidget() is self.viewer:
            left = self.split.sizes()[0]
            self.split.setSizes([left, max(300, self.split.width() - left - 260), 260])
            self.refresh_connections()
        else:
            self.cancel_connections()

    def cancel_connections(self):
        self.connections_generation += 1
        self.connections_pending = None
        self.connections_progress.request_cancel()

    def start_connections(self):
        if self.connections_progress.busy or self.connections_pending is None or self.closing or self.locked:
            return
        generation, work = self.connections_pending
        self.connections_pending = None
        self.connections_running = generation
        self.connections_progress.start(work, show_progress=False)

    def connections_completed(self, result, error):
        if self.closing or self.locked:
            self.close()
            return
        if self.connections_running == self.connections_generation and self.check_provider():
            self.render_connections(result, error)
        self.start_connections()

    def refresh_connections(self):
        # Hidden tabs still own their current note and may finish a read/save.
        # Use the panel preference rather than ancestor visibility to avoid
        # retaining another note's results until the next user interaction.
        if (not self.links_button.isChecked() or self.document_stack.currentWidget() is not self.viewer
                or self.library is None or self.locked):
            return
        self.cancel_connections()
        self.links_tree.clear()
        if self.storage.path is None:
            self.links_tree.addTopLevelItem(qt.QTreeWidgetItem(['Open a Markdown note to see its connections.']))
            return
        library = self.library
        path = self.storage.path.relative_to(self.provider.root.resolve()).as_posix()
        self.links_tree.addTopLevelItem(qt.QTreeWidgetItem(['Finding local connections…']))
        from features.notes_library.notes_links import connections
        self.connections_pending = (self.connections_generation,
            lambda report, cancelled: connections(library, path, cancelled=cancelled))
        self.start_connections()

    def render_connections(self, result, error):
        self.links_tree.clear()
        if error:
            self.links_tree.addTopLevelItem(qt.QTreeWidgetItem([error]))
            return
        self.links_tree.addTopLevelItem(qt.QTreeWidgetItem([
            f"{result['words']:,} words · {result['characters']:,} characters"]))
        for key, label in [('incoming', 'Backlinks'), ('outgoing', 'Outgoing links'), ('unresolved', 'Unresolved links')]:
            section = qt.QTreeWidgetItem([f'{label} ({len(result[key])})'])
            self.links_tree.addTopLevelItem(section)
            for path in result[key]:
                item = qt.QTreeWidgetItem([path if key == 'unresolved' else posixpath.relpath(path, self.library.root or '.')])
                if key != 'unresolved':
                    item.setData(0, qt.Qt.ItemDataRole.UserRole, path)
                section.addChild(item)
            section.setExpanded(True)

    def choose_connection(self, item, *args):
        path = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if path:
            self.open_note(path)

