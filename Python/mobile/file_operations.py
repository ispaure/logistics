"""Captured mobile file commands and their owned worker lifecycle; no widgets."""
import asyncio
from dataclasses import dataclass
from threading import Event
from typing import Callable

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.operations import MutationIncomplete, check_cancelled
from commonUtils.runtime.resources.paths import resource_path
from commonUtils.runtime.resources.mutations import (
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
            if getattr(self.location, 'closed', False) and hasattr(self.location, 'reopen'):
                return self.location.reopen()
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
    plaintext_approved: bool = False

    def execute(self, cancelled, *, destination=None):
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
            return move_resource(self.provider, self.path, destination or self.destination.resolve(), self.target,
                                 cancelled=cancelled)
        raise ValueError('Unknown file operation: ' + self.kind)


@dataclass(frozen=True)
class FileOperationsHost:
    allowed: Callable
    begin: Callable
    current: Callable
    report: Callable
    finish: Callable
    prepare: Callable = lambda request, mutation: None


async def retiring_work(work, cancel, *, completed=lambda result: None, failed=lambda error: None):
    """Retire a mutation's thread and reconcile a committed result even on Cancel."""
    worker = asyncio.create_task(asyncio.to_thread(work, cancel.is_set))
    try:
        result = await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel.set()
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
                failed(error)
            else:
                completed(worker.result())
        raise
    completed(result)
    return result


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
        if self.cancel_event is not None or not self.host.allowed(False):
            return False
        cancel = self.cancel_event = Event()
        self.task = asyncio.current_task()
        view = None
        plan = None
        try:
            view = self.host.begin(cancel)
            # Capture inputs on the UI thread; execution never reads widgets.
            self.request = capture()
            import inspect
            prepared = self.host.prepare(self.request, mutation)
            plan = await prepared if inspect.isawaitable(prepared) else prepared
            command = plan or self.request
            work = command.execute if plan or isinstance(command, FileOperationRequest) else command
            await retiring_work(work, cancel, completed=plan.apply if plan else lambda result: None,
                                failed=lambda error: self.report_failure(view, error))
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
                    try:
                        if plan is not None:
                            plan.release()
                    finally:
                        self.host.finish(view, cancel)
            finally:
                self.cancel_event = self.task = self.request = None
