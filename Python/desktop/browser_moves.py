"""Run desktop browser moves with the provider transfer and reader-state services."""
from dataclasses import dataclass
from pathlib import Path

from commonUtils.filesystem.local_access import check_local_path
from commonUtils.persistence.publication import mutation_lock
from commonUtils.runtime.operations import MutationIncomplete, OperationCancelled, check_cancelled
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.mutations import move_resource
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress


@dataclass(frozen=True)
class MoveSource:
    provider: object
    path: str
    revision: object = None

    @property
    def physical(self):
        return self.provider.root / self.path

    @classmethod
    def local(cls, path):
        path = Path(path)
        check_local_path(path)
        return cls(LocalFiles(path.parent), path.name)


@dataclass(frozen=True)
class BrowserMoveResult:
    completed: tuple
    issues: tuple
    cancelled: bool
    failed: bool = False


PRIVATE_MOVE_MIME = 'application/x-logistics-private-move'


class PrivateMoveMime(qt.QMimeData):
    def __init__(self, sources):
        super().__init__()
        self.sources = sources
        self.setData(PRIVATE_MOVE_MIME, b'1')


def install_private_browser_moves(host, layout):
    from .browser_drop import BrowserDropTargets

    BrowserDropTargets.instance()
    return BrowserMoves(host, layout)


def move_selection(sources, destination, folder, state_root, *, cancelled, report, name_override=None):
    from desktop.document_catalog import relocate_reference, source_reference
    from services.documents.progress import prepare_local_progress_move
    from services.documents.progress_identity import ordinary_local_provider

    completed, issues = [], []
    failed = False
    paths = {item.physical for item in sources}
    sources = tuple(item for item in sources if not any(parent in paths for parent in item.physical.parents))
    total = len(sources)
    for index, item in enumerate(sources):
        source, path = item.provider, item.path
        name = Path(path).name
        target = '/'.join(filter(None, (folder, name_override or name)))
        destination_path = destination.root / target

        def progress(*, phase, done=0, total=None, **_):
            report(done, total or 0, f'{phase} · {name} ({index + 1}/{len(sources)})')

        try:
            with mutation_lock:
                check_cancelled(cancelled)
                if item.revision is not None and source.entry(path)['revision'] != item.revision:
                    raise ValueError('The selected item changed. Select it again before moving.')
                if source.storage_id == destination.storage_id and source.storage_namespace == destination.storage_namespace and path == target:
                    completed.append((item, destination_path))
                    continue
                ordinary = ordinary_local_provider(source) is not None and ordinary_local_provider(destination) is not None
                relocate_progress = None
                origin = None
                try:
                    origin = source_reference(item.physical, source)
                except (OSError, ValueError) as error:
                    issues.append(f'{name}: Could not prepare Home references ({error}).')
                try:
                    relocate_progress = prepare_local_progress_move(None, source, path, destination, target,
                                                                    cancelled=cancelled, state_root=state_root)
                except (OSError, ValueError) as error:
                    issues.append(f'{name}: Could not prepare reading history ({error}).')
                try:
                    result = move_resource(source, path, destination, target, cancelled=cancelled, progress=progress)
                except MutationIncomplete as error:
                    for removed in error.result.removed_paths:
                        try:
                            relocate_reference(source_reference(source.root / removed, source))
                        except (OSError, ValueError) as reference_error:
                            issues.append(f'{name}: Could not clear an old Home reference ({reference_error}).')
                    raise
                if result.source_state == 'removed':
                    completed.append((item, destination_path))
                    try:
                        target_reference = source_reference(destination_path, destination)[0] if ordinary else None
                        if origin is not None:
                            relocate_reference(origin, target_reference)
                    except (OSError, ValueError) as error:
                        issues.append(f'{name}: Could not update Home references ({error}).')
                    if relocate_progress is not None:
                        try:
                            relocate_progress()
                        except (OSError, ValueError) as error:
                            issues.append(f'{name}: Could not carry reading history ({error}).')
                    if not ordinary:
                        issues.append(f'{name}: Reading history stays in its original storage. The old Home reference was removed.')
        except OperationCancelled:
            return BrowserMoveResult(tuple(completed), tuple(issues), True, failed)
        except (OSError, ValueError) as error:
            issues.append(f'{name}: {error}')
            failed = True
        report(index + 1, total, f'Processed {name}')
    return BrowserMoveResult(tuple(completed), tuple(issues), False, failed)


