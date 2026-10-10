"""Logistics archive workspace: route user commands and report job outcomes."""
from pathlib import Path

from commonUtils.ui import pyside as qt
from commonUtils.ui.archive_view import size_text
from commonUtils import archives
from .chrome import build_workspace
from .create import NewArchiveDialog
from .dialogs import extraction_destination, confirm_removal
from .session import ArchiveSession


class ArchivePage(qt.QWidget):
    idle = qt.Signal()
    archive_changed = qt.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('navigation_position', 'workspace')
        self.setProperty('navigation_order', 15)
        self.setObjectName('archiveWorkspace')
        self.setAcceptDrops(True)
        self.path = None
        self.session = ArchiveSession(self)
        self.task = self.session.task
        self.session.completed.connect(self._completed)
        self.session.state_changed.connect(self._enabled)
        self.session.idle.connect(self.idle.emit)
        build_workspace(self)
        self._enabled()

    @property
    def busy(self):
        return self.session.busy

    @property
    def closing(self):
        return self.session.closing

    def _enabled(self):
        available = bool(self.path) and not self.busy and not self.closing
        for key, button in self.commands.items():
            button.setEnabled(not self.busy and not self.closing if key in ('open', 'create') else available)
        selected = self.contents.selected_paths()
        editable = available and archives.is_zip_archive(self.path)
        self.edit_menu.setEnabled(editable)
        self.remove_action.setEnabled(editable and bool(selected))
        self.commands['selected'].setEnabled(available and bool(selected))
        self.contents.set_state(busy=self.busy, editable=editable, closing=self.closing)
        self.location.setEnabled(not self.busy and not self.closing)
        self.reload.setEnabled(available)

    def open_dialog(self):
        if self.busy or self.closing:
            return
        path, _ = qt.QFileDialog.getOpenFileName(self, 'Open archive', str(self.path or ''), archives.ARCHIVE_FILTER)
        if path:
            self.open_archive(path)

    def open_archive(self, path):
        if not path:
            return False
        candidate = Path(path).absolute()
        return self._run('open', lambda progress, cancelled, password: archives.entries(candidate, progress=progress, cancelled=cancelled), candidate)

    def refresh(self):
        if self.path:
            self.open_archive(self.path)

    def _run(self, kind, work, path=None, *, unlock=False, password=None):
        started = self.session.start(kind, work, path or self.path, unlock=unlock, password=password)
        if started:
            self.status.setText(self.task.message.text())
        return started

    def _completed(self, kind, path, result, error):
        if error:
            self.status.setText(f'Operation failed: {error}')
        elif result is None:
            self.status.setText('Cancelled. No output was published.')
        elif kind == 'open':
            self.path = path
            self.location.setText(str(path))
            self.contents.set_entries(path, result)
            files = [entry for entry in result if not entry.directory]
            try:
                packed = path.stat().st_size
            except OSError:
                packed = 0
            self.summary.setText(f'{path.name}  /  {len(files):,} files  /  {size_text(sum(entry.size for entry in files))} unpacked  /  {size_text(packed)} archive'
                                 + ('  /  Encrypted' if any(entry.encrypted for entry in result) else ''))
            self.status.setText('Archive opened. Double-click folders to explore; select files to extract or preview.')
        elif kind == 'preview':
            self.contents.show_preview(result)
            self.status.setText('Preview ready.')
        elif kind == 'test':
            self.status.setText(f'Integrity check passed: {result:,} entries read successfully.'
                                + (' TAR has no per-entry checksums.' if not archives.is_zip_archive(path) else ''))
        elif kind == 'extract':
            self.status.setText(f'Extracted to {result}')
            self.archive_changed.emit(result)
            if self.path != path and not self.closing:
                qt.QTimer.singleShot(0, self, lambda: self.open_archive(path))
        elif kind in ('create', 'edit'):
            self.status.setText(f'Archive verified and saved: {result}')
            self.archive_changed.emit(result)
            if not self.closing:
                qt.QTimer.singleShot(0, self, lambda: self.open_archive(result))

    def _extract(self, selected=None):
        if self.path:
            return self.extract_path(self.path, selected=selected)
        return False

    def extract_path(self, path, *, selected=None):
        """Explicit browser extraction can start without first opening headers."""
        if self.busy or self.closing:
            return False
        path = Path(path).absolute()
        try:
            destination = extraction_destination(self, path)
        except ValueError as error:
            self.status.setText(str(error))
            return False
        if destination is None:
            return False
        return self._run('extract', lambda progress, cancelled, password: archives.extract(path, destination,
            selected=selected, password=password, progress=progress, cancelled=cancelled), path, unlock=True)

    def extract_all(self):
        self._extract()

    def extract_selected(self, selected=None):
        if selected is None or isinstance(selected, bool):
            selected = self.contents.selected_paths()
        if selected:
            self._extract(selected)

    def test(self):
        if self.path:
            path = self.path
            self._run('test', lambda progress, cancelled, password: archives.test_archive(path, password=password,
                       progress=progress, cancelled=cancelled), unlock=True)

    def preview_selected(self, name=None):
        if name is None or isinstance(name, bool):
            selected = self.contents.files.selectedItems()
            if len(selected) != 1:
                return
            name, directory = selected[0].data(0, qt.Qt.ItemDataRole.UserRole)
            if directory:
                return
        path = self.path
        preview = archives.preview_image if archives.is_image_entry(name) else archives.preview
        self._run('preview', lambda progress, cancelled, password: preview(path, name, password=password,
                    progress=progress, cancelled=cancelled), unlock=True)

    def new_archive(self, checked=False, sources=()):
        if self.busy or self.closing:
            return
        dialog = NewArchiveDialog(sources, self)
        try:
            if dialog.exec() != qt.QDialog.DialogCode.Accepted:
                return
            options = dialog.options()
        finally:
            dialog.deleteLater()
        self._run('create', lambda progress, cancelled, password: archives.create(**options, progress=progress, cancelled=cancelled),
                  options['destination'], password=options['password'])

    def _edit(self, sources=(), remove=()):
        if not self.path:
            return
        path = self.path
        self._run('edit', lambda progress, cancelled, password: archives.update_zip(path, sources=sources,
                  remove=remove, password=password, progress=progress, cancelled=cancelled), unlock=True)

    def add_files(self):
        paths, _ = qt.QFileDialog.getOpenFileNames(self, 'Add files to ZIP')
        if paths:
            self._edit(sources=paths)

    def add_folder(self):
        path = qt.QFileDialog.getExistingDirectory(self, 'Add folder to ZIP')
        if path:
            self._edit(sources=[path])

    def remove_selected(self, selected=None):
        if selected is None or isinstance(selected, bool):
            selected = self.contents.selected_paths()
        if selected and confirm_removal(self, self.path, selected):
            self._edit(remove=selected)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy and not self.closing and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if not paths or self.busy or self.closing:
            return
        event.acceptProposedAction()
        if len(paths) == 1 and paths[0].is_file() and archives.is_supported_archive(paths[0]):
            self.open_archive(paths[0])
        else:
            self.new_archive(sources=paths)

    def can_close(self):
        return True

    def prepare_close(self):
        return self.session.prepare_close()
