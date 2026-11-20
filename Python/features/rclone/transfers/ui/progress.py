"""Desktop rclone progress presentation over commonUtils process windows."""
from functools import partial

from features.rclone import session


def open_download_progress(provider, path, destination):
    """Present a staged download using the same progress view as a Pull."""
    from threading import Event

    from commonUtils.runtime.operations import OperationCancelled
    from commonUtils.ui import pyside as qt
    from commonUtils.ui.tasks.operations import ProgressOperation
    from commonUtils.ui.tasks.process_progress import ProcessProgressWindow, present_process_window
    from commonUtils.ui.tasks.process_runner import ProcessResult
    from features.rclone.transfers.progress import RcloneProgressParser
    from features.rclone.transfers.remote_download import download_remote_item

    class DownloadRunner(qt.QObject):
        output = qt.Signal(str)
        status = qt.Signal(str, int, str)
        progress = qt.Signal(object)
        completed = qt.Signal(object)

        def __init__(self, release):
            super().__init__()
            self.release = release
            self.busy = False
            self.cancelled = Event()
            self.parser = RcloneProgressParser()
            self.worker = ProgressOperation(self)
            self.worker.thread.finished.connect(self.finish, qt.Qt.ConnectionType.QueuedConnection)

        def start(self):
            self.busy = True
            self.worker.callback = self.download
            self.status.emit('running', 1, 'Preparing download…')
            self.worker.start()

        def download(self):
            try:
                return download_remote_item(provider, path, destination,
                    cancelled=self.cancelled.is_set, progress=self.report)
            except OperationCancelled:
                return None
            finally:
                self.release()

        def report(self, stats):
            update = self.parser.parse_record({'stats': stats})
            self.progress.emit(update)
            if not self.cancelled.is_set():
                self.status.emit(update.state, 1, update.message)

        def cancel(self):
            if self.busy:
                self.cancelled.set()
                self.status.emit('running', 1, 'Cancelling safely…')

        @qt.Slot()
        def finish(self):
            self.worker.thread.wait()
            self.worker.callback = None
            self.busy = False
            error = self.worker.error or ''
            if self.worker.result is not None:
                result = ProcessResult('succeeded', 0, 1)
                message = 'Downloaded successfully.'
                from desktop.file_browser import refresh_download_directory
                refresh_download_directory(destination)
            elif error:
                result = ProcessResult('failed', None, 1, error)
                self.output.emit(error)
                message = error
            else:
                result = ProcessResult('cancelled', None, 1)
                message = 'Cancelled.'
            self.status.emit(result.state, 1, message)
            self.completed.emit(result)

    release = provider.acquire()
    try:
        window = ProcessProgressWindow('Pull · Download locally', runner=DownloadRunner(release),
            context={'operation': 'Pull', 'source': provider.storage_label, 'destination': str(destination)},
            presentation=transfer_presentation(dry_run=False))
        present_process_window(window)
        window.runner.start()
    except BaseException:
        release()
        raise
    return window


def open_transfer_progress(arguments, *, source, destination, dry_run,
                           credential_path, revoked, cancelled, session_bound,
                           environment=None):
    """Launch the existing process window and bind rclone presentation/lifetime."""
    from commonUtils.ui.tasks.process_progress import open_process
    from features.rclone.transfers.progress import RcloneProgressParser

    window = open_process('rclone sync (dry run)' if dry_run else 'rclone sync',
        arguments[0], arguments[1:], parser=RcloneProgressParser(),
        context={'operation': 'Sync (dry run)' if dry_run else 'Sync',
                 'source': source, 'destination': destination, 'dry_run': dry_run},
        presentation=transfer_presentation(dry_run=dry_run, show_removals=True),
        **({'environment': environment} if environment is not None else {}))
    watch_transfer(window, credential_path, revoked, cancelled, session_bound=session_bound)
    return window


def watch_transfer(window, config_path, revoked, cancelled, *, session_bound):
    """Keep the captured access/cancellation binding alive with the GUI process."""
    from commonUtils.ui import pyside as qt

    class Guard(qt.QObject):
        stop = qt.Signal()

        def invalidate(self):
            self.stop.emit()

        def release(self, *_):
            self.timer.stop()
            self.unsubscribe()

        def poll(self):
            if revoked() or cancelled():
                self.timer.stop()
                self.invalidate()

    guard = Guard(window)
    guard.stop.connect(window.runner.cancel, qt.Qt.ConnectionType.QueuedConnection)
    guard.unsubscribe = session.on_forget(config_path, guard.invalidate) if session_bound else lambda: None
    guard.timer = qt.QTimer(guard)
    guard.timer.timeout.connect(guard.poll)
    guard.timer.start(100)
    window.runner.completed.connect(guard.release)
    window.destroyed.connect(guard.release)
    window._session_guard = guard
    # A reload between launch and subscription must not attach old work to new keys.
    guard.poll()
    if not window.busy:
        guard.release()


def removal_rows(dry_run):
    titles = ('Planned file deletions', 'Planned folder removals') if dry_run else (
        'File deletion attempts', 'Folder removal attempts')
    return tuple(zip(('deleted', 'deleted_dirs'), titles))


def transfer_presentation(*, dry_run, show_removals=False):
    from commonUtils.ui.tasks.process_transfer_progress import TransferProgressPresentation

    return partial(TransferProgressPresentation,
                   bytes_title='Planned / total' if dry_run else 'Transferred / total',
                   progress_format='Planned: %p%' if dry_run else None,
                   count_rows=removal_rows(dry_run) if show_removals else ())


def add_removal_statistics(window, *, dry_run):
    """Add removal counters to an existing transfer window."""
    window.presentation.add_count_rows(removal_rows(dry_run))
