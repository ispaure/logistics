"""Gutter review and undoable restoration; Git staging uses the existing backend."""
from commonUtils.ui import pyside as qt
from shiboken6 import isValid


def restore_change(editor, expected, before, change):
    if editor.isReadOnly() or editor.toPlainText() != expected:
        raise ValueError('The buffer changed or became read-only. Reopen the hunk.')
    lines = expected.splitlines(keepends=True)
    start = len(''.join(lines[:change.start]).encode('utf-16-le')) // 2
    end = len(''.join(lines[:change.end]).encode('utf-16-le')) // 2
    replacement = ''.join(before.splitlines(keepends=True)[change.old_start:change.old_end])
    cursor = qt.QTextCursor(editor.document())
    cursor.beginEditBlock()
    cursor.setPosition(start)
    cursor.setPosition(end, qt.QTextCursor.MoveMode.KeepAnchor)
    cursor.insertText(replacement)
    cursor.endEditBlock()


class HunkReview(qt.QDialog):
    def __init__(self, controller, editor, change):
        super().__init__(editor.window())
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Review change')
        self.resize(760, 470)
        self.controller, self.editor, self.change = controller, editor, change
        self.snapshot = controller.snapshot()
        self.text = editor.toPlainText()
        self.before, self.label = controller.baseline
        self.revision = editor.document().revision()
        self.busy = False
        self.stage_inputs = None
        layout = qt.QVBoxLayout(self)
        title = qt.QLabel(self.label)
        title.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(title)
        self.preview = qt.QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(editor.font())
        left = ''.join(self.before.splitlines(keepends=True)[change.old_start:change.old_end])
        right = ''.join(self.text.splitlines(keepends=True)[change.start:change.end])
        self.preview.setPlainText('BASELINE\n' + (left or '(no lines)\n') + '\nCURRENT BUFFER\n' + (right or '(no lines)\n'))
        layout.addWidget(self.preview)
        self.status = qt.QLabel('Revert is undoable. IDE autosave will save the reverted buffer when enabled.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        row = qt.QHBoxLayout()
        self.revert = qt.QPushButton('Revert change in buffer')
        self.revert.setEnabled(not editor.isReadOnly())
        self.revert.clicked.connect(self.restore)
        row.addWidget(self.revert)
        self.stage = qt.QPushButton('Preview Git hunk to stage…')
        self.stage.setVisible(self.label.startswith('Git index'))
        self.stage.clicked.connect(self.stage_clicked)
        row.addWidget(self.stage)
        close = qt.QPushButton('Close')
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)

    def valid(self):
        return (isValid(self.controller) and isValid(self.editor)
                and self.controller.snapshot().path == self.snapshot.path
                and self.editor.document().revision() == self.revision
                and self.editor.toPlainText() == self.text)

    def run(self, work, done):
        if not self.valid():
            self.status.setText('The buffer changed. Close this review and reopen the hunk.')
            return
        self.busy = True
        self.revert.setEnabled(False)
        self.stage.setEnabled(False)
        def failed(error):
            if isValid(self):
                self.busy = False
                self.status.setText(str(error))
                self.stage.setEnabled(True)
                self.revert.setEnabled(isValid(self.editor) and not self.editor.isReadOnly())
        def completed(result):
            if not isValid(self):
                return
            self.busy = False
            if not self.valid():
                self.status.setText('Operation completed; the buffer changed. Reopen this review.')
                return
            try:
                done(result)
            except (OSError, ValueError, RuntimeError) as error:
                failed(error)
        self.controller.run(work, completed, failed)

    def restore(self):
        snapshot, baseline, label = self.snapshot, self.before, self.label
        def validate():
            if label.startswith('Git index'):
                from features.git.editor_baseline import index_baseline
                if index_baseline(snapshot.path, snapshot.encoding) != (baseline, label):
                    raise ValueError('The Git index changed. Reopen the hunk.')
        def apply(_):
            if not label.startswith('Git index') and self.controller.snapshot().text != baseline:
                raise ValueError('The saved baseline changed. Reopen the hunk.')
            restore_change(self.editor, self.text, baseline, self.change)
            self.close()
        self.run(validate, apply)

    def stage_clicked(self):
        if self.stage_inputs is None:
            from features.git.editor_baseline import stage_preview
            path, text, encoding, change = self.snapshot.path, self.text, self.snapshot.encoding, self.change
            def show(inputs):
                self.stage_inputs = inputs
                self.preview.setPlainText(inputs[-1])
                self.status.setText('Stage exactly the patch displayed above. Git may group nearby changes into one hunk.')
                self.stage.setText('Stage displayed Git hunk')
                self.stage.setEnabled(True)
            self.run(lambda: stage_preview(path, encoding, text, change.start, change.end), show)
        else:
            from features.git.editor_baseline import stage_reviewed
            inputs = self.stage_inputs
            self.run(lambda: stage_reviewed(inputs), lambda _: self.close())

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)
