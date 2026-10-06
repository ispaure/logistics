"""Reader menus and visual controls; loading and navigation remain in the window."""

from commonUtils.ui import pyside as qt
from .reader_pages import PageCanvas


class ReaderControls(qt.QWidget):
    def __init__(self, fullscreen_action, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.addLayout(self._create_header(fullscreen_action))
        self.canvas = PageCanvas()
        self.canvas.setFocusPolicy(qt.Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(self._create_footer())

    def _create_header(self, fullscreen_action):
        header = qt.QHBoxLayout()
        self.previous_file_button = self._button('Previous file', qt.QStyle.StandardPixmap.SP_MediaSkipBackward)
        self.next_file_button = self._button('Next file', qt.QStyle.StandardPixmap.SP_MediaSkipForward)
        self.file_controls = qt.QHBoxLayout()
        header.addLayout(self.file_controls)
        self.title = qt.QLabel()
        self.title.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        header.addWidget(self.title, 1)
        self.direction = qt.QLabel()
        header.addWidget(self.direction)
        fullscreen = qt.QToolButton()
        fullscreen.setDefaultAction(fullscreen_action)
        header.addWidget(fullscreen)
        return header

    def _create_footer(self):
        footer = qt.QHBoxLayout()
        self.previous_button = self._button('Previous page', qt.QStyle.StandardPixmap.SP_ArrowLeft)
        self.next_button = self._button('Next page', qt.QStyle.StandardPixmap.SP_ArrowRight)
        self.page_controls = qt.QHBoxLayout()
        footer.addLayout(self.page_controls)
        self.progress = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.progress.setAccessibleName('Reading progress')
        self.progress.setLayoutDirection(qt.Qt.LayoutDirection.LeftToRight)
        footer.addWidget(self.progress, 1)
        self.progress_label = qt.QLabel()
        footer.addWidget(self.progress_label)
        return footer

    def _button(self, name, icon):
        button = qt.QToolButton()
        button.setIcon(self.style().standardIcon(icon))
        button.setIconSize(qt.QSize(22, 22))
        button.setAutoRaise(True)
        button.setToolTip(name)
        button.setAccessibleName(name)
        return button

    def set_file(self, pages):
        self.title.setText(pages.path.name)
        rtl = pages.right_to_left
        self.direction.setText('Right to left' if rtl else 'Left to right')
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
                                  qt.QStyle.StandardPixmap.SP_ArrowLeft, qt.QStyle.StandardPixmap.SP_ArrowRight)
        self._set_direction_icons(self.previous_file_button, self.next_file_button, rtl,
                                  qt.QStyle.StandardPixmap.SP_MediaSkipBackward, qt.QStyle.StandardPixmap.SP_MediaSkipForward)

    def _set_direction_icons(self, previous, following, rtl, backward_icon, forward_icon):
        previous.setIcon(self.style().standardIcon(forward_icon if rtl else backward_icon))
        following.setIcon(self.style().standardIcon(backward_icon if rtl else forward_icon))

    def show_progress(self, start, displayed, count):
        end = displayed[-1]
        with qt.QSignalBlocker(self.progress):
            self.progress.setValue(0 if start == 0 else end)
        numbers = ' & '.join(str(index + 1) for index in displayed)
        self.progress_label.setText(f'{numbers} / {count} · {(end + 1) / count:.0%}')


class ReaderMenus(qt.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._build()

    def _build(self):
        file_menu = self.window.menuBar().addMenu('File')
        open_action = file_menu.addAction('Open Comic…')
        open_action.setShortcut(qt.QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.window._choose_file)
        self.previous_file_action = file_menu.addAction('Previous File')
        self.previous_file_action.setShortcut('Ctrl+Shift+Left')
        self.previous_file_action.triggered.connect(lambda: self.window.open_adjacent(-1))
        self.next_file_action = file_menu.addAction('Next File')
        self.next_file_action.setShortcut('Ctrl+Shift+Right')
        self.next_file_action.triggered.connect(lambda: self.window.open_adjacent(1))
        self.previous_file_action.setAutoRepeat(False)
        self.next_file_action.setAutoRepeat(False)
        file_menu.addSeparator()
        close_action = file_menu.addAction('Close')
        close_action.setShortcut(qt.QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.window.close)
        edit_menu = self.window.menuBar().addMenu('Edit')
        self.edit_metadata_action = edit_menu.addAction('Edit Metadata…')
        self.edit_metadata_action.setShortcut('Ctrl+I')
        self.edit_metadata_action.triggered.connect(self.window.edit_metadata)
        view_menu = self.window.menuBar().addMenu('View')
        group = qt.QActionGroup(self)
        self.mode_actions = {}
        for mode, label in (('auto', 'Automatic Pages'), ('single', 'Single Page'), ('double', 'Two Pages')):
            action = view_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == 'auto')
            group.addAction(action)
            self.mode_actions[mode] = action
            action.triggered.connect(lambda checked=False, selected=mode: self.window.set_mode(selected))
        self.fullscreen_action = view_menu.addAction('Full Screen')
        self.fullscreen_action.setShortcut('F11')
        self.fullscreen_action.triggered.connect(self.window.toggle_fullscreen)
