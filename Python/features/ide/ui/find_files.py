"""Retained, nonmodal Find in Files with cancellable search and source preview."""
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path
from threading import Event
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.syntax import SyntaxHighlighter, detect_language
from features.ide.ui.project_search import search_files, preview_text
from features.ide.ui.usages import position_editor_popup

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='ide-find-files')


class MatchDelegate(qt.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.column() != 0:
            return super().paint(painter, option, index)
        hit = index.data(qt.Qt.ItemDataRole.UserRole)
        if hit is None:
            return super().paint(painter, option, index)
        styled = qt.QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        styled.text = ''
        style = styled.widget.style() if styled.widget else qt.QApplication.style()
        style.drawControl(qt.QStyle.ControlElement.CE_ItemViewItem, styled, painter, styled.widget)
        document = qt.QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(option.font)
        selected = bool(option.state & qt.QStyle.StateFlag.State_Selected)
        color = option.palette.color(qt.QPalette.ColorRole.HighlightedText if selected else qt.QPalette.ColorRole.Text)
        a, b = hit.excerpt_start, hit.excerpt_end
        html = (escape(hit.excerpt[:a]) + '<b style="background:#f5d780;color:#202020">'
                + escape(hit.excerpt[a:b]) + '</b>' + escape(hit.excerpt[b:]))
        document.setHtml('<span style="color:' + color.name() + ';white-space:pre">' + html + '</span>')
        painter.save()
        painter.setClipRect(option.rect)
        painter.translate(option.rect.x() + 3, option.rect.y() + (option.rect.height() - document.size().height()) / 2)
        document.drawContents(painter)
        painter.restore()


class FindFiles(qt.QFrame):
    def __init__(self, workspace):
        super().__init__(workspace, qt.Qt.WindowType.Popup)
        self.workspace = workspace
        self.setObjectName('ideFindFilesPopup')
        self.setStyleSheet('QFrame#ideFindFilesPopup { background: palette(window); border: 1px solid palette(mid); border-radius: 8px; }')
        self.setWindowTitle('Find in Files')
        self.resize(1000, 720)
        self.setMinimumSize(680, 440)
        self.search_future = self.preview_future = None
        self.search_cancel, self.preview_cancel = Event(), Event()
        self.pending_search = False
        self.pending_preview = None
        self.generation = self.preview_generation = 0
        self.closing = False
        self.jobs = []
        jobs = self.jobs
        def stop_destroyed():
            for future, cancel in jobs:
                cancel.set(); future.cancel()
        self.destroyed.connect(stop_destroyed)
        layout = qt.QVBoxLayout(self)
        top = qt.QHBoxLayout()
        title = qt.QLabel('Find in Files')
        font = title.font(); font.setBold(True); title.setFont(font)
        top.addWidget(title)
        self.summary = qt.QLabel('Enter text to search')
        top.addWidget(self.summary, 1)
        self.masks = qt.QLineEdit()
        self.masks.setPlaceholderText('*.py; *.txt (optional)')
        self.masks.setAccessibleName('File masks')
        top.addWidget(qt.QLabel('File mask:')); top.addWidget(self.masks)
        layout.addLayout(top)
        query_row = qt.QHBoxLayout()
        self.query = qt.QLineEdit()
        self.query.setPlaceholderText('Find text…')
        self.query.setClearButtonEnabled(True)
        query_row.addWidget(self.query, 1)
        self.options = {}
        for key, text, tip in [('case', 'Cc', 'Match case'), ('whole', 'W', 'Whole words'), ('regex', '.*', 'Regular expression')]:
            button = qt.QToolButton()
            button.setText(text); button.setCheckable(True)
            button.setToolTip(tip); button.setAccessibleName(tip)
            self.options[key] = button
            query_row.addWidget(button)
            button.toggled.connect(self.changed)
        layout.addLayout(query_row)
        scope_row = qt.QHBoxLayout()
        self.scope = qt.QComboBox()
        self.scope.addItems(['In Project', 'Source folders', 'Directory'])
        scope_row.addWidget(self.scope)
        self.directory = qt.QLineEdit(str(workspace.project.root))
        self.directory.setAccessibleName('Search directory')
        scope_row.addWidget(self.directory, 1)
        self.browse = qt.QPushButton('Browse…')
        self.browse.setAutoDefault(False)
        self.browse.clicked.connect(self.choose_directory)
        scope_row.addWidget(self.browse)
        layout.addLayout(scope_row)
        self.splitter = qt.QSplitter(qt.Qt.Orientation.Vertical)
        self.results = qt.QTreeWidget()
        self.results.setHeaderLabels(['Match', 'File', 'Line'])
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setItemDelegate(MatchDelegate(self.results))
        self.results.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.results.setColumnWidth(1, 280); self.results.setColumnWidth(2, 60)
        self.results.currentItemChanged.connect(self.selected)
        self.results.itemActivated.connect(self.open_selected)
        self.splitter.addWidget(self.results)
        preview_pane = qt.QWidget()
        preview_layout = qt.QVBoxLayout(preview_pane)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_title = qt.QLabel('Select a result to preview its source')
        self.preview_title.setTextFormat(qt.Qt.TextFormat.PlainText)
        preview_layout.addWidget(self.preview_title)
        self.preview = CodeEdit()
        self.preview.setReadOnly(True)
        from services.editors.ui.fonts import code_font
        code_font().bind(self.preview)
        self.highlighter = SyntaxHighlighter(self.preview, 'text')
        preview_layout.addWidget(self.preview)
        self.splitter.addWidget(preview_pane)
        self.splitter.setSizes([260, 360])
        layout.addWidget(self.splitter, 1)
        footer = qt.QHBoxLayout()
        footer.addWidget(qt.QLabel('↑↓ to select · Enter to open · Esc or click outside to close'))
        footer.addStretch()
        self.open_button = qt.QPushButton('Open selected')
        self.open_button.setAutoDefault(False)
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_selected)
        footer.addWidget(self.open_button)
        close = qt.QPushButton('Close')
        close.setAutoDefault(False); close.clicked.connect(self.close)
        footer.addWidget(close)
        layout.addLayout(footer)
        self.debounce = qt.QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.start_search)
        self.poll = qt.QTimer(self)
        self.poll.setInterval(50)
        self.poll.timeout.connect(self.completed)
        self.query.textChanged.connect(self.changed)
        self.query.returnPressed.connect(self.open_selected)
        self.query.installEventFilter(self)
        self.masks.textChanged.connect(self.changed)
        self.directory.textChanged.connect(self.changed)
        self.scope.currentIndexChanged.connect(self.scope_changed)
        self.scope_changed()

    def scope_changed(self, *args):
        directory = self.scope.currentIndex() == 2
        self.directory.setEnabled(directory); self.browse.setEnabled(directory)
        self.changed()

    def choose_directory(self):
        path = qt.QFileDialog.getExistingDirectory(self, 'Search directory', self.directory.text())
        if path:
            self.directory.setText(path)
        self.reveal()

    def reveal(self):
        self.closing = False
        origin = self.workspace.current
        origin = getattr(origin, 'editor', origin) if origin is not None else self.workspace
        position_editor_popup(self, origin, 1000, 720)
        self.show(); self.raise_(); self.activateWindow()
        self.query.setFocus(); self.query.selectAll()
        self.changed()

    def changed(self, *args):
        self.generation += 1
        self.search_cancel.set(); self.preview_cancel.set()
        self.pending_search = bool(self.query.text())
        self.pending_preview = None
        self.results.clear(); self.open_button.setEnabled(False)
        self.preview.clear(); self.preview_title.setText('Select a result to preview its source')
        self.preview.search_selections = []
        self.summary.setText('Searching…' if self.pending_search else 'Enter text to search')
        self.debounce.start(400)

    def start_search(self):
        if self.closing or not self.pending_search or self.search_future is not None:
            return
        self.pending_search = False
        project = self.workspace.project
        if self.scope.currentIndex() == 2 and not self.directory.text().strip():
            self.summary.setText('Choose a search directory.')
            return
        roots = ([project.root] if self.scope.currentIndex() == 0 else
                 project.sources() if self.scope.currentIndex() == 1 else [Path(self.directory.text()).expanduser()])
        roots = tuple(dict.fromkeys(Path(root).resolve() for root in roots))
        self.job_generation = self.generation
        self.search_cancel = Event()
        buffers = {path: doc.toPlainText() for path, doc in self.workspace.documents.items()}
        self.search_future = _executor.submit(search_files, roots, tuple(project.excluded_paths),
            self.query.text(), self.masks.text(), buffers=buffers,
            cancelled=self.search_cancel.is_set,
            **{key: button.isChecked() for key, button in self.options.items()})
        self.jobs.append((self.search_future, self.search_cancel))
        self.poll.start()

    def selected(self, item, previous=None):
        hit = item.data(0, qt.Qt.ItemDataRole.UserRole) if item else None
        self.open_button.setEnabled(hit is not None)
        self.preview_generation += 1
        self.preview_cancel.set()
        self.pending_preview = hit
        if hit:
            self.preview_title.setText(str(hit.path) + ' — loading…')
            self.start_preview()

    def start_preview(self):
        if self.closing or self.preview_future is not None or self.pending_preview is None:
            return
        self.preview_hit, self.pending_preview = self.pending_preview, None
        self.preview_job_generation = self.preview_generation
        doc = self.workspace.documents.get(self.preview_hit.path)
        self.preview_cancel = Event()
        self.preview_future = _executor.submit(preview_text, self.preview_hit.path, doc.toPlainText() if doc else None)
        self.jobs.append((self.preview_future, self.preview_cancel))
        self.poll.start()

    def completed(self):
        if self.search_future is not None and self.search_future.done():
            future, self.search_future = self.search_future, None
            self.jobs[:] = [(f, c) for f, c in self.jobs if f is not future]
            if not self.closing and self.job_generation == self.generation:
                try:
                    result = future.result()
                    self.summary.setText(f'{len(result.hits)} matches in {result.files} files' + (' · results limited' if result.limited else ''))
                    for hit in result.hits:
                        try:
                            path = str(hit.path.relative_to(self.workspace.project.root))
                        except ValueError:
                            path = str(hit.path)
                        item = qt.QTreeWidgetItem([hit.excerpt, path, str(hit.line)])
                        item.setData(0, qt.Qt.ItemDataRole.UserRole, hit)
                        item.setToolTip(1, str(hit.path))
                        self.results.addTopLevelItem(item)
                    if result.hits:
                        self.results.setCurrentItem(self.results.topLevelItem(0))
                except Exception as error:
                    self.summary.setText(str(error))
            if self.pending_search:
                self.start_search()
        if self.preview_future is not None and self.preview_future.done():
            future, self.preview_future = self.preview_future, None
            self.jobs[:] = [(f, c) for f, c in self.jobs if f is not future]
            if not self.closing and self.preview_job_generation == self.preview_generation and not self.preview_cancel.is_set():
                try:
                    text = future.result()
                    hit = self.preview_hit
                    self.preview.setPlainText(text)
                    self.highlighter.configure(detect_language(hit.path, text) if len(text) <= 250000 else 'text')
                    self.workspace.place_view(self.preview, line=hit.line, column=hit.column)
                    selection = qt.QTextEdit.ExtraSelection()
                    selection.cursor = self.preview.textCursor()
                    selection.cursor.setPosition(min(hit.start + hit.length, self.preview.document().characterCount() - 1),
                                                 qt.QTextCursor.MoveMode.KeepAnchor)
                    selection.format.setBackground(self.preview.palette().color(qt.QPalette.ColorRole.Highlight))
                    self.preview.search_selections = [selection]
                    self.preview.highlight_cursor()
                    self.preview_title.setText(str(hit.path) + f' — line {hit.line}')
                except Exception as error:
                    self.preview_title.setText(str(error))
            self.start_preview()
        if self.search_future is None and self.preview_future is None:
            self.poll.stop()
            if self.closing:
                self.workspace.idle.emit()

    def open_selected(self, *args):
        item = self.results.currentItem()
        if item is None:
            return
        hit = item.data(0, qt.Qt.ItemDataRole.UserRole)
        self.workspace.remember()
        self.workspace.navigate_to(hit.path, line=hit.line, column=hit.column)
        self.close()

    def eventFilter(self, watched, event):
        if self.isVisible() and event.type() == qt.QEvent.Type.KeyPress and event.key() == qt.Qt.Key.Key_Escape:
            self.close()
            if self.workspace.current:
                self.workspace.current.setFocus()
            return True
        if self.isVisible() and event.type() == qt.QEvent.Type.MouseButtonPress:
            if not self.rect().contains(self.mapFromGlobal(event.globalPosition().toPoint())):
                self.close()
        if event.type() == qt.QEvent.Type.ApplicationDeactivate:
            self.close()
        if watched is self.query and event.type() == qt.QEvent.Type.KeyPress and event.key() in (qt.Qt.Key.Key_Up, qt.Qt.Key.Key_Down):
            count = self.results.topLevelItemCount()
            if count:
                row = self.results.indexOfTopLevelItem(self.results.currentItem())
                row = max(0, min(count - 1, row + (1 if event.key() == qt.Qt.Key.Key_Down else -1)))
                self.results.setCurrentItem(self.results.topLevelItem(row))
            return True
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        qt.QApplication.instance().installEventFilter(self)
        super().showEvent(event)

    def hideEvent(self, event):
        qt.QApplication.instance().removeEventFilter(self)
        if not self.closing:
            self.prepare_close()
        super().hideEvent(event)

    def prepare_close(self):
        self.closing = True
        self.generation += 1; self.preview_generation += 1
        self.pending_search = False; self.pending_preview = None
        self.debounce.stop()
        for future, cancel in self.jobs:
            cancel.set(); future.cancel()
        self.hide()
        return self.search_future is None and self.preview_future is None

    def closeEvent(self, event):
        self.prepare_close()
        event.accept()
