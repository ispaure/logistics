"""Qt presentation of the shared transfer review lifecycle."""
from commonUtils.ui import pyside as qt
from features.rclone.transfers.review import ReviewScan, unchanged


class ReviewDialog(qt.QDialog):
    def __init__(self, request, scanner, valid, parent=None):
        super().__init__(parent)
        self.request, self.scanner, self.valid = request, scanner, valid
        self.scan = ReviewScan(scanner)
        self.expected = None
        self.decision = None
        self.setWindowTitle('Review ' + request.operation)
        self.resize(760, 520)
        layout = qt.QVBoxLayout(self)
        self.paths = qt.QPlainTextEdit(f'From: {request.source}\nTo: {request.destination}')
        self.paths.setReadOnly(True)
        self.paths.setMaximumHeight(80)
        layout.addWidget(self.paths)
        self.notice = qt.QLabel('Scanning; comparison does not change files.')
        layout.addWidget(self.notice)
        self.details = qt.QPlainTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details)
        row = qt.QHBoxLayout()
        self.cancel_button = qt.QPushButton('Cancel')
        self.early_button = qt.QPushButton('Proceed without full review…')
        self.proceed_button = qt.QPushButton('Confirm ' + request.operation + '…')
        self.proceed_button.setEnabled(False)
        for button in (self.cancel_button, self.early_button, self.proceed_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.cancel_button.clicked.connect(self.reject)
        self.early_button.clicked.connect(lambda: self.approve(True))
        self.proceed_button.clicked.connect(lambda: self.approve(False))
        self.timer = qt.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(100)
        self.refresh()

    def approve(self, incomplete):
        if not self.valid():
            self.notice.setText('Connection or target changed. Cancel and review again.')
            self.reject()
            return
        snapshot = self.scan.snapshot()
        if not incomplete and not snapshot.complete:
            return
        if qt.QMessageBox.question(self, 'Confirm ' + self.request.operation,
                self.request.confirmation(incomplete=incomplete),
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Yes:
            return
        if not self.valid():
            self.reject()
        elif incomplete:
            self.decision = 'proceed'
            self.scan.stop()
        else:
            self.expected = snapshot
            self.scan = ReviewScan(self.scanner)
            self.notice.setText('Checking that the completed review is still current…')
            self.proceed_button.setEnabled(False)

    def refresh(self):
        if not self.valid():
            self.decision = 'cancel'
            self.scan.stop()
            self.paths.setPlainText('Connection locked or changed.')
            self.details.clear()
        snapshot = self.scan.snapshot()
        text = snapshot.text()
        if self.valid() and text != self.details.toPlainText():
            self.details.setPlainText(text)
        self.proceed_button.setEnabled(snapshot.complete and self.expected is None and self.decision is None)
        if self.decision is not None:
            self.notice.setText('Stopping comparison…')
            if self.scan.retired.is_set() and self.isVisible():
                self.timer.stop()
                if self.decision == 'proceed' and self.valid():
                    super().accept()
                else:
                    super().reject()
        elif self.expected is not None and self.scan.retired.is_set():
            if unchanged(self.expected, snapshot) and self.valid():
                self.timer.stop()
                super().accept()
            else:
                self.expected = None
                self.notice.setText('Files changed or could not be checked. Review the current results before confirming again.')
        elif snapshot.error:
            self.notice.setText('Comparison failed. Retry later, or explicitly proceed without a full review.')
        elif snapshot.complete and self.expected is None:
            self.notice.setText('Review complete. Confirm to check for changes and start the transfer.')

    def reject(self):
        self.decision = 'cancel'
        self.scan.stop()
        self.refresh()

    def closeEvent(self, event):
        event.ignore()
        self.reject()


def confirm_review(request, scanner, valid=lambda: True, parent=None):
    if not valid():
        return False
    dialog = ReviewDialog(request, scanner, valid, parent)
    try:
        return dialog.exec() == qt.QDialog.DialogCode.Accepted
    finally:
        dialog.deleteLater()
