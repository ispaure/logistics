"""Message composition, bounded screenshot paste/drop and sampling controls."""
from commonUtils.ui import pyside as qt
from ..screenshots import read_clipboard_image_file, MAX_IMAGES


class SamplingSpin(qt.QDoubleSpinBox):
    """Treat server default as a choice adjacent to zero, not a negative range."""
    def stepBy(self, steps):
        if self.value() < 0 and steps > 0:
            self.setValue(0)
        elif self.value() == 0 and steps < 0:
            self.setValue(-1)
        else:
            self.setValue(max(0, self.value() + steps * self.singleStep()) if self.value() >= 0 else -1)

    def valueFromText(self, text):
        value = super().valueFromText(text)
        return -1 if value < 0 else value



class Composer(qt.QPlainTextEdit):
    send_requested = qt.Signal()
    image_pasted = qt.Signal(object)
    image_paste_failed = qt.Signal(str)

    def keyPressEvent(self, event):
        if event.key() in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter):
            # Let an input method finish composing before treating Return as Send.
            if event.modifiers() == qt.Qt.KeyboardModifier.NoModifier and not self.composing:
                event.accept()
                self.send_requested.emit()
                return
        super().keyPressEvent(event)

    def canInsertFromMimeData(self, source):
        return source.hasImage() or any(url.isLocalFile() for url in source.urls()) or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        paths = [url.toLocalFile() for url in source.urls() if url.isLocalFile()]
        if paths:
            try:
                if len(paths) > MAX_IMAGES:
                    raise ValueError('Paste at most four image files at once.')
                # Decode the entire selection before accepting any attachment.
                images = [read_clipboard_image_file(path) for path in paths]
            except (ValueError, OSError) as error:
                self.image_paste_failed.emit(str(error))
                return
            for image in images:
                self.image_pasted.emit(image)
            return
        if source.hasImage():
            image = source.imageData()
            if isinstance(image, qt.QPixmap):
                image = image.toImage()
            if isinstance(image, qt.QImage):
                self.image_pasted.emit(image)
                return
        super().insertFromMimeData(source)

    @staticmethod
    def image_source(source):
        return source.hasImage() or any(url.isLocalFile() for url in source.urls())

    @staticmethod
    def accept_image_drop(event):
        event.setDropAction(qt.Qt.DropAction.CopyAction)
        event.accept()

    def dragEnterEvent(self, event):
        if self.image_source(event.mimeData()):
            Composer.accept_image_drop(event)
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self.image_source(event.mimeData()):
            Composer.accept_image_drop(event)
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if self.image_source(event.mimeData()):
            self.insertFromMimeData(event.mimeData())
            Composer.accept_image_drop(event)
        else:
            super().dropEvent(event)

    def inputMethodEvent(self, event):
        self.composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    composing = False

