"""Folder-detail UI for Calibre libraries discovered inside a Logistics folder."""

from commonUtils import ui
from commonUtils.ui import pyside
from commonUtils.ui.pyside.selection_details import SelectionDetails

from features.calibre import actions
from models.folder_entry import FolderEntry


class CalibreFolderWidget(SelectionDetails):
    """Display discovered Calibre libraries and actions for the selected library."""

    def __init__(self, entry: FolderEntry, parent=None):
        header = pyside.QLabel('Libraries')
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        super().__init__('Calibre', self._show_library, parent, list_header=header)
        libraries = actions.get_libraries(entry.local) if entry.local is not None else []
        self.set_entries(libraries, label=lambda library: library.name)

    def _show_library(self, library):
        title = pyside.QLabel(library.name)
        title.setTextFormat(pyside.Qt.TextFormat.PlainText)
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        self.details_layout.addWidget(title)

        path_label = pyside.QLabel(str(library.path))
        path_label.setTextFormat(pyside.Qt.TextFormat.PlainText)
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_layout.addWidget(path_label)

        self.add_detail_action(
            'Open Library Folder',
            lambda: actions.open_library(library),
            tooltip='Open the Calibre library directory.'
        )
        self.add_detail_action(
            'Launch Calibre',
            lambda: actions.launch_calibre(library),
            tooltip='Open this library in Calibre.'
        )
        self.add_detail_action(
            'Echo EPUBs to BOOX-SD',
            lambda: self._echo_to_boox(library),
            tooltip='Mirror EPUB files from this library to BOOX-SD.'
        )

        self.add_detail_action('Export books…', lambda: self._export(library),
                               tooltip='Review an EPUB mirror in a dedicated folder of your choice.')
        boox_help = pyside.QLabel(
            'BOOX echo mirrors EPUB files from this library to '
            '/Volumes/BOOX-SD/Calibre [EPUBs]/<library>.'
        )
        boox_help.setWordWrap(True)
        self.details_layout.addWidget(boox_help)

    def _export(self, library, destination=None):
        from .export_dialog import ExportDialog
        dialog = ExportDialog(library, destination, self)
        dialog.exec()
        dialog.deleteLater()

    def _echo_to_boox(self, library):
        from pathlib import Path
        volume = Path('/Volumes/BOOX-SD')
        if not volume.is_mount():
            ui.display_msg_box_ok('Export books', 'BOOX-SD is not mounted. Use Export books to choose another folder.')
            return
        self._export(library, volume / 'Calibre [EPUBs]' / library.name)
