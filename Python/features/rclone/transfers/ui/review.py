"""Qt presentation of the shared transfer review lifecycle."""
from shiboken6 import isValid
from commonUtils.ui import pyside as qt
from commonUtils.ui.document_host import CloseOutcome, current_document_host
from features.rclone.transfers.review import ReviewSession
from features.rclone.transfers.presentation import ReviewProjection, PAGE_SIZE, workspace_name


def finish_setup_for_review(dialog):
    host = current_document_host(destination=ReviewDialog.document_destination)
    if host is not None and not host.closing and host.window().isVisible() and dialog.isModal():
        dialog.accept()


class ReviewDialog(qt.QDialog):
    document_destination = 'workspace-actions'

    def __init__(self, request, scanner, valid, parent=None, *, session=None):
        super().__init__(parent)
        self.request, self.scanner, self.valid = request, scanner, valid
        self.session = session or ReviewSession(request, scanner, valid)
        self.context = dict(operation='Review ' + request.operation, source=request.source,
                            destination=request.destination)
        self.setWindowTitle(self.context['operation'])
        self.resize(980, 640)
        self.projection = ReviewProjection(request)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        self.heading = qt.QLabel(workspace_name(request.source, request.destination, request.operation))
        self.heading.setTextFormat(qt.Qt.TextFormat.PlainText)
        font = self.heading.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 5)
        self.heading.setFont(font)
        layout.addWidget(self.heading)
        self.direction_toggle = qt.QToolButton()
        self.direction_toggle.setText(('Local → Cloud' if request.operation == 'Push' else 'Cloud → Local') + ' · Show full paths')
        self.direction_toggle.setCheckable(True)
        layout.addWidget(self.direction_toggle)
        endpoints = qt.QGroupBox('Transfer direction')
        endpoint_layout = qt.QFormLayout(endpoints)
        self.path_labels = []
        for title, path in (('Source', request.source), ('Destination', request.destination)):
            label = qt.QLabel(path)
            label.setWordWrap(True)
            label.setTextFormat(qt.Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
            endpoint_layout.addRow(title, label)
            self.path_labels.append(label)
        layout.addWidget(endpoints)
        endpoints.hide()
        self.direction_toggle.toggled.connect(endpoints.setVisible)
        self.notice = qt.QLabel('Comparing files… No files have changed.')
        self.notice.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.summary = qt.QLabel()
        layout.addWidget(self.summary)
        filters = qt.QHBoxLayout()
        self.filter = qt.QComboBox()
        for label, kind in (('All changes', 'all'), ('Add', 'add'), ('Update', 'replace'),
                            ('Delete', 'delete'), ('Local cleanup', 'cleanup')):
            self.filter.addItem(label, kind)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Find a file or folder…')
        filters.addWidget(self.filter)
        filters.addWidget(self.search)
        layout.addLayout(filters)
        self.details = qt.QTreeWidget()
        self.details.setHeaderLabels(['Change', 'File', 'Folder'])
        self.details.setRootIsDecorated(False)
        self.details.setAlternatingRowColors(True)
        self.details.setSelectionMode(qt.QAbstractItemView.SelectionMode.SingleSelection)
        self.details.header().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.Stretch)
        self.details.setColumnWidth(0, 120)
        self.details.setColumnWidth(2, 180)
        self.details.setUniformRowHeights(True)
        split = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        split.addWidget(self.details)
        inspector = qt.QWidget()
        inspector_layout = qt.QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(20, 8, 0, 8)
        self.inspector_labels = {}
        for name in ('action', 'name', 'path', 'effect', 'source', 'destination'):
            label = qt.QLabel('')
            label.setWordWrap(True)
            label.setTextFormat(qt.Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
            inspector_layout.addWidget(label)
            self.inspector_labels[name] = label
        inspector_layout.addStretch()
        inspector.setMinimumWidth(210)
        split.addWidget(inspector)
        split.setSizes([650, 250])
        layout.addWidget(split, 1)
        self.details.currentItemChanged.connect(self.inspect_file)
        paging = qt.QHBoxLayout()
        self.previous = qt.QPushButton('Previous')
        self.next = qt.QPushButton('Next')
        self.position = qt.QLabel('')
        self.pager = qt.QWidget()
        pager_layout = qt.QHBoxLayout(self.pager)
        pager_layout.setContentsMargins(0, 0, 0, 0)
        pager_layout.addWidget(self.previous)
        pager_layout.addWidget(self.position, 1)
        pager_layout.addWidget(self.next)
        paging.addWidget(self.pager)
        layout.addLayout(paging)
        self.previous.clicked.connect(lambda: self.change_page(-1))
        self.next.clicked.connect(lambda: self.change_page(1))
        self.empty = qt.QLabel()
        layout.addWidget(self.empty)
        self.warning = qt.QLabel('Destination files may be replaced or deleted. No backup or undo.')
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)
        self._rendered = None
        self.filter.currentIndexChanged.connect(self.reset_filter)
        qt.connect_search(self.search, self.reset_filter)
        row = qt.QHBoxLayout()
        self.cancel_button = qt.QPushButton('Cancel')
        self.early_button = qt.QPushButton('Skip preview and start ' + request.operation)
        self.proceed_button = qt.QPushButton('Confirm ' + request.operation + '…')
        self.proceed_button.setEnabled(False)
        self.proceed_button.setDefault(True)
        row.addWidget(self.cancel_button)
        row.addStretch()
        row.addWidget(self.early_button)
        row.addWidget(self.proceed_button)
        layout.addLayout(row)
        self.cancel_button.clicked.connect(self.reject)
        self.early_button.clicked.connect(lambda: self.approve(True))
        self.proceed_button.clicked.connect(lambda: self.approve(False))
        self.timer = qt.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(100)
        self.refresh()

    def reset_filter(self):
        self.projection.select(kind=self.filter.currentData(), query=self.search.text())
        self.refresh()

    def change_page(self, step):
        self.projection.select(step=step)
        self.refresh()

    def inspect_file(self, item=None, previous=None):
        for label in self.inspector_labels.values():
            label.clear()
        if item is None:
            return
        action, path = item.data(0, qt.Qt.ItemDataRole.UserRole)
        labels = self.inspector_labels
        labels['action'].setText(dict(add='Add', replace='Update', delete='Delete', cleanup='Local cleanup')[action])
        labels['name'].setText(path.rstrip('/').rsplit('/', 1)[-1])
        labels['path'].setText(path)
        labels['effect'].setText(dict(add='Add this entry to the destination.',
            replace='Replace the destination entry with the source version.',
            delete='Delete this entry from the destination.',
            cleanup='Remove this local generated entry before Push.')[action])
        labels['source'].setText('Source: ' + self.request.source)
        labels['destination'].setText('Local cleanup: ' + self.request.source if action == 'cleanup'
                                      else 'Destination: ' + self.request.destination)

    def approve(self, incomplete):
        if not self.valid():
            self.notice.setText('Connection or target changed. Cancel and review again.')
            self.reject()
            return
        if not self.session.can_approve(incomplete=incomplete):
            return
        if incomplete or qt.QMessageBox.question(self, 'Confirm ' + self.request.operation,
                self.request.confirmation(),
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel) == qt.QMessageBox.StandardButton.Yes:
            self.session.approve(incomplete=incomplete)
            self.refresh()

    def refresh(self):
        state = self.session.poll()
        snapshot = self.session.scan.snapshot()
        if not self.valid():
            self.heading.setText('Transfer review')
            self.warning.clear()
            self.position.clear()
            self.pager.hide()
            self.proceed_button.setText('Confirm ' + self.request.operation)
            for label in self.path_labels:
                label.setText('Connection locked or changed.')
            self.details.clear()
            self.summary.clear()
            self.search.clear()
            self.empty.clear()
            self._rendered = None
            self.inspect_file()
            self.projection.clear()
        else:
            signature = (snapshot, self.projection.kind, self.projection.query, self.projection.page)
            if signature != self._rendered:
                self._rendered = signature
                counts = snapshot.counts
                self.summary.setText('   •   '.join(f'{counts[kind]:,} {label}' for kind, label in
                    (('add', 'Add'), ('replace', 'Update'), ('delete', 'Delete'), ('cleanup', 'Local cleanup'))))
                model = self.projection.model(snapshot, state=state, can_confirm=False, can_early=False)
                rows = model['rows']
                selected = self.details.currentItem()
                selected_path = selected.data(0, qt.Qt.ItemDataRole.UserRole) if selected is not None else None
                self.details.clear()
                chosen = None
                labels = dict(add='+ Add', replace='↻ Update', delete='− Delete', cleanup='− Local cleanup')
                for action, path in rows:
                    folder, _, name = path.rstrip('/').rpartition('/')
                    filename = (name or path) + ('/' if path.endswith('/') else '')
                    item = qt.QTreeWidgetItem([labels[action], filename, folder or '—'])
                    item.setData(0, qt.Qt.ItemDataRole.UserRole, (action, path))
                    item.setIcon(1, self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon if path.endswith('/') else qt.QStyle.StandardPixmap.SP_FileIcon))
                    item.setSizeHint(0, qt.QSize(0, 40))
                    if selected_path == (action, path):
                        chosen = item
                    for column in range(3):
                        item.setToolTip(column, path)
                    self.details.addTopLevelItem(item)
                if chosen is None and self.details.topLevelItemCount():
                    chosen = self.details.topLevelItem(0)
                self.details.setCurrentItem(chosen)
                self.pager.setVisible(model['total'] > PAGE_SIZE)
                self.previous.setEnabled(model['page'] > 0)
                self.next.setEnabled((model['page'] + 1) * PAGE_SIZE < model['total'])
                self.position.setText(f"{model['page'] * PAGE_SIZE + 1:,}–{min((model['page'] + 1) * PAGE_SIZE, model['total']):,} / {model['total']:,}")
                self.proceed_button.setText(self.request.operation + f" {sum(counts.values()):,} changes…")
                risk = (f"{counts['delete']:,} destination deletions · No backup or undo" if snapshot.complete
                        else 'Skipping may replace or delete destination files before you can review them.')
                if not snapshot.complete and self.request.operation == 'Push':
                    risk += ' LocalCrypt Push also skips the full integrity scan and generated-file cleanup.'
                elif counts['cleanup']:
                    risk += f" · {counts['cleanup']:,} local generated entries removed before Push"
                self.warning.setText(risk)
                self.empty.setText('' if rows else ('No matching changes.' if self.search.text() or self.filter.currentData() != 'all'
                    else 'No changes needed.' if snapshot.complete else 'Looking for changes…'))
            if snapshot.error:
                self.notice.setText('Comparison failed: ' + snapshot.error)
        self.proceed_button.setEnabled(snapshot.complete and self.session.can_approve())
        self.early_button.setEnabled(self.session.can_approve(incomplete=True))
        self.early_button.setVisible(not snapshot.complete)
        notices = dict(stopping='Stopping comparison…', checking='Checking that the completed review is still current…',
            changed='Files changed or could not be checked. Review the current results before confirming again.',
            failed='Comparison failed: ' + snapshot.error,
            ready='Review complete. Confirm to check for changes and start the transfer.')
        if state in notices:
            self.notice.setText(notices[state])
        if state in ('approved', 'cancelled') and not self.isHidden():
            self.timer.stop()
            if state == 'approved':
                super().accept()
            else:
                super().reject()

    def reject(self):
        self.session.cancel()
        self.refresh()

    def request_close(self):
        self.reject()
        return CloseOutcome.ACCEPTED if self.session.scan.retired.is_set() else CloseOutcome.PENDING

    def closeEvent(self, event):
        event.ignore()
        self.reject()


def confirm_review(prepared, parent=None):
    review = prepared.review
    if not review.valid():
        review.cancel()
        return None
    dialog = ReviewDialog(prepared.request, review.scanner, review.valid, parent, session=review)
    try:
        host = current_document_host(dialog)
        if host is not None and host.closing:
            review.cancel()
            return None
        if host is None or not host.window().isVisible() or qt.QApplication.activeModalWidget():
            return prepared if dialog.exec() == qt.QDialog.DialogCode.Accepted else None

        # Keep the existing synchronous handoff for callers which launch a
        # series of transfers. The hosted review itself is a non-modal tab.
        loop = qt.QEventLoop()
        dialog.finished.connect(loop.exit)
        dialog.destroyed.connect(loop.quit)
        host.present(dialog)
        dialog.refresh()
        result = loop.exec() if dialog.timer.isActive() else dialog.result()
        return prepared if result == qt.QDialog.DialogCode.Accepted and isValid(host) and not host.closing else None
    finally:
        if isValid(dialog):
            dialog.deleteLater()
