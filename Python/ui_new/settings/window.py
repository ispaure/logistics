"""One central settings destination, also available from standalone tools."""
from commonUtils.ui import pyside as qt
from shiboken6 import isValid


class SettingsWindow(qt.QMainWindow):
    def closeEvent(self, event):
        if self.centralWidget().can_close():
            super().closeEvent(event)
        else:
            event.ignore()


def open_settings(parent=None, category='commonutils'):
    from ui_new.pages.settings import SettingsPage
    app = qt.QApplication.instance()
    for window in app.topLevelWidgets():
        for page in window.findChildren(SettingsPage):
            if isValid(page):
                reveal = getattr(page, 'reveal', None)
                if callable(reveal):
                    reveal()
                page.show_category(category)
                window.show(); window.raise_(); window.activateWindow()
                return page
    window = SettingsWindow(parent)
    window.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
    window.setWindowTitle('Logistics Settings')
    page = SettingsPage(window)
    window.setCentralWidget(page)
    window.resize(1000, 700)
    page.show_category(category)
    window.show()
    return page
