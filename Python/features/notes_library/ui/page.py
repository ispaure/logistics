"""Dedicated library sessions using the desktop's retained workspace lifecycle."""
from pathlib import Path
from shiboken6 import isValid
from commonUtils.ui import pyside as qt
from commonUtils.ui.document_host import register_document_host
from desktop.documents import DocumentsPage


def library_identity(provider, root):
    root = provider.relative(root)
    if not getattr(provider, 'private', False):
        return 'local', str((provider.root / root).resolve())
    connection = getattr(provider, 'connection', None)
    return ('private', str(provider.root), getattr(provider, 'storage_id', None),
            getattr(provider, 'storage_namespace', ''),
            str(getattr(connection, 'package', '')), str(getattr(connection, 'context', '')),
            getattr(connection, 'remote', ''), root)


class NotesLibraryPage(DocumentsPage):
    detached_title = 'Notes Library: {title}'
    retain_when_disabled = True

    def __init__(self, parent=None):
        super().__init__(lambda: None, parent)
        self.setAccessibleName('Notes Library')
        self.setProperty('navigation_position', 'notes_library')
        self.setProperty('navigation_key', 'feature:notes_library:notes_library.workspace')
        register_document_host(self, destination='notes_library')

    def _make_chooser(self, workspace, window=None):
        panel = qt.QWidget()
        layout = qt.QVBoxLayout(panel)
        layout.addStretch()
        title = qt.QLabel('Notes Library'); title.setObjectName('sectionTitle')
        layout.addWidget(title)
        description = qt.QLabel('Open a local folder or an unlocked LocalCrypt copy to read and edit its notes.')
        description.setWordWrap(True); layout.addWidget(description)
        button = qt.QPushButton('Open Library')
        from features.application import registry
        button.setEnabled(registry.is_feature_enabled('notes_library'))
        button.clicked.connect(lambda: self.choose_library(workspace))
        layout.addWidget(button)
        layout.addStretch()
        panel.open_button = button
        self._choosers.add(panel)
        return panel

    def _refresh_choosers(self):
        from features.application import registry
        for panel in tuple(self._choosers):
            if isValid(panel):
                panel.open_button.setEnabled(registry.is_feature_enabled('notes_library'))

    def new_document_chooser(self, workspace):
        return self.choose_library(workspace)

    def choose_library(self, workspace):
        from features.application import registry
        if not registry.is_feature_enabled('notes_library') or self.closing:
            return None
        from services.documents.ui.editors import choose_editor_resource
        choice = choose_editor_resource(self.window(), 'folder')
        if choice is None:
            return None
        try:
            provider, root = choice.provider, choice.path
            label = Path(root).name or provider.root.name or 'Notes Library'
            with self.creation_scope(workspace):
                return self.open_library(lambda: provider, label, root=root)
        except (OSError, ValueError, PermissionError) as error:
            qt.QMessageBox.warning(self, 'Open Library', str(error))
        finally:
            choice.close()

    def open_library(self, factory, label, *, root='', remote=False):
        from .library_workspace import TabbedNotesLibrary
        from features.notes_library.notes import local_library
        from features.application import registry
        if self.closing or not registry.is_feature_enabled('notes_library'):
            raise ValueError('Enable Notes Library to open a library.')
        from commonUtils.ui.resources.picker import ResourceTaskDialog
        from commonUtils.runtime.operations import check_cancelled
        loading = ResourceTaskDialog(self.window(), 'Opening Notes Library')
        prepared = []
        def prepare(report, cancelled):
            provider = factory()
            release = provider.acquire() if hasattr(provider, 'acquire') else lambda: None
            try:
                check_cancelled(cancelled)
                if remote or not local_library(provider):
                    raise ValueError('Notes Library requires a local copy. Download or sync this folder first.')
                return provider, library_identity(provider, root), release
            except BaseException:
                release()
                raise
        def completed(result, error):
            if loading.operation.cancelled.is_set() or self.closing:
                if result is not None:
                    result[2]()
            elif error:
                prepared.append(ValueError(error))
            elif result is not None:
                prepared.append(result)
            loading.accept()
        loading.operation.completed.connect(completed)
        loading.operation.completed.connect(lambda *_: self.idle.emit())
        loading.operation.start(prepare, message='Opening library storage…')
        try:
            loading.exec()
        finally:
            loading.deleteLater()
        if not prepared:
            return None
        if isinstance(prepared[0], Exception):
            raise prepared[0]
        provider, identity, lease = prepared[0]
        if self.closing or not registry.is_feature_enabled('notes_library'):
            lease()
            raise ValueError('Notes Library is closing or disabled. Reopen it after closing finishes.')
        for window, record in tuple(self.records.items()):
            if (isValid(window) and not record['closed'] and not window.locked and not window.closing
                    and getattr(window, 'library_session_identity', None) == identity):
                if window.library is None and not window.progress.busy:
                    # Failed initial loads hold no draft. Retry with the fresh provider.
                    from commonUtils.ui.document_host import close_document
                    close_document(window)
                    continue
                lease()
                self.present(window)
                return window
        # Hold the prepared provider until the library's asynchronous acquisition.
        def release():
            nonlocal lease
            callback, lease = lease, lambda: None
            callback()
        try:
            window = TabbedNotesLibrary(lambda: provider, label, remote=remote, root=root)
            window.library_session_identity = identity
            def acquired():
                if not window.progress.busy:
                    window.idle.disconnect(acquired)
                    release()
            window.idle.connect(acquired)
            window.destroyed.connect(release)
            self.present(window)
            return window
        except BaseException:
            release()
            raise
