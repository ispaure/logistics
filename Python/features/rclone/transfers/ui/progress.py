"""Desktop rclone progress presentation over commonUtils process windows.

The feature owns labels, removal counters and the captured access guard. The
shared window/runner retain rendering, process lifetime and workspace hosting.
"""
from features.rclone import session


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
        **({'environment': environment} if environment is not None else {}))
    add_removal_statistics(window, dry_run=dry_run)
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


def add_removal_statistics(window, *, dry_run):
    from commonUtils.ui import pyside as qt

    grid = window.statistics.layout()
    row = grid.rowCount()
    titles = ('Planned file deletions', 'Planned folder removals') if dry_run else (
        'File deletion attempts', 'Folder removal attempts')
    for column, (key, title) in enumerate(zip(('deleted', 'deleted_dirs'), titles)):
        label = qt.QLabel('Not reported')
        label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        window.fields[key] = label
        grid.addWidget(qt.QLabel(title), row, column * 2)
        grid.addWidget(label, row, column * 2 + 1)

    def update_removals(update):
        for key in ('deleted', 'deleted_dirs'):
            count = update.metrics.get(key)
            window.fields[key].setText(f'{int(count):,}' if count is not None else 'Not reported')

    window.runner.progress.connect(update_removals)