def copy_selection(sources, destination, folder, *, cancelled, report):
    from .browser_copy import copy_item

    completed, issues = [], []
    paths = {item.physical for item in sources}
    sources = tuple(item for item in sources if not any(parent in paths for parent in item.physical.parents))
    for index, item in enumerate(sources, 1):
        name = Path(item.path).name
        target = '/'.join(filter(None, (folder, name)))

        def progress(*, phase, done=0, total=0):
            report(done, total, f'{phase} · {name} ({index}/{len(sources)})')

        try:
            if getattr(item.provider, 'remote_storage', False):
                from features.rclone.transfers.remote_download import download_remote_item

                def remote_progress(stats):
                    progress(phase='Downloading', done=stats.get('bytes') or 0, total=stats.get('totalBytes') or 0)

                download_remote_item(item.provider, item.path, destination.root / target, cancelled=cancelled,
                                     progress=remote_progress, recoverable=False, expected_revision=item.revision)
            else:
                copy_item(item.provider, item.path, destination, target, cancelled=cancelled, progress=progress,
                          revision=item.revision)
            completed.append((item, destination.root / target))
        except OperationCancelled:
            return BrowserMoveResult(tuple(completed), tuple(issues), True, bool(issues))
        except (OSError, ValueError) as error:
            issues.append(f'{name}: {error}')
    return BrowserMoveResult(tuple(completed), tuple(issues), False, bool(issues))


