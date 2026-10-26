"""Provider-backed image document with bounded, cancellable folder navigation."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from features.images.document import adjacent_image


class ImageWindow(qt.QMainWindow):
    idle = qt.Signal()

    def __init__(self, choice):
        super().__init__()
        self.choice = choice
        self.closing = False
        self.document_read_only = True
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.destroyed.connect(lambda: choice.close())
        self.resize(900, 700)
        body = qt.QWidget()
        layout = qt.QVBoxLayout(body)
        self.setCentralWidget(body)
        row = qt.QHBoxLayout()
        self.previous = qt.QPushButton('‹ Previous image')
        self.following = qt.QPushButton('Next image ›')
        self.fit = qt.QPushButton('Fit image')
        for button in (self.previous, self.following, self.fit):
            row.addWidget(button)
        layout.addLayout(row)
        self.canvas = qt.QLabel()
        self.canvas.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.scroll = qt.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll, 1)
        self.operation = OperationProgress(self)
        layout.addWidget(self.operation)
        self.operation.completed.connect(self.completed)
        self.previous.clicked.connect(lambda: self.load(-1))
        self.following.clicked.connect(lambda: self.load(1))
        self.fit.clicked.connect(self.fit_image)
        self.pixmap = qt.QPixmap()
        self.setWindowTitle(Path(choice.path).name)
        from services.documents.ui.private_views import protect_private_view
        protect_private_view(self, choice.provider)
        self.load()

    def load(self, direction=0):
        if self.closing or self.operation.busy:
            return
        provider, key = self.choice.provider, self.choice.path
        self.previous.setEnabled(False)
        self.following.setEnabled(False)
        def read(report, cancelled):
            from services.documents.storage import document_operation
            from commonUtils.runtime.streams import read_up_to
            from features.images.validation import MAX_IMAGE, image_dimensions
            with document_operation(provider, cancelled):
                rows = provider.list(key.rpartition('/')[0], cancelled=cancelled)
                target = adjacent_image(rows, key, direction) if direction else key
                if target is None:
                    return key, None, rows
                with provider.open(target) as stream:
                    data = read_up_to(stream, MAX_IMAGE + 1, cancelled=cancelled)
                image_dimensions(data)
                return target, data, rows
        self.operation.start(read, message='Opening image…')

    def completed(self, result, error):
        self.operation.hide()
        if self.closing or getattr(getattr(self, '_private_view_guard', None), 'locked', False):
            self.idle.emit()
            return
        if error:
            qt.QMessageBox.warning(self, 'Image viewer', error)
            self.previous.setEnabled(True)
            self.following.setEnabled(True)
        elif result and not self.operation.cancelled.is_set():
            key, data, rows = result
            pixmap = qt.QPixmap()
            if data is not None and not pixmap.loadFromData(data):
                qt.QMessageBox.warning(self, 'Image viewer', 'Cannot decode this image.')
                self.previous.setEnabled(True)
                self.following.setEnabled(True)
            else:
                if data is not None:
                    self.pixmap = pixmap
                    self.choice.path = key
                    self.setWindowTitle(Path(key).name)
                    self.fit_image()
                self.previous.setEnabled(adjacent_image(rows, key, -1) is not None)
                self.following.setEnabled(adjacent_image(rows, key, 1) is not None)
        self.idle.emit()

    def fit_image(self):
        if not self.pixmap.isNull():
            self.canvas.setPixmap(self.pixmap.scaled(self.scroll.viewport().size(),
                qt.Qt.AspectRatioMode.KeepAspectRatio, qt.Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'pixmap'):
            self.fit_image()

    def retire_private_content(self):
        self.operation.request_cancel()
        self.pixmap = qt.QPixmap()
        self.canvas.clear()

    def prepare_close(self):
        self.closing = True
        self.operation.request_cancel()
        return not self.operation.busy

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()
            self.operation.completed.connect(lambda *_: self.close())


def open_image_choice(choice, parent=None):
    from services.documents.ui.editors import retain
    try:
        window = ImageWindow(choice)
        return retain(window)
    except BaseException:
        choice.close()
        raise


def open_image(path, parent=None):
    from services.documents.ui.editors import local_document_choice
    return open_image_choice(local_document_choice(path), parent)


def launch(parent):
    from services.documents.ui.editors import choose_editor_resource
    from features.images.document import IMAGE_EXTENSIONS
    choice = choose_editor_resource(parent, 'open', extensions=tuple(sorted(IMAGE_EXTENSIONS)))
    return open_image_choice(choice, parent) if choice is not None else None
