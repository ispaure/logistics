"""Host admission and foreground policy for the ordinary directory index.

Only explicitly admitted physical local callers reach this service. Private
provider metadata remains owned by its credential-scoped provider.
"""
from pathlib import Path
from contextlib import contextmanager
from threading import Event, RLock, Thread
from time import monotonic
from weakref import finalize

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.filesystem.index.coordinator import IndexCoordinator

_lock = RLock()
_hosts = {}


class ScanPolicy:
    """Debounced foreground demand with a bounded turn for deferred work."""
    def __init__(self, cache):
        self.cache = cache
        self.coordinator = None
        self.lock = RLock()
        self.owners = {}
        self.hints = {}
        self.served = {}
        self.started = {}
        self.quanta = {}

    def active(self, owner, value):
        with self.lock:
            self.owners[owner] = value

    def focus(self, owner, paths):
        paths = tuple(Path(path).absolute() for path in paths)
        with self.lock:
            if paths:
                self.hints[owner] = monotonic(), paths
            else:
                self.hints.pop(owner, None)
        self.cache.set_priority_folders(owner, paths)

    def retire(self, owner):
        with self.lock:
            self.owners.pop(owner, None)
        self.focus(owner, ())

    def _choose(self, jobs):
        if not jobs or self.owners and not any(self.owners.values()):
            return None
        now = monotonic()
        for job in jobs:
            self.served.setdefault(job['id'], now)
        # A waiting background receipt gets a turn even during continuous typing.
        oldest = min(jobs, key=lambda job: self.served[job['id']])
        if now-self.served[oldest['id']] >= 5:
            return oldest
        hints = [(stamp, paths) for stamp, paths in self.hints.values() if now-stamp >= .15]
        if hints:
            _, paths = max(hints, key=lambda item: item[0])
            for job in jobs:
                root = Path(job['root'])
                if any(root == path or path in root.parents or root in path.parents for path in paths):
                    return job
        return jobs[0]

    def select_job(self, jobs):
        with self.lock:
            chosen = self._choose(jobs)
            if chosen is not None:
                self.started[chosen['id']] = self.served[chosen['id']] = monotonic()
                # Existing-generation reconciliation is atomic, so cancellation
                # may roll back its work. Longer resumed turns prevent an active
                # foreground hint from making the same receipt restart forever.
                self.quanta[chosen['id']] = self.quanta.get(chosen['id'], .25) * 2
            live = {job['id'] for job in jobs}
            self.served = {key: value for key, value in self.served.items() if key in live}
            self.started = {key: value for key, value in self.started.items() if key in live}
            self.quanta = {key: value for key, value in self.quanta.items() if key in live}
            return chosen

    def should_yield(self, job):
        with self.lock:
            if self.owners and not any(self.owners.values()):
                return True
            if monotonic()-self.started.get(job['id'], monotonic()) < self.quanta.get(job['id'], .5):
                return False
        jobs = self.coordinator.active_jobs()
        with self.lock:
            chosen = self._choose(jobs)
            return chosen is not None and chosen['id'] != job['id']


def register(coordinator, policy):
    """Register an externally owned desktop runner; no worker is started here."""
    policy.coordinator = coordinator
    key = coordinator.cache.database
    with _lock:
        if key in _hosts:
            raise RuntimeError('This host already owns the directory index')
        _hosts[key] = coordinator, policy, None


def unregister(coordinator):
    with _lock:
        current = _hosts.get(coordinator.cache.database)
        if current is not None and current[0] is coordinator:
            del _hosts[coordinator.cache.database]


def coordinator_for(database):
    with _lock:
        current = _hosts.get(Path(database).absolute())
        return current[0] if current is not None else None


def cache_for(database=None):
    cache = DirectoryCache(database=database)
    cache.coordinator = coordinator_for(cache.database)
    return cache


def focus(database, owner, paths=()):
    """GUI-safe hint: callers must first admit an ordinary local provider."""
    with _lock:
        current = _hosts.get(Path(database).absolute())
    if current is not None:
        current[1].focus(owner, paths)


@contextmanager
def foreground(database, path):
    """Retire a request's scheduling hint without cancelling another subscriber."""
    owner = object()
    focus(database, owner, (path,))
    try:
        yield
    finally:
        focus(database, owner)


class _MobileCoordinator(IndexCoordinator):
    def submit(self, *args, **kwargs):
        identity = super().submit(*args, **kwargs)
        self.start_runner()
        return identity


class _Runner:
    def __init__(self, database):
        self.cache = DirectoryCache(database=database)
        self.policy = ScanPolicy(self.cache)
        self.coordinator = _MobileCoordinator(self.cache, select_job=self.policy.select_job,
                                              should_yield=self.policy.should_yield)
        self.coordinator.start_runner = self.start
        self.policy.coordinator = self.coordinator
        self.stop = Event()
        self.owners = set()
        self.worker = Thread(target=self.run, name='Logistics directory index', daemon=True)

    def start(self):
        from commonUtils.runtime.operations import OperationCancelled
        with _lock:
            if self.stop.is_set():
                raise OperationCancelled('Directory index host retired')
            if self.worker.ident is None:
                self.worker.start()

    def run(self):
        try:
            self.coordinator.run(self.stop.is_set)
        finally:
            self.cache.close()


class IndexLease:
    def __init__(self, runner):
        self.runner = runner
        self.owner = object()
        self._release = finalize(self, _release, runner, self.owner)

    @property
    def closed(self):
        return not self._release.alive

    def set_active(self, active):
        if not self.closed:
            self.runner.policy.active(self.owner, bool(active))

    def close(self):
        """Deny new work now; the retained runner exits at a safe checkpoint."""
        self._release()


def _release(runner, owner):
    with _lock:
        runner.policy.retire(owner)
        runner.owners.discard(owner)
        if not runner.owners:
            unregister(runner.coordinator)
            runner.stop.set()


def acquire(database):
    """Share one mobile runner across app scenes using the same private cache."""
    key = Path(database).absolute()
    with _lock:
        current = _hosts.get(key)
        if current is None:
            runner = _Runner(key)
            _hosts[key] = runner.coordinator, runner.policy, runner
        else:
            runner = current[2]
            if runner is None:
                raise RuntimeError('The desktop host already owns this directory index')
        lease = IndexLease(runner)
        runner.owners.add(lease.owner)
        runner.policy.active(lease.owner, True)
        return lease