class BrowserMoves(qt.QObject):
    """Keep a destination and all of its provider leases alive until retirement."""

    def __init__(self, host, layout):
        super().__init__(host)
        self.host = host
        self.browser = host.file_browser
        self.operation = OperationProgress(host)
        self.operation.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.operation.completed.connect(self._finished)
        layout.addWidget(self.operation)
        self.releases = []
        self.clipboard_request = None
        self.affected = set()

    @property
    def busy(self):
        return self.operation.busy

    def stop(self):
        self.operation.request_cancel()
        return self.busy

    def available(self):
        actions = getattr(self.browser, 'file_actions', None)
        export = getattr(self.host, 'browser_export', None)
        return (not self.host.closing and self.host.isEnabled() and self.browser.isEnabled()
                and not self.busy and not (export and export.operation.busy)
                and not (actions.busy if actions is not None else self.browser.busy))

    def handoff(self, message):
        if message and not self.busy and not self.host.closing:
            self.operation.bar.hide()
            self.operation.cancel_button.hide()
            self.operation.message.setText(message)
            self.operation.show()

    def _provider(self, directory):
        provider = getattr(self.host, 'provider', None)
        return (provider, provider.relative(directory)) if provider is not None else (LocalFiles(directory), '')

    def paste(self, directory=None):
        from commonUtils.ui.file_browser.file_actions import clipboard_files

        directory = directory or self.browser.navigation.directory
        if directory is None:
            return
        mime = qt.QApplication.clipboard().mimeData()
        if isinstance(mime, PrivateMoveMime):
            self.start(mime.sources, directory, clipboard_request=mime)
            return
        paths, move, marker = clipboard_files()
        if not paths:
            return
        if move and (marker or not hasattr(self.browser, 'file_actions')):
            self.start(tuple(MoveSource.local(path) for path in paths), directory,
                       clipboard_request=(paths, move, marker))
        elif hasattr(self.browser, 'file_actions'):
            self.browser.file_actions.paste(directory)

    def selected_sources(self):
        provider = self.host.provider
        return tuple(MoveSource(provider, row['path'], row.get('revision')) for row in self.browser.selected_rows())

    def cut_selected(self):
        if self.host.isEnabled() and not self.host.closing and not self.busy:
            sources = self.selected_sources()
            if sources:
                qt.QApplication.clipboard().setMimeData(PrivateMoveMime(sources))

    def clear_private_cut(self):
        mime = qt.QApplication.clipboard().mimeData()
        if isinstance(mime, PrivateMoveMime) and any(item.provider is self.host.provider for item in mime.sources):
            qt.QApplication.clipboard().clear()

    def start(self, sources, directory=None, *, destination=None, name=None, clipboard_request=None,
              native=False, copy=False):
        from commonUtils.filesystem.storage import cache_directory
        from commonUtils.runtime.resources.provider import capabilities

        if not sources or not self.available():
            return False
        provider, folder = destination or self._provider(directory)
        if not capabilities(provider).rename:
            return False
        if any(item.provider.private for item in sources) and not provider.private:
            answer = qt.QMessageBox.question(self.host, 'Move to unencrypted storage?',
                'The destination will contain decrypted files. Continue?',
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel)
            if answer != qt.QMessageBox.StandardButton.Yes or not self.available():
                return False
        try:
            for entry in {provider, *(item.provider for item in sources)}:
                if hasattr(entry, 'acquire'):
                    self.releases.append(entry.acquire())
            root = cache_directory(create=False)
            self.clipboard_request = clipboard_request
            self.affected = {provider.root / folder, *(item.physical.parent for item in sources)}
            self.browser.setEnabled(False)
            self.operation.bar.show()
            self.operation.cancel_button.show()
            if copy:
                self.operation.start(lambda report, cancelled: copy_selection(sources, provider, folder,
                                     report=report, cancelled=cancelled), message='Copying files…')
            else:
                self.operation.start(lambda report, cancelled: move_selection(sources, provider, folder, root,
                                     report=report, cancelled=cancelled, name_override=name), message='Moving files…')
        except BaseException:
            self.browser.setEnabled(True)
            self._release()
            raise
        if native:
            from .browser_transfer_view import present_browser_transfer
            present_browser_transfer(self.operation, 'Copy files' if copy else 'Move files', provider=provider)
        return True

    def _release(self):
        for release in reversed(self.releases):
            release()
        self.releases.clear()

    def _finished(self, result, error):
        from commonUtils.ui.file_browser.file_actions import prune_cut_clipboard

        self._release()
        guard = getattr(self.host, '_private_view_guard', None)
        self.browser.setEnabled(not self.host.closing and not getattr(guard, 'locked', False))
        clipboard_request, self.clipboard_request = self.clipboard_request, None
        affected, self.affected = self.affected, set()
        if result is not None:
            if isinstance(clipboard_request, PrivateMoveMime):
                clipboard = qt.QApplication.clipboard()
                if clipboard.mimeData() is clipboard_request:
                    moved = {source.physical for source, _ in result.completed}
                    clipboard_request.sources = tuple(item for item in clipboard_request.sources
                        if item.physical not in moved and not moved.intersection(item.physical.parents))
                    if not clipboard_request.sources:
                        clipboard.clear()
            elif clipboard_request is not None:
                prune_cut_clipboard(tuple(source.physical.parent.resolve() / source.physical.name
                                          for source, _ in result.completed),
                                    expected=clipboard_request)
        for widget in qt.QApplication.allWidgets():
            other = getattr(widget, 'move_actions', None)
            if other is None or other.host is not widget or other.host.closing or other.busy:
                continue
            browser = other.browser
            if hasattr(browser, 'refresh_changed'):
                directory = browser.views.browsing_directory()
                if directory in affected:
                    browser.refresh_changed(affected)
            elif browser.navigation.directory in affected and other.host.isEnabled():
                browser.refresh()
        if not self.host.closing:
            if error or result is not None and result.issues:
                self.operation.message.setText(error or '\n'.join(result.issues))
                self.operation.message.setWordWrap(True)
        else:
            self.host.idle.emit()
