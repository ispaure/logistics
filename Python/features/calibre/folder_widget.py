"""Folder-detail UI for Calibre libraries discovered inside a Logistics folder."""

from commonUtils import ui
from commonUtils.ui import pyside

from features.calibre import actions
from models.folder_entry import FolderEntry


class CalibreFolderWidget(pyside.QGroupBox):
    """Display discovered Calibre libraries and actions for the selected library."""

    def __init__(self, entry: FolderEntry, parent=None):
        super().__init__('Calibre', parent)

        self.libraries = actions.get_libraries(entry.local) if entry.local is not None else []

        self.library_list = pyside.QListWidget()
        self.library_list.setMinimumWidth(150)
        self.library_list.setMaximumWidth(240)

        self.details_widget = pyside.QWidget()
        self.details_layout = pyside.QVBoxLayout(self.details_widget)
        self.details_layout.setContentsMargins(0, 0, 0, 0)
        self.details_layout.setSpacing(8)

        self._build_layout()

        self.library_list.currentRowChanged.connect(self._library_changed)
        self._populate_libraries()

    def _build_layout(self):
        layout = pyside.QHBoxLayout(self)
        layout.setSpacing(12)

        library_panel = pyside.QWidget()
        library_panel_layout = pyside.QVBoxLayout(library_panel)
        library_panel_layout.setContentsMargins(0, 0, 0, 0)
        library_panel_layout.setSpacing(6)

        library_label = pyside.QLabel('Libraries')
        label_font = library_label.font()
        label_font.setBold(True)
        library_label.setFont(label_font)

        library_panel_layout.addWidget(library_label)
        library_panel_layout.addWidget(self.library_list, 1)

        layout.addWidget(library_panel)
        layout.addWidget(self.details_widget, 1)

    def _populate_libraries(self):
        self.library_list.clear()
        self._clear_details()

        for library in self.libraries:
            self.library_list.addItem(library.name)

        if self.libraries:
            self.library_list.setCurrentRow(0)

    def _library_changed(self, row: int):
        self._clear_details()

        if row < 0 or row >= len(self.libraries):
            return

        self._show_library(self.libraries[row])

    def _clear_details(self):
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

    def _show_library(self, library):
        title = pyside.QLabel(library.name)
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        self.details_layout.addWidget(title)

        path_label = pyside.QLabel(str(library.path))
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_layout.addWidget(path_label)

        self._add_action_button(
            'Open Library Folder',
            lambda: actions.open_library(library),
            True,
            'Open the Calibre library directory.'
        )
        self._add_action_button(
            'Launch Calibre',
            lambda: actions.launch_calibre(library),
            True,
            'Open this library in Calibre.'
        )
        self._add_action_button(
            'Echo EPUBs to BOOX-SD',
            lambda: self._echo_to_boox(library),
            True,
            'Mirror EPUB files from this library to BOOX-SD.'
        )

        boox_help = pyside.QLabel(
            'BOOX echo mirrors EPUB files from this library to '
            '/Volumes/BOOX-SD/Calibre [EPUBs]/<library>.'
        )
        boox_help.setWordWrap(True)
        self.details_layout.addWidget(boox_help)

        self.details_layout.addStretch()

    def _echo_to_boox(self, library):
        confirmed = ui.display_msg_box_ok_cancel(
            'Echo EPUBs to BOOX-SD',
            f'Echo EPUB files from "{library.name}" to BOOX-SD?\n\n'
            'The destination is treated as a mirror. Files that no longer exist '
            'in the Calibre library may be removed from the destination.'
        )

        if confirmed:
            actions.echo_epubs_to_boox_sd(library)

    def _add_action_button(self, name, callback, enabled: bool, tooltip: str):
        button = pyside.QPushButton(name)
        button.setEnabled(enabled)
        button.setToolTip(tooltip)
        button.clicked.connect(lambda _checked=False, callback=callback: callback())
        self.details_layout.addWidget(button)
