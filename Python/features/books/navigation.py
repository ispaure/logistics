"""EPUB arrows stay page-oriented while the chapter tree has keyboard focus."""
from commonUtils.ui import pyside as qt


class BookNavigation(qt.QObject):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        qt.QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        if (event.type() not in (qt.QEvent.Type.ShortcutOverride, qt.QEvent.Type.KeyPress)
                or not isinstance(watched, qt.QWidget)
                or watched.window() is not self.page.window()
                or event.modifiers()
                or event.key() not in (qt.Qt.Key.Key_Left, qt.Qt.Key.Key_Right)):
            return False
        # Do not steal arrows from find fields, appearance controls or dialogs.
        panes = (self.page.text, self.page.spread.second, self.page.chapters, self.page.bookmark_list)
        if not any(watched is pane or pane.isAncestorOf(watched) for pane in panes):
            return False
        event.accept()
        if event.type() == qt.QEvent.Type.KeyPress and self.page.text.navigation_enabled:
            self.page.turn_page(1 if event.key() == qt.Qt.Key.Key_Right else -1)
        return True
