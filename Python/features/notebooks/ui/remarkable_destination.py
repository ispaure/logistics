"""Native save selection for an exact, revision-approved RMDOC destination."""
from pathlib import Path

from commonUtils.ui import pyside as qt
from services.documents.storage import local_document_export_revision


def choose_destination(parent, suggested):
    # Configure the suffix before native overwrite confirmation. macOS ignores
    # DontConfirmOverwrite; keep confirmation with the native picker everywhere.
    picker = qt.QFileDialog(parent, 'Save retrieved notebook', str(suggested),
                            'reMarkable notebook (*.rmdoc)')
    picker.setAcceptMode(qt.QFileDialog.AcceptMode.AcceptSave)
    picker.setFileMode(qt.QFileDialog.FileMode.AnyFile)
    picker.setDefaultSuffix('rmdoc')
    captured = []

    def selected(value):
        try:
            path = Path(value).absolute()
            if path.suffix.lower() != '.rmdoc':
                raise ValueError('Choose a filename ending in .rmdoc. The selected destination was not changed.')
            captured[:] = [(path, local_document_export_revision(path))]
        except (OSError, ValueError) as error:
            captured[:] = [error]

    picker.fileSelected.connect(selected)
    try:
        if picker.exec() != qt.QDialog.DialogCode.Accepted:
            return None
        if not captured:
            values = picker.selectedFiles()
            if not values:
                return None
            selected(values[0])
        if isinstance(captured[0], Exception):
            raise captured[0]
        return captured[0]
    finally:
        picker.deleteLater()
