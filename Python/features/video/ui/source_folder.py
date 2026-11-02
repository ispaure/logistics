"""Retained provider browser for the video's Show in folder action."""

from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.content import ProviderContent
from commonUtils.runtime.resources.selection import ResourceSelection
from commonUtils.ui.resources.browser import ResourceBrowser


class VideoSourceFolder(qt.QMainWindow):
    idle = qt.Signal()

    def __init__(self, content):
        super().__init__()
        self.source = ProviderContent(content.provider, content.path)
        self.document_read_only = True
        self.closing = False
        self.retired = False
        self.pending_selection = True
        self.path = content.path
        try:
            model = ResourceSelection(self.source.provider)
            folder = self.path.rpartition('/')[0]
            self.browser = ResourceBrowser(model, parent=self,
                directory=self.source.provider.root / folder, preview=False)
            self.setCentralWidget(self.browser)
            self.browser.idle.connect(self.loaded)
            self.setWindowTitle('Video source folder')
            self.resize(900, 600)
            self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
            from services.documents.ui.private_views import protect_private_view
            protect_private_view(self, self.source.provider)
        except BaseException:
            self.source.close()
            self.deleteLater()
            raise

    def loaded(self):
        if self.closing:
            self.close()
            return
        if self.pending_selection:
            index = self.browser.model.browse_index(self.source.provider.root / self.path)
            if index.isValid():
                self.browser.views.select_source(index)
            self.pending_selection = False
        self.idle.emit()

    def retire_private_content(self):
        self.closing = True
        self.browser.stop()
        if not self.browser.busy:
            self.source.close()
            self.retired = True

    def closeEvent(self, event):
        self.retire_private_content()
        if self.retired:
            event.accept()
        else:
            event.ignore()
