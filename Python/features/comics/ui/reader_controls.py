"""Reader menus and visual controls; loading and navigation remain in the window."""
from commonUtils.ui.icons import set_painted_icon

from commonUtils.ui import pyside as qt
from .reader_pages import PageCanvas
from commonUtils.ui.reader_menus import ReaderMenus as SharedReaderMenus
from commonUtils.ui.reader_chrome import ReaderLabel, ReaderFullscreen, ReaderIcon, reader_button, READER_MARGINS, READER_SPACING


class ReaderControls(qt.QWidget):
    def __init__(self, fullscreen_action, parent=None, *, menus=None):
        super().__init__(parent)
        self.menus = menus
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(*READER_MARGINS)
        layout.setSpacing(READER_SPACING)
        layout.addLayout(self._create_header(fullscreen_action))
        self.canvas = PageCanvas()
        self.canvas.setFocusPolicy(qt.Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(self._create_footer())

    def _create_header(self, fullscreen_action):
        header = qt.QHBoxLayout()
        self.workspace_controls = header
        header.setSpacing(READER_SPACING)
        if self.menus is not None:
            self.open_button = reader_button(self, 'Open comic', action=self.menus.shared.open_action)
            self.open_button.hide()  # File > Open already exposes the same action.
        self.previous_file_button = self._button('Previous file', 'previous-file')
        self.next_file_button = self._button('Next file', 'next-file')
        self.file_controls = qt.QHBoxLayout()
        header.addLayout(self.file_controls)
        self.title = ReaderLabel()
        self.title.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.title, 1)
        self.direction = qt.QLabel()
        self.direction.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
        header.addWidget(self.direction)
        if self.menus is not None:
            self.layout_button = reader_button(self, 'Page layout', icon='layout')
            self.layout_button.setMenu(self.menus.layout_menu)
            self.layout_button.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
            header.addWidget(self.layout_button)
        self.fullscreen_button = reader_button(self, 'Full screen', action=fullscreen_action, icon='fullscreen')
        header.addWidget(self.fullscreen_button)
        return header

    def _create_footer(self):
        footer = qt.QHBoxLayout()
        footer.setSpacing(READER_SPACING)
        self.previous_button = self._button('Previous page', 'previous')
        self.next_button = self._button('Next page', 'next')
        self.page_controls = qt.QHBoxLayout()
        footer.addLayout(self.page_controls)
        self.progress = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.progress.setAccessibleName('Reading progress')
        self.progress.setToolTip('Jump to a page · Ctrl+G opens Go to page')
        self.progress.setLayoutDirection(qt.Qt.LayoutDirection.LeftToRight)
        footer.addWidget(self.progress, 1)
        self.progress_label = qt.QLabel()
        self.progress_label.setAccessibleName('Reading progress')
        footer.addWidget(self.progress_label)
        return footer

    def _button(self, name, icon):
        return reader_button(self, name, icon=icon)

    def set_file(self, pages):
        self.title.setText(pages.path.name)
        rtl = pages.right_to_left
        self.direction.setText('Right to left' if rtl else 'Left to right')
        self.direction.setVisible(rtl)
        with qt.QSignalBlocker(self.progress):
            self.progress.setInvertedAppearance(rtl)
            self.progress.setRange(0, max(1, len(pages.pages) - 1))
            self.progress.setEnabled(len(pages.pages) > 1)
        for layout, previous, following in ((self.page_controls, self.previous_button, self.next_button),
                                            (self.file_controls, self.previous_file_button, self.next_file_button)):
            while layout.count():
                layout.takeAt(0)
            layout.addWidget(following if rtl else previous)
            layout.addWidget(previous if rtl else following)
        self._set_direction_icons(self.previous_button, self.next_button, rtl,
                                  'previous', 'next')
        self._set_direction_icons(self.previous_file_button, self.next_file_button, rtl,
                                  'previous-file', 'next-file')

    def _set_direction_icons(self, previous, following, rtl, backward_icon, forward_icon):
        set_painted_icon(previous, ReaderIcon, forward_icon if rtl else backward_icon)
        set_painted_icon(following, ReaderIcon, backward_icon if rtl else forward_icon)

    def show_progress(self, start, displayed, count):
        end = displayed[-1]
        with qt.QSignalBlocker(self.progress):
            self.progress.setValue(0 if start == 0 else end)
        numbers = ' & '.join(str(index + 1) for index in displayed)
        self.progress_label.setText(f'Page {numbers} / {count} · {(end + 1) / count:.0%}')


class ReaderMenus(qt.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._build()

    def _build(self):
        from commonUtils.ui.document_host import close_document
        self.shared = SharedReaderMenus(self, self.window.menuBar(),
            open_file=self.window._choose_file, edit_metadata=self.window.edit_metadata,
            close=lambda: close_document(self.window), fullscreen=self.window.toggle_fullscreen,
            open_path=lambda path: self.window._request_file(path, False),
            open_label='Open comic…', suffixes=('.cbz',))
        self.fullscreen = ReaderFullscreen(self.window, self.shared.fullscreen_action)
        self.previous_file_action = self.shared.action(self.shared.navigate, 'Previous file',
            lambda: self.window.open_adjacent(-1), 'Ctrl+Shift+Left')
        self.next_file_action = self.shared.action(self.shared.navigate, 'Next file',
            lambda: self.window.open_adjacent(1), 'Ctrl+Shift+Right')
        self.previous_page_action = self.shared.action(self.shared.navigate, 'Previous page', lambda: self.window.step(-1))
        self.next_page_action = self.shared.action(self.shared.navigate, 'Next page', lambda: self.window.step(1))
        self.go_page_action = self.shared.action(self.shared.navigate, 'Go to page…', self.window.go_to_page, 'Ctrl+G')
        self.edit_metadata_action = self.shared.metadata_action
        self.fullscreen_action = self.shared.fullscreen_action
        self.layout_menu = self.shared.view.addMenu('Page layout')
        view_menu = self.layout_menu
        group = qt.QActionGroup(self)
        self.mode_actions = {}
        for mode, label in (('auto', 'Automatic'), ('single', 'Single page'), ('double', 'Two pages')):
            action = view_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == 'auto')
            action.setToolTip({'auto': 'Fit one or two pages according to the window and page shapes.',
                              'single': 'Display one page at a time.',
                              'double': 'Display facing pages together when possible.'}[mode])
            group.addAction(action)
            self.mode_actions[mode] = action
            action.triggered.connect(lambda checked=False, selected=mode: self.window.set_mode(selected))
