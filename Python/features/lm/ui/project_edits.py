"""Marshal bounded model edits to the GUI thread, guarding every live IDE buffer."""
from threading import Event

from commonUtils.ui import pyside as qt
from .ide_context import ide_pages


class ProjectEditDispatcher(qt.QObject):
    requested = qt.Signal(object)
    changes_saved = qt.Signal(object)

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.requested.connect(self._apply, qt.Qt.ConnectionType.QueuedConnection)

    def dispatch(self, tools, args, cancelled):
        request = dict(tools=tools, args=args, cancelled=cancelled, done=Event())
        if qt.QThread.currentThread() == self.thread():
            self._apply(request)
        else:
            self.requested.emit(request)
            while not request['done'].wait(.05):
                if cancelled():
                    # A queued callback rechecks cancellation before touching files.
                    raise ValueError('Edit cancelled.')
        if 'error' in request:
            raise request['error']
        return request['result']

    @qt.Slot(object)
    def _apply(self, request):
        try:
            if request['cancelled']():
                raise ValueError('Edit cancelled.')
            request['result'] = request['tools'].apply_edit(request['args'],
                validate_editors=self.validate_editors, publish_editors=self.publish_editors,
                cancelled=request['cancelled'])
            self.changes_saved.emit(list(request['tools'].changes))
        except Exception as error:
            request['error'] = error
        finally:
            request['done'].set()

    def undo_changes(self, project, changes, saved):
        """Preflight the whole turn, then publish each guarded file and checkpoint progress."""
        from ..project_tools import ProjectTools, MAX_FILE_BYTES
        from ..undo import reverse_patch
        from commonUtils.persistence.text import write_text_file, decode_bytes
        import stat
        tools = ProjectTools(project)
        plans = []
        for change in changes:
            if change.get('undone', False):
                continue
            try:
                path = tools.path(change['path'])
                snapshot = tools.disk_snapshot(change['path'])
                text = reverse_patch(snapshot.text, change['patch'])
                content = snapshot.encode(text)
                if len(content) > MAX_FILE_BYTES:
                    raise ValueError('Reverted file exceeds the 256 KiB limit.')
                if not path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
                    raise ValueError('The file is read-only.')
                self.validate_editors(path, snapshot)
                plans.append((change, path, snapshot, content))
            except (OSError, ValueError) as error:
                raise ValueError(f'{change["path"]}: {error}') from error
        for change, path, snapshot, content in plans:
            try:
                tools.path(change['path'])
                editors = self.validate_editors(path, snapshot)
                write_text_file(path, content, expected=snapshot.original)
                change['undone'] = True
                try:
                    self.publish_editors(editors, decode_bytes(content, path=path))
                finally:
                    saved()
            except (OSError, ValueError) as error:
                raise ValueError(f'{change["path"]}: {error}') from error

    def validate_editors(self, path, snapshot):
        editors, seen = [], set()
        for page in ide_pages(self.owner):
            for workspace in page.views:
                for opened, doc in workspace.documents.items():
                    same = opened.resolve() == path
                    if not same:
                        try:
                            same = opened.samefile(path)
                        except OSError:
                            pass
                    if not same or id(doc.buffer) in seen:
                        continue
                    buffer = doc.buffer
                    seen.add(id(buffer))
                    if (workspace.closing or buffer.autosave.busy or buffer.autosave.error
                            or buffer.text.isModified()
                            or buffer.text.toPlainText() != snapshot.text
                            or buffer.snapshot.original != snapshot.original):
                        raise ValueError('Open editor has pending changes, a stale version or an autosave in progress. '
                                         'Save or reload it, then read again before editing.')
                    if any((getattr(view, 'editor', view)).isReadOnly() for view in buffer.views):
                        raise ValueError('An open editor is read-only.')
                    # Aliases to another hard link would diverge after atomic replace.
                    if opened.resolve() != path:
                        raise ValueError('The file is open through another filesystem alias.')
                    editors.append((workspace, buffer))
        return editors

    @staticmethod
    def publish_editors(editors, saved):
        for workspace, buffer in editors:
            buffer.autosave.timer.stop()
            buffer.snapshot = saved
            cursor = qt.QTextCursor(buffer.text)
            cursor.beginEditBlock()
            cursor.select(qt.QTextCursor.SelectionType.Document)
            cursor.insertText(saved.text)
            cursor.endEditBlock()
            buffer.text.setModified(False)
            buffer.configure()
            buffer.autosave.last_text = saved.text
            buffer.autosave.timer.stop()
            workspace.watch.addPath(str(saved.path))
            workspace.update_buffer_titles(buffer)
            workspace.status.setText(f'Saved model edit: {saved.path.name}')
