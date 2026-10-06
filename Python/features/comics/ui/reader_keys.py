"""Reader navigation keys scoped to its window, leaving dialogs and menus alone."""

from commonUtils.ui import pyside as qt


class ReaderKeyHandler(qt.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        qt.QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        if (not isinstance(watched, qt.QWidget) or watched.window() is not self.window
                or event.type() not in (qt.QEvent.Type.ShortcutOverride, qt.QEvent.Type.KeyPress)):
            return super().eventFilter(watched, event)
        modifiers = event.modifiers() & ~qt.Qt.KeyboardModifier.KeypadModifier
        keys = (qt.Qt.Key.Key_Left, qt.Qt.Key.Key_Right, qt.Qt.Key.Key_Up, qt.Qt.Key.Key_Down,
                qt.Qt.Key.Key_Home, qt.Qt.Key.Key_End, qt.Qt.Key.Key_Escape)
        if modifiers or event.key() not in keys:
            return super().eventFilter(watched, event)
        event.accept()
        if event.type() == qt.QEvent.Type.KeyPress and not event.isAutoRepeat():
            self._navigate(event.key())
        return True

    def _navigate(self, key):
        if key in (qt.Qt.Key.Key_Left, qt.Qt.Key.Key_Right):
            direction = 1 if key == qt.Qt.Key.Key_Right else -1
            self.window.step(-direction if self.window.pages.right_to_left else direction)
        elif key in (qt.Qt.Key.Key_Up, qt.Qt.Key.Key_Down):
            self.window.step(1 if key == qt.Qt.Key.Key_Down else -1)
        elif key in (qt.Qt.Key.Key_Home, qt.Qt.Key.Key_End):
            self.window.go(0 if key == qt.Qt.Key.Key_Home else len(self.window.pages.pages) - 1)
        else:
            self.window.leave_fullscreen()
