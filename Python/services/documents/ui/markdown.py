"""Provider-backed Markdown presentation, independent of storage encoding."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress

def choose_destination(parent, provider, name, action):
    from services.documents.ui.editors import choose_editor_resource
    choice = choose_editor_resource(parent, 'save' if action == 'Save As' else 'destination', provider, name,
                                    markdown=action == 'Save As')
    return (choice.provider, choice.path, choice.close) if choice else None


class MarkdownStorage:
    private = True
    def __init__(self, provider, path, data, resources, open_link):
        self.provider, self.path, self.data = provider, path, data
        from services.documents.storage import DocumentResource
        self.resource = DocumentResource(provider, path, max_bytes=8 * 1024 * 1024, independent=False)
        self.resources = resources
        self._initial_open_link = open_link
        self._initial_provider = provider

    def open_link(self, path, fragment=''):
        if Path(path).suffix.lower() in {'.md', '.markdown', '.txt'}:
            from services.documents.ui.editors import open_editor_choice
            from commonUtils.runtime.resources.selection import ResourceChoice
            choice = ResourceChoice(self.provider, self.provider.relative(path),
                                    self.provider.acquire() if hasattr(self.provider, 'acquire') else lambda: None)
            return open_editor_choice(choice, self.window, markdown=Path(path).suffix.lower() != '.txt', fragment=fragment, edit=False)
        if self.provider is self._initial_provider:
            return self._initial_open_link(path, fragment)
        qt.QMessageBox.information(self.window, 'Open link', 'Open this file from its current storage browser.')

    def bind_window(self, window):
        self.window = window
        window.destroyed.connect(lambda: getattr(self.resources, 'close', lambda: None)())
        self.operation = OperationProgress(window)
        self.operation.completed.connect(self._written)
        content = qt.QWidget(window)
        layout = qt.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        window.viewer.setParent(content)
        layout.addWidget(window.viewer, 1)
        layout.addWidget(self.operation)
        window.setCentralWidget(content)

    def submit_write(self, path, data, expected, completed):
        self.pending_write = data, completed
        self.window.viewer.setEnabled(False)
        self.operation.start(lambda report, cancelled: self.write_bytes(path, data, expected=expected, cancelled=cancelled), message='Encrypting local Markdown save…')

    def _written(self, result, error):
        locked = getattr(getattr(self.window, '_private_view_guard', None), 'locked', False)
        self.window.viewer.setEnabled(not locked)
        if locked:
            error = error or 'Private session locked. Reopen the document.'
        data, completed = self.pending_write
        completed(error)
        self.operation.hide()
        self.window.idle.emit()
        if not error and self.window.pending_close:
            self.window.close()
        elif error:
            self.window.pending_close = False

    def read_bytes(self, path):
        if hasattr(self.provider, '_check_active'):
            self.provider._check_active()
        if path != self.path:
            raise ValueError('Open other documents through the private browser.')
        return self.data

    def write_bytes(self, path, data, *, expected=None, cancelled=lambda: False):
        current = self.resource.read(cancelled=cancelled)
        if expected is not None and current != expected:
            raise ValueError('File changed. Reopen it before saving.')
        self.resource.save(data, cancelled=cancelled)
        self.data = data

    def open_dialog(self, viewer):
        from services.documents.ui.editors import choose_editor_resource, open_editor_choice
        if self.operation.busy:
            return False
        choice = choose_editor_resource(self.window, 'open', self.provider, markdown=True)
        if choice:
            open_editor_choice(choice, self.window, markdown=True)
        return False

    def save_as(self, viewer):
        from services.documents.storage import DocumentResource
        if self.operation.busy:
            return False
        selected = choose_destination(self.window, self.provider, self.path.name, 'Save As')
        if selected is None:
            return False
        provider, target, release = selected
        from services.documents.storage import DocumentPolicy
        if self.resource.policy.confirm_plaintext(DocumentPolicy.for_provider(provider)):
            if qt.QMessageBox.question(self.window, 'Save to unencrypted storage?',
                    'The destination will contain a decrypted copy. Continue?',
                    qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                    qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Yes:
                release()
                return False
        try:
            data = viewer.capture_save()
            if Path(target).suffix.lower() not in {'.md', '.markdown'} or len(data) > 8 * 1024 * 1024:
                raise ValueError('Choose a Markdown filename; saves are limited to 8 MiB.')
        except Exception as error:
            release()
            qt.QMessageBox.warning(self.window, 'Save As', str(error))
            return False
        if not viewer.begin_save():
            release()
            return False
        viewer.setEnabled(False)
        def completed(error):
            if error:
                release()
                viewer.complete_save(self.path, data, error)
                return
            self.window.destroyed.connect(release)
            self.resource.close()
            getattr(self.resources, 'close', lambda: None)()
            self.resource = DocumentResource(provider, target, max_bytes=8 * 1024 * 1024, independent=False)
            self.provider, self.path, self.data = provider, provider.root / target, data
            self.resources = {}
            self.window._session_private = self.window._session_private or not self.resource.policy.persistent
            viewer.complete_save(self.path, data)
        self.pending_write = data, completed
        def save_copy(report, cancelled):
            return DocumentResource.publish(provider, target, data, max_bytes=8 * 1024 * 1024, cancelled=cancelled)
        self.operation.start(save_copy, message='Saving verified copy…')
        return False

    def load_resource(self, kind, url):
        if self.resource.closed:
            return qt.QImage() if kind == qt.QTextDocument.ResourceType.ImageResource else qt.QByteArray()
        if hasattr(self.provider, '_check_active'):
            self.provider._check_active()
        if not url.isLocalFile():
            url = qt.QUrl.fromLocalFile(str(self.path.parent) + '/').resolved(url)
        target = Path(url.toLocalFile()).resolve()
        data = self.resources.get(target)
        if kind == qt.QTextDocument.ResourceType.ImageResource:
            reason = getattr(self.resources, 'errors', {}).get(target)
            from commonUtils.ui.markdown.images import prepared_image
            return prepared_image(data, reason)
        return qt.QByteArray(data or b'')

    def video_source(self, url):
        if self.resource.closed:
            return None
        return getattr(self.resources, 'videos', {}).get(Path(url.toLocalFile()).resolve())


from services.documents.markdown import prepare_markdown


from commonUtils.ui.markdown.window import MarkdownWindow


class ProgressMarkdownWindow(MarkdownWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .text_position import TextPosition

        viewer = self.viewer
        self.position = TextPosition(
            self, {'preview': viewer.browser, 'source': viewer.editor, 'formatted': viewer.formatted_editor},
            active=lambda: viewer.edit_mode.currentData() if viewer.edit_button.isChecked() else 'preview',
            set_mode=self.restore_mode, current_path=lambda: viewer.current_path, notice=viewer.status.setText,
        )
        viewer.path_changed.connect(self.bind_position)
        viewer.pages.currentChanged.connect(self.position.observe)
        self.bind_position(viewer.current_path)

    def restore_mode(self, mode):
        if mode == 'preview':
            self.viewer.set_editing(False)
        elif self.viewer.allow_edit:
            self.viewer.set_edit_mode(mode)
            self.viewer.set_editing(True)

    def bind_position(self, path):
        viewer = self.viewer
        storage = viewer.storage
        resource = getattr(storage, 'resource', None)
        provider = resource.provider if resource is not None else None
        data = storage.data if resource is not None else viewer.editor.toPlainText().encode('utf-8')
        url = viewer.history[viewer.history_index]['url'] if 0 <= viewer.history_index < len(viewer.history) else None
        self.position.bind(provider, path, data, kind='desktop-markdown', restore=url is None or not url.fragment())

    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted():
            self.position.retire()


def activate_markdown(item, context):
    from commonUtils.formats.markdown.file import MarkdownFile

    if not isinstance(item, MarkdownFile):
        return False
    open_markdown(item.path)
    return True


def open_markdown(path=None, *, allow_edit=False):
    from .editors import retain

    return retain(ProgressMarkdownWindow(path, allow_edit=allow_edit))


class PrivateMarkdownWindow(ProgressMarkdownWindow):
    idle = qt.Signal()
    def __init__(self, path, storage, *, edit=True):
        self.pending_close = False
        self._session_private = not storage.resource.policy.persistent
        super().__init__(path, allow_edit=True, storage=storage)
        if not edit:
            self.viewer.set_editing(False)
        storage.bind_window(self)
        from services.documents.ui.private_views import protect_private_view
        protect_private_view(self, storage.provider)

    def _update_title(self):
        super()._update_title()
        if self._session_private:
            self.setWindowTitle('🕵️ Private - ' + self.windowTitle())

    def retire_private_content(self):
        self.position.retire()
        viewer, storage = self.viewer, self.viewer.storage
        viewer.browser.inline_videos.clear()
        viewer.formatted_editor.inline_videos.clear()
        viewer.speech.stop()
        if viewer._diagram_renderer:
            viewer._diagram_renderer.cancel()
        storage.resource.close()
        getattr(storage.resources, 'close', lambda: None)()
        storage.data, storage.resources = b'', {}
        blockers = [qt.QSignalBlocker(widget) for widget in
                    (viewer, viewer.editor, viewer.formatted_editor, viewer.browser)]
        for widget in (viewer.editor, viewer.formatted_editor, viewer.browser):
            widget.setUndoRedoEnabled(False)
            widget.clear()
        viewer.document_state.new()
        viewer.history.clear()
        viewer.history_index = -1
        viewer.location.clear()
        viewer.document_title.clear()
        del blockers

    def closeEvent(self, event):
        storage = self.viewer.storage
        if storage.operation.busy:
            self.pending_close = True
            event.ignore()
            return
        if getattr(getattr(self, '_private_view_guard', None), 'locked', False):
            event.accept()
            return
        super().closeEvent(event)
        if storage.operation.busy:
            self.pending_close = True
