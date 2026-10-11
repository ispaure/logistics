"""Host lifecycle for process-shared indexing, independent of browser ownership."""
from commonUtils.filesystem.index import directory_cache
from commonUtils.filesystem.index.coordinator import IndexCoordinator
from commonUtils.ui import pyside as qt
from commonUtils.ui.operations import Operation


class IndexService(qt.QObject):
    activity = qt.Signal(object)

    def __init__(self):
        super().__init__()
        self.coordinator = IndexCoordinator(directory_cache, notify=self.activity.emit,
                                            set_priority=self._set_priority)
        self.worker = Operation(lambda: self.coordinator.run(self.worker.isInterruptionRequested))

    def _set_priority(self, background):
        self.worker.setPriority(qt.QThread.Priority.LowPriority if background else qt.QThread.Priority.NormalPriority)

    def start(self):
        directory_cache.coordinator = self.coordinator
        directory_cache.shared_activity = self.activity
        self.worker.start(qt.QThread.Priority.LowPriority)

    def stop(self):
        self.worker.requestInterruption()
        # The index closes its transaction/connection before another host takes
        # ownership. Never destroy a running QThread on event-loop shutdown.
        self.worker.wait()
        if directory_cache.coordinator is self.coordinator:
            directory_cache.coordinator = None
            directory_cache.shared_activity = None
