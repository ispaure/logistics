"""Destination and confirmation prompts captured before starting archive jobs."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.archives import ARCHIVE_SUFFIXES


def extraction_destination(parent, archive_path):
    archive_path = Path(archive_path)
    base = qt.QFileDialog.getExistingDirectory(parent, 'Choose parent folder for extraction', str(archive_path.parent))
    if not base:
        return None
    title = archive_path.name
    for suffix in sorted(ARCHIVE_SUFFIXES, key=len, reverse=True):
        if title.lower().endswith(suffix):
            title = title[:-len(suffix)]
            break
    name, accepted = qt.QInputDialog.getText(parent, 'Extract archive',
        'New destination folder name (existing folders are kept):',
        qt.QLineEdit.EchoMode.Normal, title + '-extracted')
    if not accepted:
        return None
    name = name.strip()
    if not name or name in ('.', '..') or '/' in name or '\\' in name or ':' in name:
        raise ValueError('Enter a single, nonempty folder name.')
    return Path(base) / name


def confirm_removal(parent, archive_path, selected):
    question = qt.QMessageBox(parent)
    question.setWindowTitle('Remove archive entries')
    question.setTextFormat(qt.Qt.TextFormat.PlainText)
    question.setText(f'Remove {len(selected)} selected entries from {Path(archive_path).name}?')
    question.setInformativeText('Selected folders include all their contents. The ZIP is rebuilt and verified before saving.')
    question.setDetailedText('\n'.join(selected))
    question.setStandardButtons(qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel)
    question.setDefaultButton(qt.QMessageBox.StandardButton.Cancel)
    return question.exec() == qt.QMessageBox.StandardButton.Yes
