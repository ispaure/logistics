"""Choose a folder's presentation before the browser publishes its contents."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from features.text_editor.notes import operation, vault_root, local_library


class NotesFolderOffer(qt.QWidget):
    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.location = None
        self.accepted = None
        self.candidate = None
        self.closing = False
        self.probed = None
        self.resume = None
        self.dialog = None
        self.progress = OperationProgress(self)
        self.progress.completed.connect(self.completed)
        from features.application import registry
        self.enabled = registry.is_feature_enabled('text_editor')
        self._unsubscribe = registry.subscribe(self.features_changed)
        self.destroyed.connect(self._unsubscribe)
        self.hide()
        browser.directory_gate = self.request
        signal = getattr(browser, 'directory_changed', None)
        if signal is None:
            signal = browser.views.directory_changed
        signal.connect(self.changed)

    def changed(self, path):
        # Only a published location counts as a visit (including refreshes).
        self.accepted = Path(path) if path is not None else None

    def features_changed(self):
        from features.application import registry
        self.enabled = registry.is_feature_enabled('text_editor')
        if not self.enabled and not self.closing:
            self.dismiss()
            self.progress.request_cancel()
            self.browse()

    def dismiss(self):
        dialog, self.dialog = self.dialog, None
        if dialog is not None:
            dialog.reject()
            dialog.deleteLater()

    def request(self, location, resume):
        location = Path(location)
        if self.closing:
            return True
        if location == self.location and self.resume is not None:
            return True
        self.dismiss()
        self.location, self.resume = location, resume
        self.candidate = None
        provider = getattr(self.browser, 'provider', None)
        # The local browser already stats paths during navigation. Avoid a
        # worker/listing for ordinary folders; provider paths must stay decoded.
        if (not self.enabled or location == self.accepted or (provider is not None and not local_library(provider))
                or (provider is None and not (location / '.obsidian').is_dir())):
            self.resume = None
            self.progress.request_cancel()
            return False
        if self.progress.busy:
            self.progress.request_cancel()
        else:
            self.probe(location)
        return True

    def probe(self, location):
        self.probed = location
        provider = getattr(self.browser, 'provider', None)
        if provider is None:
            from services.documents.storage import local_document_provider
            factory = lambda: local_document_provider(location)
            root = ''
        else:
            factory = lambda: provider
            root = provider.relative(location)
        def check(report, cancelled):
            owner = factory()
            with operation(owner, cancelled):
                found = local_library(owner) and vault_root(owner, root, owner.list(root, cancelled=cancelled)) is not None
            return location, factory, root, found
        self.progress.start(check, message='Checking notes folder…', show_progress=False)

    def completed(self, result, error):
        if self.closing or self.resume is None or self.browser_closed():
            return
        if self.probed != self.location or self.progress.cancelled.is_set():
            self.probe(self.location)
            return
        if error or result is None or not result[3]:
            self.browse()
            return
        from services.documents.storage import check_document_access
        try:
            check_document_access(result[1]())
        except (OSError, ValueError):
            self.resume = None
            return
        self.candidate = result[1:3]
        dialog = self.dialog = qt.QMessageBox(self.browser.window())
        dialog.setWindowTitle('Open Obsidian folder')
        dialog.setText('Open this folder as a Notes Library or browse its files?')
        notes = dialog.addButton('Open as Notes Library', qt.QMessageBox.ButtonRole.AcceptRole)
        files = dialog.addButton('Browse Files', qt.QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(qt.QMessageBox.StandardButton.Cancel)
        dialog.setWindowModality(qt.Qt.WindowModality.WindowModal)
        def chosen(*args):
            if self.dialog is not dialog or self.closing:
                return
            self.dialog = None
            clicked = dialog.clickedButton()
            dialog.deleteLater()
            if clicked is notes:
                self.open()
            elif clicked is files:
                self.browse()
            else:
                self.resume = None
                self.candidate = None
        dialog.finished.connect(chosen)
        dialog.open()

    def browse(self):
        resume, self.resume = self.resume, None
        self.candidate = None
        if resume is not None and not self.closing and not self.browser_closed():
            provider = getattr(self.browser, 'provider', None)
            if provider is not None:
                from services.documents.storage import check_document_access
                try:
                    check_document_access(provider)
                except (OSError, ValueError):
                    return
            self.accepted = self.location
            resume()

    def browser_closed(self):
        return getattr(self.browser, 'stopping', False) or getattr(self.browser, 'closing', False)

    def open(self):
        if self.candidate is None or self.closing or not self.enabled or self.browser_closed():
            return
        factory, root = self.candidate
        from services.documents.storage import check_document_access, document_remote
        try:
            provider = factory()
            check_document_access(provider)
        except (OSError, ValueError):
            self.resume = None
            self.candidate = None
            return
        self.resume = None
        self.candidate = None
        from .notes_library import open_notes
        open_notes(factory, self.location.name, root=root, remote=document_remote(provider))

    def prepare_close(self):
        self.closing = True
        self._unsubscribe()
        self.resume = None
        self.dismiss()
        self.progress.request_cancel()
        return not self.progress.busy
