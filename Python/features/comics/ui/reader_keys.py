"""Window-scoped navigation with a steady hold cadence independent of OS repeats."""

from commonUtils.ui import pyside as qt
from commonUtils.settings import get_wheel_navigation_settings
from commonUtils.ui.page_wheel import PageWheel

PAGE_TURN_INTERVAL_MS = 225


class ReaderKeyHandler(qt.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.held_key = None
        self.direction = None
        self.wheel = PageWheel()
        self.timer = qt.QTimer(self)
        self.timer.setInterval(PAGE_TURN_INTERVAL_MS)
        self.timer.setTimerType(qt.Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._repeat)
        qt.QApplication.instance().installEventFilter(self)

    def start(self, direction, key=None):
        self.stop()
        self.held_key = key
        self.direction = direction
        self.window.step(direction)
        if self.direction is not None and not self.window.closing and not self.window.file_loading:
            self.timer.start()

    def stop(self):
        self.timer.stop()
        self.held_key = None
        self.direction = None

    def page_shown(self):
        # Give a newly loaded spread a full interval, even after a missed slow-I/O tick.
        if self.direction is not None:
            self.timer.start()

    def _repeat(self):
        if (self.window.closing or self.window.file_loading or not self.window.isActiveWindow()
                or qt.QApplication.activePopupWidget() or qt.QApplication.activeModalWidget()):
            self.stop()
            return
        # Slow storage may miss a tick; never queue a burst or skip undisplayed pages.
        if self.window.busy or self.window.page != self.window.shown_page:
            return
        end = self.window.displayed_pages[-1]
        if (self.direction > 0 and end >= len(self.window.pages.pages) - 1
                or self.direction < 0 and self.window.page == 0):
            self.stop()
            return
        self.window.step(self.direction)

    def eventFilter(self, watched, event):
        if watched is self.window.canvas and event.type() == qt.QEvent.Type.Wheel:
            event.accept()
            if (event.modifiers() or self.window.busy or self.window.file_loading or self.window.closing
                    or qt.QApplication.activeModalWidget() or qt.QApplication.activePopupWidget()):
                return True
            direction = self.wheel.direction(event, settings=get_wheel_navigation_settings())
            if direction:
                self.stop()
                self.window.step(direction)
            return True
        if watched is self.window and event.type() in (
                qt.QEvent.Type.WindowDeactivate, qt.QEvent.Type.Hide, qt.QEvent.Type.Close):
            self.stop()
        if (not isinstance(watched, qt.QWidget) or watched.window() is not self.window
                or event.type() not in (qt.QEvent.Type.ShortcutOverride, qt.QEvent.Type.KeyPress,
                                        qt.QEvent.Type.KeyRelease)):
            return super().eventFilter(watched, event)
        if event.type() == qt.QEvent.Type.KeyRelease and event.key() == self.held_key:
            if not event.isAutoRepeat():
                self.stop()
            event.accept()
            return True
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
            self.start(-direction if self.window.pages.right_to_left else direction, key)
        else:
            self.stop()
            if key in (qt.Qt.Key.Key_Up, qt.Qt.Key.Key_Down):
                self.start(1 if key == qt.Qt.Key.Key_Down else -1, key)
            elif key in (qt.Qt.Key.Key_Home, qt.Qt.Key.Key_End):
                self.window.go(0 if key == qt.Qt.Key.Key_Home else len(self.window.pages.pages) - 1)
            else:
                self.window.leave_fullscreen()
