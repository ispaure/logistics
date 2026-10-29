"""Reader history settings, independent of the selected feature or credentials."""

from commonUtils.ui import pyside as qt


class ReaderHistoryPanel(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        label = qt.QLabel(
            "Clear saved positions and recent files independently, across all readers and sources. "
            "Credentials need not be unlocked. Document files are kept."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        for positions, title in (
            (True, "Clear all saved positions…"),
            (False, "Clear all recent files…"),
        ):
            button = qt.QPushButton(title)
            button.clicked.connect(lambda checked=False, p=positions: self.clear(p))
            layout.addWidget(button)
        migrate_button = qt.QPushButton("Migrate protected reader history…")
        migrate_button.clicked.connect(self.migrate)
        layout.addWidget(migrate_button)
        layout.addStretch()

    def clear(self, positions):
        title = "Clear all saved positions?" if positions else "Clear all recent files?"
        detail = (
            "Open readers will not save their old position again until reopened. "
            "Document files and recent history are kept."
            if positions
            else "Document files and saved positions are kept."
        )
        if (
            qt.QMessageBox.question(self, title, detail)
            != qt.QMessageBox.StandardButton.Yes
        ):
            return
        from commonUtils.filesystem.storage import cache_directory
        from services.documents.history_controls import (
            clear_saved_positions,
            clear_recent_files,
        )

        try:
            (clear_saved_positions if positions else clear_recent_files)(
                cache_directory(create=False)
            )
        except (OSError, ValueError) as error:
            qt.QMessageBox.warning(
                self, "Could not finish clearing history", str(error)
            )

    def migrate(self):
        password, accepted = qt.QInputDialog.getText(
            self,
            "Previous credential ZIP password",
            "Unlock the updated ZIP first. Enter its previous password to migrate protected history. Unreadable records are preserved.",
            qt.QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return
        from commonUtils.filesystem.storage import cache_directory
        from services.documents.state_migration import migrate

        try:
            result = migrate(cache_directory(create=False), password)
            qt.QMessageBox.information(
                self,
                "Reader history migration",
                f"Migrated {result['migrated']} records; preserved {result['preserved']}. Reopen affected readers to restore positions.",
            )
        except (OSError, ValueError) as error:
            qt.QMessageBox.warning(self, "History was preserved", str(error))
        finally:
            password = None

    def can_close(self):
        return True
