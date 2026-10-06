"""Filesystem model with asynchronously supplied recursive directory sizes."""

from pathlib import Path
from commonUtils.ui import pyside as qt
from features.comics.folder_stats import format_size


class ComicFileSystemModel(qt.QFileSystemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_totals = {}

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        if index.isValid() and index.column() == 1 and self.isDir(index):
            stats = self.folder_totals.get(Path(self.filePath(index)))
            if role == qt.Qt.ItemDataRole.DisplayRole:
                if self.fileInfo(index).isSymLink():
                    return '—'
                return format_size(stats.size) if stats is not None else '…'
            if role == qt.Qt.ItemDataRole.ToolTipRole:
                return 'Recursive file size; symbolic links are excluded.'
        return super().data(index, role)

    def set_folder_totals(self, totals):
        previous = self.folder_totals
        self.folder_totals = totals or {}
        for path in previous.keys() | self.folder_totals.keys():
            index = self.index(str(path), 1)
            if index.isValid():
                self.dataChanged.emit(index, index, [qt.Qt.ItemDataRole.DisplayRole])
