"""Initial storage choice for a session-loaded crypt remote."""
from commonUtils.ui import pyside as qt
from features.rclone import actions


def pull_new_copy(remote, config_path):
    dialog = qt.QMessageBox(qt.QApplication.activeWindow())
    dialog.setWindowTitle('Choose local storage')
    dialog.setIcon(qt.QMessageBox.Icon.Question)
    dialog.setText('Pull downloads files from Cloud to this device. Choose local storage.')
    dialog.setInformativeText(
        'LocalCrypt (recommended) — encrypted copy: keeps encrypted names and file contents '
        'on disk. Unlock the matching credential ZIP to read it in Logistics.\n\n'
        'Local — readable copy: stores decrypted files in your Local folder. Files remain readable '
        'after credentials lock or Logistics exits.\n\n'
        'Both copies stay on this device. Next, review the destination and file changes before starting. '
        'You can cancel without downloading anything.')
    encrypted = dialog.addButton('LocalCrypt (recommended)', qt.QMessageBox.ButtonRole.AcceptRole)
    local = dialog.addButton('Regular Local copy', qt.QMessageBox.ButtonRole.ActionRole)
    dialog.addButton(qt.QMessageBox.StandardButton.Cancel)
    dialog.setDefaultButton(encrypted)
    dialog.setEscapeButton(qt.QMessageBox.StandardButton.Cancel)
    dialog.exec()
    if dialog.clickedButton() is encrypted:
        return actions.pull_encrypted_copy(remote, config_path, review=True)
    if dialog.clickedButton() is local:
        return actions.pull_remote(remote, config_path, review=True)
    return False
