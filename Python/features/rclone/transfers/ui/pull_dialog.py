"""Initial storage choice for a session-loaded crypt remote."""
from commonUtils.ui import pyside as qt
from features.rclone import actions


def pull_new_copy(remote, config_path):
    dialog = qt.QMessageBox(qt.QApplication.activeWindow())
    dialog.setWindowTitle('Choose local storage')
    dialog.setIcon(qt.QMessageBox.Icon.Question)
    dialog.setText('LocalCrypt is strongly recommended for session-only credentials.')
    dialog.setInformativeText(
        'LocalCrypt keeps the existing encrypted names and file contents on disk. '
        'A regular Local copy stores decrypted files that remain readable after '
        'credentials lock or the app exits. Both copies remain on disk. '
        'You can review and cancel the transfer after choosing.')
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
