"""Personal push filter editor; exclusions never authorize local deletion."""
from commonUtils.ui import pyside as qt
from features.rclone.push_policy import load_excludes, save_excludes, DEFAULT_EXCLUDES


class PushSettings(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        note = qt.QLabel('Push exclusions: one rclone pattern per line. These skip transfers, never delete matching local files. '
                        'LocalCrypt checks every file before applying filters. Raw or encrypted .DS_Store, Thumbs.db, '
                        'ehthumbs.db and ehthumbs_vista.db files are automatically removed before a real push. '
                        'Patterns match stored names; LocalCrypt transfers use encrypted names.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.patterns = qt.QPlainTextEdit()
        layout.addWidget(self.patterns)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        try:
            self.patterns.setPlainText('\n'.join(load_excludes()))
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
        save = qt.QPushButton('Save push exclusions')
        reset = qt.QPushButton('Restore defaults')
        save.clicked.connect(self.save)
        reset.clicked.connect(lambda: self.patterns.setPlainText('\n'.join(DEFAULT_EXCLUDES)))
        layout.addWidget(save)
        layout.addWidget(reset)

    def save(self):
        try:
            save_excludes(self.patterns.toPlainText().splitlines())
            self.status.setText('Push exclusions saved.')
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
