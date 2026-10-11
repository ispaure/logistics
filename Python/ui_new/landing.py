"""Application launch choices and chrome for sidebar-free workspaces."""

from commonUtils.ui import pyside as qt
from commonUtils.ui.icons import set_painted_icon
from ui_new.sidebar import DestinationGlyph, DestinationIcon


class LaunchCard(qt.QPushButton):
    """One keyboard-accessible choice with a title, description and glyph."""

    def __init__(self, title, detail, icon, parent=None):
        super().__init__(parent)
        self.setObjectName('launchCard')
        self.setAccessibleName(title)
        self.setAccessibleDescription(detail)
        self.setMinimumHeight(88)
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)
        glyph = DestinationGlyph()
        glyph.setFixedSize(28, 28)
        set_painted_icon(glyph, DestinationIcon, icon)
        layout.addWidget(glyph)
        text = qt.QVBoxLayout()
        text.setSpacing(4)
        heading = qt.QLabel(title)
        heading.setObjectName('launchTitle')
        description = qt.QLabel(detail)
        description.setObjectName('launchDetail')
        description.setWordWrap(True)
        text.addWidget(heading)
        text.addWidget(description)
        layout.addLayout(text, 1)
        for child in self.findChildren(qt.QWidget):
            child.setAttribute(qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents)


class LandingPage(qt.QWidget):
    launch_requested = qt.Signal(str)
    document_requested = qt.Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('''
            QPushButton#launchCard, QFrame#documentCard {
                background: palette(base); border: 1px solid palette(mid);
                border-radius: 10px;
            }
            QPushButton#launchCard:hover { background: palette(midlight); border-color: palette(highlight); }
            QPushButton#launchCard:focus { border: 2px solid palette(highlight); }
            QPushButton#launchCard:pressed { background: palette(button); }
            QPushButton#launchCard:disabled { background: palette(window); }
            QLabel#launchTitle { font-weight: bold; font-size: 14px; }
            QLabel#launchDetail { color: palette(text); }
            QLabel#sectionTitle { font-weight: bold; font-size: 15px; }
            QPushButton#documentAction { padding: 5px 12px; }
        ''')
        outer = qt.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = qt.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qt.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        canvas = qt.QWidget()
        scroll.setWidget(canvas)
        centered = qt.QVBoxLayout(canvas)
        centered.setContentsMargins(36, 36, 36, 64)
        centered.addStretch()
        content = qt.QWidget()
        content.setMinimumWidth(720)
        content.setMaximumWidth(880)
        content.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Preferred)
        layout = qt.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        heading = qt.QLabel('Welcome to Logistics')
        font = heading.font()
        font.setPointSize(26)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        layout.addWidget(qt.QLabel('Choose your workspace, or open something to read or edit.'))
        self.buttons = {}
        hub = LaunchCard('Open full hub with sidebar', 'All your tools, folders and documents in one place.', 'hub')
        hub.clicked.connect(lambda: self.launch_requested.emit('hub'))
        self.buttons['hub'] = hub
        layout.addWidget(hub)
        tools = qt.QHBoxLayout()
        tools.setSpacing(12)
        for mode, title, detail, icon in (
                ('browser', 'File Browser', 'Browse and organize files', 'browser'),
                ('git', 'Git', 'Work with repositories', 'git'),
                ('ide', 'IDE', 'Explore and edit projects', 'text')):
            button = LaunchCard(title, detail, icon)
            button.clicked.connect(lambda checked=False, mode=mode: self.launch_requested.emit(mode))
            self.buttons[mode] = button
            tools.addWidget(button, 1)
        layout.addLayout(tools)
        hint = qt.QLabel('Focused workspaces open without the sidebar. The settings icon keeps your launch choices nearby.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addSpacing(8)
        title = qt.QLabel('Read & edit')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)
        self.document_grid = qt.QGridLayout()
        self.document_grid.setSpacing(12)
        layout.addLayout(self.document_grid)
        self.editor_buttons = {}
        self.editor_new_buttons = {}
        self._launcher_signature = None
        centered.addWidget(content, 0, qt.Qt.AlignmentFlag.AlignHCenter)
        centered.addStretch()

    def set_available(self, mode, available):
        button = self.buttons[mode]
        button.setEnabled(available)
        button.setToolTip('' if available else 'Enable this feature in Settings to open it.')

    def set_document_launchers(self, launchers):
        signature = tuple((key, entry.name, entry.icon, bool(entry.new_document))
                          for key, entry in launchers.items())
        if signature == self._launcher_signature:
            return
        self._launcher_signature = signature
        while self.document_grid.count():
            widget = self.document_grid.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        self.editor_buttons = {}
        self.editor_new_buttons = {}
        for index, (key, entry) in enumerate(launchers.items()):
            card = qt.QFrame()
            card.setObjectName('documentCard')
            layout = qt.QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(12)
            heading = qt.QHBoxLayout()
            glyph = DestinationGlyph()
            glyph.setFixedSize(24, 24)
            set_painted_icon(glyph, DestinationIcon, entry.icon or key)
            heading.addWidget(glyph)
            label = qt.QLabel(entry.name)
            label.setObjectName('launchTitle')
            heading.addWidget(label, 1)
            layout.addLayout(heading)
            actions = qt.QHBoxLayout()
            actions.addStretch()
            if entry.new_document:
                new = qt.QPushButton('New')
                new.setObjectName('documentAction')
                new.setAccessibleName('New ' + entry.name)
                new.clicked.connect(lambda checked=False, key=key: self.document_requested.emit(key, True))
                actions.addWidget(new)
                self.editor_new_buttons[key] = new
            button = qt.QPushButton('Open…')
            button.setObjectName('documentAction')
            button.setAccessibleName('Open ' + entry.name)
            button.clicked.connect(lambda checked=False, key=key: self.document_requested.emit(key, False))
            actions.addWidget(button)
            self.editor_buttons[key] = button
            layout.addLayout(actions)
            self.document_grid.addWidget(card, index // 3, index % 3)
        for column in range(3):
            self.document_grid.setColumnStretch(column, 1)


class LaunchSurface(qt.QWidget):
    """Keep the settings control above the central content without a layout slot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_button = qt.QToolButton(self)
        self.settings_button.setObjectName('floatingSettings')
        self.settings_button.setAccessibleName('Settings and launch navigation')
        self.settings_button.setToolTip('Settings and launch choices')
        self.settings_button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.settings_button.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.settings_button.setIconSize(qt.QSize(20, 20))
        self.settings_button.setFixedSize(36, 36)
        self.settings_button.setAutoRaise(False)
        self.settings_button.setAutoFillBackground(True)
        self.settings_button.setStyleSheet('''
            QToolButton#floatingSettings {
                background: palette(window); border: 1px solid palette(mid);
                border-radius: 6px; padding: 0px;
            }
            QToolButton#floatingSettings:hover { background: palette(button); border-color: palette(highlight); }
            QToolButton#floatingSettings:focus { border: 2px solid palette(highlight); }
            QToolButton#floatingSettings::menu-indicator { image: none; width: 0px; }
        ''')
        set_painted_icon(self.settings_button, DestinationIcon, 'settings')

    def position_settings(self):
        button = self.settings_button
        button.move(12, max(12, self.height() - button.height() - 12))
        button.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_settings()
