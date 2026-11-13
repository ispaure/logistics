"""Host lifecycle for process-shared indexing, independent of browser ownership."""
from commonUtils.filesystem.index import directory_cache
from commonUtils.filesystem.index.coordinator import IndexCoordinator
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operations import Operation
from services.directory_index import ScanPolicy, register, unregister


class IndexService(qt.QObject):
    activity = qt.Signal(object)

    def __init__(self):
        super().__init__()
        self.policy = ScanPolicy(directory_cache)
        self.coordinator = IndexCoordinator(directory_cache, notify=self._activity,
                                            set_priority=self._set_priority,
                                            select_job=self.policy.select_job, should_yield=self.policy.should_yield)
        self.policy.coordinator = self.coordinator
        self.worker = Operation(lambda: self.coordinator.run(self.worker.isInterruptionRequested))

    def _activity(self, job):
        # A filename validation is not the browser's full metadata check.
        if not job.get('names_only'):
            self.activity.emit(job)

    def _set_priority(self, background):
        self.worker.setPriority(qt.QThread.Priority.LowPriority if background else qt.QThread.Priority.NormalPriority)

    def start(self):
        register(self.coordinator, self.policy)
        directory_cache.coordinator = self.coordinator
        directory_cache.shared_activity = self.activity
        self.worker.start(qt.QThread.Priority.LowPriority)

    def stop(self):
        unregister(self.coordinator)
        self.worker.requestInterruption()
        # The index closes its transaction/connection before another host takes
        # ownership. Never destroy a running QThread on event-loop shutdown.
        self.worker.wait()
        if directory_cache.coordinator is self.coordinator:
            directory_cache.coordinator = None
            directory_cache.shared_activity = None
