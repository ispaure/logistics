"""Workspaces discovery tasks and cache, independent of the folder widgets."""
import asyncio
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

from .folder_hub import discover_folder_choices


@dataclass(frozen=True)
class FolderDiscoveryHost:
    """UI-thread capabilities; only the detached snapshot reaches a worker."""
    loop: object
    active: Callable
    stamp: Callable
    snapshot: Callable
    publish: Callable
    error: Callable


class FolderDiscovery:
    def __init__(self, host):
        self.host = host
        self.task = None
        self.cache = {}
        self.cache_stamp = None
        self.epoch = 0
        self.refresh_again = False

    def discover_now(self):
        """Preserve synchronous discovery for dummy/desktop host callers."""
        return discover_folder_choices(self.host.snapshot())

    def cached_choices(self):
        if self.cache_stamp == self.host.stamp():
            return deepcopy(self.cache)
        self.cache = {}
        self.cache_stamp = None
        # Never show a previous connection's names while its replacement loads.
        return {'All files': dict(source='Local', kind='local', value='',
                                  name='Browse All Files', copies=[], browser_root=True)}

    def request(self):
        """Share one task; requests arriving during a scan coalesce into a rescan."""
        self.refresh_again = True
        if self.task is None or self.task.done():
            self.task = self.host.loop.create_task(self._scan())
        return self.task

    def invalidate(self):
        """Retire in-flight results immediately, even before credential teardown."""
        self.epoch += 1
        self.refresh_again = False
        self.cache = {}
        self.cache_stamp = None

    def _retired(self, epoch):
        return not self.host.active() or epoch != self.epoch

    async def _scan(self):
        while self.host.active() and self.refresh_again:
            self.refresh_again = False
            epoch, stamp = self.epoch, self.host.stamp()
            try:
                snapshot = self.host.snapshot()
                result = await asyncio.to_thread(discover_folder_choices, snapshot)
            except (OSError, ValueError, IndexError, KeyError) as error:
                if self._retired(epoch):
                    if self.host.active() and self.refresh_again:
                        continue
                    return None
                if stamp != self.host.stamp() or self.refresh_again:
                    self.refresh_again = True
                    continue
                self.host.error(str(error))
                return None
            if self._retired(epoch):
                if self.host.active() and self.refresh_again:
                    continue
                return None
            if stamp != self.host.stamp() or self.refresh_again:
                self.refresh_again = True
                continue
            self.cache, self.cache_stamp = result.choices, stamp
            self.host.publish(result)
            return result.choices
        return None
