"""Captured mobile file commands and their owned worker lifecycle; no widgets."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

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
from services.documents.locations import CollectionFiles
from features.rclone.localcrypt.mobile.resources import encrypted_storage
from services.worker_retirement import drain_worker


@dataclass(frozen=True)
class FileDestination:
    """Resolve a captured location without reading host fields in the worker."""
    root: object
    client: object
    location: object
    generation: object

    def resolve(self):
        if isinstance(self.location, LocalFiles):
            if self.location.private and getattr(self.client, 'generation', None) != self.generation:
                raise ValueError('Connection changed. Browse the destination again.')
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
    expected_revision: object = None
    expected_parent_revision: object = None

    def execute(self, cancelled, *, destination=None, progress=None):
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
        if self.kind == 'copy':
            from services.documents.mutations import copy_document_sibling
            return copy_document_sibling(self.provider, self.path, cancelled=cancelled)
        if self.kind == 'delete':
            from commonUtils.persistence.publication import mutation_lock
            with mutation_lock:
                if (self.expected_revision is not None
                        and self.provider.entry(self.path)['revision'] != self.expected_revision):
                    raise ValueError('The selected item changed. Review it before deleting.')
                return delete_resource(self.provider, self.path, cancelled=cancelled)
        if self.kind == 'move':
            return move_resource(self.provider, self.path, destination or self.destination.resolve(), self.target,
                                 cancelled=cancelled, progress=progress)
        raise ValueError('Unknown file operation: ' + self.kind)


@dataclass(frozen=True)
class FileSelectionMove:
    provider: object
    entries: tuple
    kind: str = 'move-selection'
    title: str = 'Move selected items'
    primary: str = 'Move here'


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
        await drain_worker(worker)
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
        try:
            view = self.host.begin(cancel)
            # Capture inputs on the UI thread; execution never reads widgets.
            self.request = capture()
            result = await self._execute(self.request, mutation, view, cancel)
            if not self.host.current(view):
                return False
            self.host.report(view, getattr(result, 'notice', '') or
                             'Finished. Destination verified before removing the source.')
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

    async def _execute(self, request, mutation, view, cancel, *, completed=lambda: None):
        import inspect

        prepared = self.host.prepare(request, mutation)
        plan = await prepared if inspect.isawaitable(prepared) else prepared
        try:
            command = plan or request
            work = command.execute if plan or isinstance(command, FileOperationRequest) else command

            def apply(result):
                completed()
                if plan:
                    plan.apply(result)

            return await retiring_work(work, cancel, completed=apply,
                                       failed=lambda error: self.report_failure(view, error))
        finally:
            if plan:
                plan.release()

    async def move_selection(self, requests, completed):
        from commonUtils.runtime.operations import OperationCancelled

        if self.cancel_event is not None or not self.host.allowed(False):
            return None
        cancel = self.cancel_event = Event()
        self.task = asyncio.current_task()
        view = None
        failures = []
        notice = ''
        try:
            view = self.host.begin(cancel)
            for index, request in enumerate(requests, 1):
                if cancel.is_set() or not self.host.current(view):
                    break
                self.request = request
                self.host.report(view, f'Moving item {index} of {len(requests)}…')
                try:
                    result = await self._execute(request, True, view, cancel, completed=lambda: completed(request))
                    notice = result.notice or notice
                except OperationCancelled:
                    break
                except (OSError, ValueError) as error:
                    failures.append(f'{request.path.rpartition("/")[2]}: {error}')
            return failures, notice, cancel.is_set() or not self.host.current(view)
        finally:
            try:
                if view is not None:
                    self.host.finish(view, cancel)
            finally:
                self.cancel_event = self.task = self.request = None
