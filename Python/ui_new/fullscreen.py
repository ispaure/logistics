"""Keep the host's fullscreen command reachable from every tool and reader."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.readers.reader_chrome import ReaderFullscreen


class WindowFullscreen(qt.QObject):
    def __init__(self, window, menu):
        super().__init__(window)
        self.window = window
        self.action = menu.addAction('Full screen')
        self.action.setCheckable(True)
        self.action.setShortcut(qt.QKeySequence('F11'))
        self.action.setShortcutContext(qt.Qt.ShortcutContext.WindowShortcut)
        window.addAction(self.action)
        self.state = ReaderFullscreen(window, self.action)
        self.action.triggered.connect(self.state.toggle)
        qt.QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        # Reader actions also bind F11. Accept ShortcutOverride before Qt's
        # shortcut map sees them, then handle the key once at the window level.
        if (event.type() in (qt.QEvent.Type.ShortcutOverride, qt.QEvent.Type.KeyPress)
                and isinstance(watched, qt.QWidget) and watched.window() is self.window
                and event.key() == qt.Qt.Key.Key_F11
                and event.modifiers() == qt.Qt.KeyboardModifier.NoModifier):
            event.accept()
            if event.type() == qt.QEvent.Type.KeyPress and not event.isAutoRepeat():
                self.state.toggle()
            return True
        return False
