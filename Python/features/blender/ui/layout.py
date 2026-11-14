"""Build Blender management widgets; operation ownership stays on the page."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.typography import point_size, setting_size
from commonUtils.ui.appearance.status_line import StatusLine

from .addon_panels import build_addon_selection, build_installed_files


def build_layout(page):
    settings_mode = page.settings_mode
    layout = qt.QVBoxLayout(page)
    layout.setContentsMargins(16, 16, 16, 16)
    title = qt.QLabel('Blender')
    font = title.font()
    font.setPointSizeF(point_size(setting_size(font) + 5.25))
    font.setBold(True)
    title.setFont(font)
    layout.addWidget(title)
    description = qt.QLabel('Your Blender configurations, ready to launch.')
    description.setWordWrap(True)
    layout.addWidget(description)
    page.stack = qt.QStackedWidget()
    layout.addWidget(page.stack, 1)
    manage_layout = _build_configuration_pages(page, settings_mode, title, description)
    controls = _build_configuration_controls(page, settings_mode, manage_layout)
    build_addon_selection(page, controls, manage_layout)
    page.add_configuration.clicked.connect(page._add_configuration)
    page.setStyleSheet("""
        QPushButton#launchCard { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }
        QPushButton#launchCard:hover { background: palette(midlight); border-color: palette(highlight); }
        QPushButton#launchCard:focus { border: 2px solid palette(highlight); }
        QLabel#launchTitle { font-size: 16px; font-weight: 600; }
        QLabel#launchDetail { color: palette(text); }
    """)
    page.status = StatusLine()
    page.status.setTextFormat(qt.Qt.TextFormat.PlainText)
    page.status.setWordWrap(True)
    layout.addWidget(page.status)
    build_installed_files(page)
    layout.addWidget(page.task)


def _build_configuration_pages(page, settings_mode, title, description):
    page.home = qt.QWidget()
    home = qt.QVBoxLayout(page.home)
    home.setContentsMargins(0, 0, 0, 0)
    toolbar = qt.QHBoxLayout()
    page.add_configuration = qt.QPushButton('Add Configuration…')
    toolbar.addWidget(page.add_configuration)
    toolbar.addStretch()
    home.addLayout(toolbar)
    scroll = qt.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(qt.QFrame.Shape.NoFrame)
    page.cards_widget = qt.QWidget()
    page.cards = qt.QVBoxLayout(page.cards_widget)
    page.cards.setContentsMargins(0, 12, 0, 0)
    scroll.setWidget(page.cards_widget)
    home.addWidget(scroll)
    page.stack.addWidget(page.home)
    page.manage = qt.QWidget()
    manage_layout = qt.QVBoxLayout(page.manage)
    manage_layout.setContentsMargins(0, 0, 0, 0)
    back = qt.QPushButton('‹ Back to configurations')
    back.clicked.connect(lambda: page.stack.setCurrentWidget(page.home))
    manage_layout.addWidget(back, 0, qt.Qt.AlignmentFlag.AlignLeft)
    back.setVisible(not settings_mode)
    page.manage_heading = qt.QLabel('Manage configuration')
    manage_layout.addWidget(page.manage_heading)
    page.preset_list = None
    if settings_mode:
        page.preset_splitter = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        selector = qt.QWidget()
        selector_layout = qt.QVBoxLayout(selector)
        selector_layout.setContentsMargins(0, 0, 8, 0)
        selector_header = qt.QHBoxLayout()
        selector_header.addWidget(qt.QLabel('Presets'), 1)
        page.add_preset_button = qt.QToolButton()
        page.add_preset_button.setText('+')
        page.add_preset_button.setAccessibleName('Add Blender preset')
        page.add_preset_button.setToolTip('Add a preset')
        page.add_preset_button.clicked.connect(page._add_configuration)
        selector_header.addWidget(page.add_preset_button)
        selector_layout.addLayout(selector_header)
        page.preset_list = qt.QListWidget()
        page.preset_list.setAccessibleName('Blender presets')
        page.preset_list.setMinimumWidth(180)
        page.preset_list.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        page.preset_list.currentItemChanged.connect(page._select_list_preset)
        page.preset_list.customContextMenuRequested.connect(page._preset_context_menu)
        selector_layout.addWidget(page.preset_list, 1)
        page.preset_splitter.addWidget(selector)
        page.preset_splitter.addWidget(page.manage)
        page.preset_splitter.setStretchFactor(0, 0)
        page.preset_splitter.setStretchFactor(1, 1)
        page.preset_splitter.setSizes([230, 750])
        page.stack.addWidget(page.preset_splitter)
        title.hide()
        description.hide()
    else:
        page.stack.addWidget(page.manage)
    return manage_layout


def _build_configuration_controls(page, settings_mode, manage_layout):
    page.controls = qt.QWidget()
    controls = qt.QVBoxLayout(page.controls)
    controls.setContentsMargins(0, 0, 0, 0)
    selection = qt.QFormLayout()
    page.version = qt.QComboBox()
    page.preset = qt.QComboBox()
    page.preset_version_label = qt.QLabel()
    if settings_mode:
        selection.addRow('Blender version', page.preset_version_label)
        page.version.setParent(page.controls)
        page.preset.setParent(page.controls)
        page.version.hide()
        page.preset.hide()
    else:
        selection.addRow('Blender version', page.version)
        selection.addRow('Preference preset', page.preset)
    controls.addLayout(selection)
    page.install_status = qt.QLabel()
    page.install_status.setWordWrap(True)
    page.install_status.setTextFormat(qt.Qt.TextFormat.PlainText)
    controls.addWidget(page.install_status)
    page.remove_button = qt.QPushButton('Remove Installation')
    page.launch_button = qt.QPushButton('Launch Blender')
    page.install_folder = qt.QPushButton('Open Installation Folder')
    page.create_button = qt.QPushButton('New Preset…')
    page.duplicate_button = qt.QPushButton('Duplicate Preset')
    page.copy_button = qt.QPushButton('Copy to Another Version')
    page.rename_button = qt.QPushButton('Rename Preset')
    page.delete_button = qt.QPushButton('Delete Preset')
    page.preset_folder = qt.QPushButton('Open Preset Folder')
    page.refresh_button = qt.QPushButton('Refresh Addons')
    page.addon_folder = qt.QPushButton('Open Addon Folder')
    primary = qt.QHBoxLayout()
    if not settings_mode:
        primary.addWidget(page.create_button)
    else:
        page.create_button.setParent(page.controls)
        page.create_button.hide()
    primary.addWidget(page.launch_button)
    page.actions = qt.QToolButton()
    page.actions.setText('More…')
    page.actions.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = qt.QMenu(page.actions)
    for button in (page.duplicate_button, page.copy_button, page.rename_button, page.delete_button,
                   page.preset_folder, page.refresh_button, page.addon_folder, page.install_folder, page.remove_button):
        action = menu.addAction(button.text())
        action.triggered.connect(button.click)
        button.hide()
        button.setParent(page.controls)
        button._menu_action = action
    page.actions.setMenu(menu)
    primary.addWidget(page.actions)
    page.add_addon = qt.QPushButton('Add Addon…')
    page.add_addon.setToolTip('Import a ZIP for this preset only; shared packages remain unchanged.')
    page.add_addon.clicked.connect(page._add_preset_addon)
    if settings_mode:
        primary.addWidget(page.add_addon)
    else:
        page.add_addon.setParent(page.controls)
        page.add_addon.hide()
    primary.addStretch()
    controls.addLayout(primary)
    manage_layout.addWidget(page.controls)
    return controls
