"""A nonmodal Notes Library choice on entering an Obsidian folder."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from features.text_editor.notes import operation, vault_root


class NotesFolderOffer(qt.QWidget):
    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.location = None
        self.candidate = None
        self.closing = False
        self.probed = None
        layout = qt.QHBoxLayout(self)
        layout.addWidget(qt.QLabel('Obsidian folder · Open as a Notes Library?'))
        open_button = qt.QPushButton('Open as Notes Library')
        open_button.clicked.connect(self.open)
        regular = qt.QPushButton('Browse Files')
        regular.clicked.connect(self.hide)
        layout.addWidget(open_button)
        layout.addWidget(regular)
        layout.addStretch()
        self.progress = OperationProgress(self)
        self.progress.completed.connect(self.completed)
        layout.addWidget(self.progress)
        browser.layout().insertWidget(min(1, browser.layout().count()), self)
        self.hide()
        signal = getattr(browser, 'directory_changed', None)
        if signal is None:
            signal = browser.views.directory_changed
        signal.connect(self.changed)
        qt.QTimer.singleShot(0, self.changed)

    def changed(self, *args):
        if self.closing:
            return
        location = Path(self.browser.navigation.directory)
        if location == self.location:
            return
        self.location = location
        self.hide()
        self.candidate = None
        if self.progress.busy:
            self.progress.request_cancel()
            return
        self.probe(location)

    def probe(self, location):
        self.probed = location
        provider = getattr(self.browser, 'provider', None)
        # Browser providers expose decoded paths for LocalCrypt and cloud roots.
        if provider is None:
            from commonUtils.runtime.resources.local import LocalFiles
            factory = lambda: LocalFiles(location)
            root = ''
        else:
            factory = lambda: provider
            root = provider.relative(location)
        def check(report, cancelled):
            owner = factory()
            with operation(owner, cancelled):
                found = vault_root(owner, root, owner.list(root, cancelled=cancelled)) is not None
            return location, factory, root, found
        self.progress.start(check, message='Checking notes folder…', show_progress=False)

    def completed(self, result, error):
        if self.closing:
            return
        if self.probed != self.location:
            self.probe(self.location)
            return
        if error or result is None or not result[3]:
            return
        from services.documents.storage import check_document_access
        try:
            check_document_access(result[1]())
        except (OSError, ValueError):
            return
        self.candidate = result[1:3]
        self.progress.hide()
        self.show()

    def open(self):
        if self.candidate is None:
            return
        factory, root = self.candidate
        provider = factory()
        from .notes_library import open_notes
        open_notes(factory, self.location.name, root=root,
                   remote=bool(getattr(provider, 'remote_storage', False)))
        self.hide()

    def prepare_close(self):
        self.closing = True
        self.progress.request_cancel()
        return not self.progress.busy
