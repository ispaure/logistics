"""Build the Git workspace layout without owning commands or jobs."""
import sys
from commonUtils.ui import pyside as qt
from .changes import ChangesPanel
from .history import HistoryPanel
from .search import SearchPanel
from .preview import Preview
from .chrome import toolbar_button, WORKSPACE_STYLE


class RepositoryLayout:
    def _build(self):
        body = qt.QWidget(self)
        self.setCentralWidget(body)
        layout = qt.QVBoxLayout(body)
        self.setObjectName('gitWorkspace')
        self.setStyleSheet(WORKSPACE_STYLE)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar_font = qt.QFont(self.font())
        content_font = qt.QFont(toolbar_font)
        self.setFont(content_font)
        self._build_toolbar(layout, toolbar_font)
        self._build_views(layout)
        qt.QApplication.instance().paletteChanged.connect(self._refresh_action_icons)
        self._build_status(layout)
        self._style_content(content_font)
        from commonUtils.ui.appearance.styling import bind_font
        bind_font(self, 'ui')
        bind_font(self.toolbar, 'ui')

    def _refresh_action_icons(self, *args):
        from .chrome import action_icon
        for button in self.action_buttons.values():
            button.defaultAction().setIcon(action_icon(button.property('git_action_icon'),
                                                       button.property('badge_count') or 0))
        for index in range(self.refs.topLevelItemCount()):
            item = self.refs.topLevelItem(index)
            name = item.data(0, qt.Qt.ItemDataRole.UserRole + 1)
            if name:
                item.setIcon(0, action_icon(name))

    def _build_toolbar(self, layout, toolbar_font):
        self.repository_menu = qt.QMenu(self)
        for title, callback in (('Open…', self.open_dialog), ('Clone…', self.clone_dialog),
                               ('Init…', self.init_dialog), ('Manage bookmarks…', self.manage_repositories)):
            self.repository_menu.addAction(title, callback)
        self.bookmark_menu = self.repository_menu.addMenu('Bookmarks')
        self.bookmark_menu.aboutToShow.connect(self._repositories)
        self.repository_label = qt.QLabel()
        self.repository_label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.repository_label.setWordWrap(True)
        self.toolbar = qt.QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setIconSize(qt.QSize(28, 28))
        self.toolbar.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.toolbar.setObjectName('gitToolbar')
        self.toolbar.setFont(toolbar_font)
        self.action_buttons = {}
        for title, icon, callback in (
                ('Commit', 'commit', self.focus_commit), ('Pull…', 'pull', self.pull_dialog),
                ('Push…', 'push', self.push_dialog), ('Fetch', 'fetch', self.fetch),
                ('Branch…', 'branch', self.branch_dialog), ('Merge…', 'merge', self.merge_dialog),
                ('Stash…', 'stash', self.stash_dialog)):
            button = toolbar_button(title, icon, callback, self.toolbar)
            self.action_buttons[title] = button
        self.toolbar.addSeparator()
        for title, icon, callback in (
                ('View Remote', 'remote', self.view_remote), ('Show in Finder' if sys.platform == 'darwin' else 'Open Folder', 'folder', self.open_folder),
                ('Terminal', 'terminal', self.open_terminal), ('Refresh', 'fetch', self.refresh),
                ('Settings', 'settings', self.settings_dialog), ('More…', 'more', self.show_more)):
            button = toolbar_button(title, icon, callback, self.toolbar)
            self.action_buttons[title] = button
        layout.insertWidget(0, self.toolbar)
        layout.addWidget(self.repository_label)
        self.operation_bar = qt.QWidget()
        operation_layout = qt.QHBoxLayout(self.operation_bar)
        operation_layout.setContentsMargins(0, 0, 0, 0)
        self.operation_label = qt.QLabel()
        operation_layout.addWidget(self.operation_label, 1)
        for title, abort in (('Continue', False), ('Abort…', True)):
            button = qt.QPushButton(title)
            button.clicked.connect(lambda checked=False, abort=abort: self.finish_operation(abort))
            operation_layout.addWidget(button)
        self.operation_bar.hide()
        layout.addWidget(self.operation_bar)
    def _build_views(self, layout):
        self.content = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        sidebar = qt.QWidget()
        sidebar.setObjectName('gitSidebar')
        sidebar_layout = qt.QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(4, 4, 4, 4)
        sidebar_layout.setSpacing(4)
        self.refs = qt.QTreeWidget()
        self.refs.setHeaderHidden(True)
        self.refs.setMinimumWidth(156)
        self.refs.setIconSize(qt.QSize(14,14))
        self.refs.setIndentation(14)
        self.refs.setUniformRowHeights(False)
        self.refs.setAccessibleName('Git workspace navigation and references')
        self.refs.itemClicked.connect(self._navigation_selected)
        self.refs.itemDoubleClicked.connect(self._ref_activated)
        self.refs.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.refs.customContextMenuRequested.connect(self.ref_menu)
        sidebar_layout.addWidget(self.refs, 1)
        self.ref_filter = qt.QLineEdit()
        self.ref_filter.setPlaceholderText('Filter references')
        self.ref_filter.textChanged.connect(self._filter_refs)
        sidebar_layout.addWidget(self.ref_filter)
        self.content.addWidget(sidebar)
        self.views = qt.QTabWidget()
        self.views.tabBar().hide()
        self.changes = ChangesPanel()
        self.history = HistoryPanel()
        self.search_results = SearchPanel()
        self.preview = Preview()
        code_font = qt.QFont(self.preview.editor.font())
        code_font.setPointSizeF(max(9.0, code_font.pointSizeF()))
        self.preview.editor.setFont(code_font)
        self.change_split = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        self.change_split.addWidget(self.changes)
        self.change_preview_host = qt.QWidget()
        self.change_preview_layout = qt.QVBoxLayout(self.change_preview_host)
        self.change_preview_layout.setContentsMargins(0, 0, 0, 0)
        self.change_preview_layout.addWidget(self.preview)
        self.change_split.addWidget(self.change_preview_host)
        self.change_split.setSizes([350, 650])
        change_view = qt.QWidget()
        change_layout = qt.QVBoxLayout(change_view)
        change_layout.setContentsMargins(0, 0, 0, 0)
        change_layout.setSpacing(0)
        change_layout.addWidget(self.change_split, 1)
        change_layout.addWidget(self.changes.composer)
        self.views.addTab(change_view, 'File status')
        history_view = qt.QSplitter(qt.Qt.Orientation.Vertical)
        history_view.addWidget(self.history)
        self.history_bottom = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        self.history_bottom.addWidget(self.history.details)
        self.history_preview_host = qt.QWidget()
        self.history_preview_layout = qt.QVBoxLayout(self.history_preview_host)
        self.history_preview_layout.setContentsMargins(0, 0, 0, 0)
        self.history_bottom.addWidget(self.history_preview_host)
        self.history_bottom.setSizes([450, 550])
        history_view.addWidget(self.history_bottom)
        history_view.setSizes([440, 300])
        self.views.addTab(history_view, 'History')
        search_view = qt.QSplitter(qt.Qt.Orientation.Vertical)
        search_view.addWidget(self.search_results)
        search_bottom = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        search_bottom.addWidget(self.search_results.details)
        search_preview_host = qt.QWidget()
        self.search_preview_layout = qt.QVBoxLayout(search_preview_host)
        self.search_preview_layout.setContentsMargins(0, 0, 0, 0)
        search_bottom.addWidget(search_preview_host)
        search_bottom.setSizes([450, 550])
        search_view.addWidget(search_bottom)
        search_view.setSizes([440, 300])
        self.views.addTab(search_view, 'Search')
        self.content.addWidget(self.views)
        self.content.setSizes([192, 1058])
        self.content.setStretchFactor(0, 0)
        self.content.setStretchFactor(1, 1)
        layout.addWidget(self.content, 1)
        self._connect_workspace_signals()
    def _build_status(self, layout):
        status = qt.QHBoxLayout()
        self.status = qt.QLabel('Ready')
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        status.addWidget(self.status, 1)
        self.progress = qt.QProgressBar()
        self.progress.setMaximumWidth(140)
        self.progress.setRange(0, 0)
        self.progress.hide()
        status.addWidget(self.progress)
        self.cancel_button = qt.QPushButton('Cancel operation')
        self.cancel_button.clicked.connect(self.cancel)
        status.addWidget(self.cancel_button)
        self.log_toggle = qt.QToolButton()
        self.log_toggle.setText('Operation log')
        self.log_toggle.setCheckable(True)
        status.addWidget(self.log_toggle)
        layout.addLayout(status)
        self.log = qt.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setAccessibleName('Git operation log')
        self.log.setMaximumBlockCount(1500)
        self.log.setMaximumHeight(170)
        self.log.hide()
        self.log_toggle.toggled.connect(self.log.setVisible)
        layout.addWidget(self.log)
        self.more_menu = qt.QMenu(self)
        for title, callback in (('Merge branch…', self.merge_dialog), ('Cherry-pick selected commit…', self.cherry_pick),
                                ('Revert selected commit…', self.revert), ('Compare selected commit to HEAD', self.compare_to_head),
                                ('Create tag…', self.tag_dialog), ('Recover from reflog…', self.reflog_dialog),
                                ('Commit identity…', self.identity_dialog),
                                ('Add remote…', self.remote_dialog),
                                ('Worktrees…', self.repository_tools.worktrees_dialog), ('Submodules…', self.repository_tools.submodules_dialog),
                                ('Subtrees…', self.repository_tools.subtree_dialog), ('Open repository folder', self.open_folder)):
            self.more_menu.addAction(title, callback)
    def _style_content(self, content_font):
        # Widgets assembled without a parent can retain the application font when
        # reparented into splitters. Apply content sizing after the layout is built.
        for widget in self.findChildren(qt.QWidget):
            if widget is self.toolbar or self.toolbar.isAncestorOf(widget): continue
            if widget is self.preview.editor or self.preview.editor.isAncestorOf(widget): continue
            widget.setFont(content_font)
            from commonUtils.ui.appearance.styling import bind_font
            bind_font(widget, 'ui')

    def _connect_workspace_signals(self):
        self.changes.change_selected.connect(self.preview_change)
        self.changes.stage_requested.connect(self.stage_files)
        self.changes.unstage_requested.connect(lambda paths: self.stage_files(paths, True))
        self.changes.discard_requested.connect(self.discard_dialog)
        self.changes.commit_requested.connect(self.commit)
        self.changes.edit_requested.connect(self.edit_file)
        self.changes.resolve_requested.connect(self.resolve_conflict)
        self.history.commit_selected.connect(self.preview_commit)
        self.history.parent_requested.connect(self.focus_parent)
        self.history.working_copy_selected.connect(self.preview_working_copy)
        self.search_results.search_requested.connect(self.search_history)
        self.search_results.commit_selected.connect(lambda commit: self.preview_commit(commit, self.search_results))
        self.search_results.blob_selected.connect(self.preview_blob)
        self.search_results.parent_requested.connect(self._search_parent)
        self.search_results.load_more.connect(self.load_more_search)
        self.preview.ignore_whitespace.toggled.connect(self._reload_preview)
        self.history.blob_selected.connect(self.preview_blob)
        self.history.edit_requested.connect(self.edit_file)
        self.search_results.edit_requested.connect(self.edit_file)
        self.history.load_more.connect(self.load_more)
        self.views.currentChanged.connect(self._view_changed)
        self.preview.stage_button.clicked.connect(self.changes.stage_selected)
        self.preview.unstage_button.clicked.connect(self.changes.unstage_selected)
        self.preview.discard_button.clicked.connect(self.changes.discard_selected)
        self.preview.compare_button.clicked.connect(self.compare_change)
        self.preview.hunk_requested.connect(self.apply_hunk)
