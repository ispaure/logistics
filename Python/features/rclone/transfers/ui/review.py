"""Qt presentation of the shared transfer review lifecycle."""
from commonUtils.ui import pyside as qt
from features.rclone.transfers.review import ReviewSession


class ReviewDialog(qt.QDialog):
    def __init__(self, request, scanner, valid, parent=None, *, session=None):
        super().__init__(parent)
        self.request, self.scanner, self.valid = request, scanner, valid
        self.session = session or ReviewSession(request, scanner, valid)
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
        if not self.session.can_approve(incomplete=incomplete):
            return
        if qt.QMessageBox.question(self, 'Confirm ' + self.request.operation,
                self.request.confirmation(incomplete=incomplete),
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel) == qt.QMessageBox.StandardButton.Yes:
            self.session.approve(incomplete=incomplete)
            self.refresh()

    def refresh(self):
        state = self.session.poll()
        if not self.valid():
            self.paths.setPlainText('Connection locked or changed.')
            self.details.clear()
        else:
            text = self.session.scan.snapshot().text()
            if text != self.details.toPlainText():
                self.details.setPlainText(text)
        self.proceed_button.setEnabled(self.session.can_approve())
        self.early_button.setEnabled(self.session.can_approve(incomplete=True))
        notices = dict(stopping='Stopping comparison…', checking='Checking that the completed review is still current…',
            changed='Files changed or could not be checked. Review the current results before confirming again.',
            failed='Comparison failed. Retry later, or explicitly proceed without a full review.',
            ready='Review complete. Confirm to check for changes and start the transfer.')
        if state in notices:
            self.notice.setText(notices[state])
        if state in ('approved', 'cancelled') and self.isVisible():
            self.timer.stop()
            if state == 'approved':
                super().accept()
            else:
                super().reject()

    def reject(self):
        self.session.cancel()
        self.refresh()

    def closeEvent(self, event):
        event.ignore()
        self.reject()


def confirm_review(prepared, parent=None):
    review = prepared.review
    if not review.valid():
        review.cancel()
        return None
    dialog = ReviewDialog(prepared.request, review.scanner, review.valid, parent, session=review)
    try:
        return prepared if dialog.exec() == qt.QDialog.DialogCode.Accepted else None
    finally:
        dialog.deleteLater()
