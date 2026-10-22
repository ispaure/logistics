"""Captured mobile file commands and their owned worker lifecycle; no widgets."""
import asyncio
from dataclasses import dataclass
from threading import Event
from typing import Callable

from commonUtils.runtime.local_files import LocalFiles
from commonUtils.runtime.operations import MutationIncomplete, check_cancelled
from commonUtils.runtime.resource_provider import resource_path
from commonUtils.runtime.resource_mutations import (
    create_resource_folder, delete_resource, move_resource, rename_resource,
)
from features.rclone.mobile.storage_location import CollectionFiles
from features.rclone.localcrypt.mobile.resources import encrypted_storage


@dataclass(frozen=True)
class FileDestination:
    """Resolve a captured location without reading host fields in the worker."""
    root: object
    client: object
    location: object
    generation: object

    def resolve(self):
        if isinstance(self.location, LocalFiles):
            return self.location
        if self.location is None:
            return CollectionFiles(self.root)
        if getattr(self.client, 'generation', None) != self.generation:
            raise ValueError('Connection changed. Browse the destination again.')
        return encrypted_storage(self.root, self.client, self.location)


@dataclass(frozen=True)
class FileOperationRequest:
    kind: str
    provider: object
    path: str | None
    target: str = ''
    destination: FileDestination | None = None

    def execute(self, cancelled):
        check_cancelled(cancelled)
        if self.kind == 'new':
            part = resource_path(self.target)
            if not part or '/' in part or self.provider is None:
                raise ValueError('Browse a folder and enter one new folder name.')
            path = '/'.join(p for p in (self.path, part) if p)
            return create_resource_folder(self.provider, path, cancelled=cancelled)
        if self.provider is None or self.path is None:
            raise ValueError('Select a file first.')
        if self.kind == 'rename':
            part = resource_path(self.target)
            if not part or '/' in part:
                raise ValueError('Enter one new name.')
            target = '/'.join(p for p in (self.path.rpartition('/')[0], part) if p)
            return rename_resource(self.provider, self.path, target, cancelled=cancelled)
        if self.kind == 'delete':
            return delete_resource(self.provider, self.path, cancelled=cancelled)
        if self.kind == 'move':
            return move_resource(self.provider, self.path, self.destination.resolve(), self.target,
                                 cancelled=cancelled)
        raise ValueError('Unknown file operation: ' + self.kind)


@dataclass(frozen=True)
class FileOperationsHost:
    allowed: Callable
    begin: Callable
    current: Callable
    report: Callable
    finish: Callable


class FileOperations:
    """One operation at a time, sharing the application's existing busy/Cancel guard."""
    def __init__(self, host):
        self.host = host
        self.cancel_event = self.task = self.request = None

    def report_failure(self, view, error):
        if not self.host.current(view):
            return
        if isinstance(error, MutationIncomplete):
            self.host.report(view, str(error) + '\nRefresh before retrying.')
        else:
            self.host.report(view, 'Operation failed: ' + str(error)[:300]
                             + '\nRefresh to inspect any completed items.')

    async def run(self, capture, *, mutation=True):
        if self.cancel_event is not None or not self.host.allowed(mutation):
            return False
        cancel = self.cancel_event = Event()
        self.task = asyncio.current_task()
        view = None
        try:
            view = self.host.begin(cancel)
            # Capture inputs on the UI thread; execution never reads widgets.
            self.request = capture()
            work = self.request.execute if isinstance(self.request, FileOperationRequest) else self.request
            worker = asyncio.create_task(asyncio.to_thread(work, cancel.is_set))
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancel.set()
                # A cancelled coroutine does not stop its thread. Keep the busy
                # guard until the worker retires, including repeated task cancels.
                while not worker.done():
                    try:
                        await asyncio.shield(worker)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not worker.cancelled():
                    error = worker.exception()
                    if error is not None:
                        self.report_failure(view, error)
                raise
            if not self.host.current(view):
                return False
            self.host.report(view, 'Finished. Destination verified before removing the source.')
            return True
        except Exception as error:
            if view is None:
                raise
            self.report_failure(view, error)
            return False
        finally:
            try:
                if view is not None:
                    self.host.finish(view, cancel)
            finally:
                self.cancel_event = self.task = self.request = None
