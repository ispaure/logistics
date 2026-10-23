"""Remote-listing state and request lifetime without application/widget access."""
import asyncio
from dataclasses import dataclass, field
from threading import Event
from typing import Protocol, ContextManager, AsyncContextManager, Callable

from features.rclone.remote_access import NativeRemoteLocation
from .service import native_service


@dataclass
class RemoteBrowserState:
    path: str = ''
    remote: str | None = None
    rows: dict = field(default_factory=dict)
    reading: bool = False
    resource: object | None = None


class RemoteBrowserPresentation(Protocol):
    def population_paused(self) -> ContextManager: ...
    def busy(self) -> bool: ...
    def selection(self) -> tuple[list[str], str | None]: ...
    def location(self, remote: str | None, folder: str) -> None: ...
    def status(self, message: str) -> None: ...
    def set_busy(self, value: bool) -> None: ...
    def labels(self, labels: list[str], selected: str | None = None) -> None: ...
    def activity(self, stage: str) -> AsyncContextManager[Callable[[str], None]]: ...
    def current(self, client, generation: int) -> bool: ...
    def has_listing(self) -> bool: ...
    def publish(self, resource, rows: list[dict], remote: str, folder: str) -> None: ...
    def record(self, remote: str, folder: str) -> None: ...
    def stop(self) -> None: ...


def _list_remote(client, location, folder, cancelled):
    resource = native_service(client).remotes.open(location)
    try:
        return resource, resource.list(folder, cancelled=cancelled.is_set)
    except BaseException:
        resource.close()
        raise


def _retire_listing(task):
    """Consume a cancelled caller's worker result and release late access."""
    try:
        resource, _ = task.result()
        resource.close()
    except BaseException:
        pass


class RemoteBrowserWorkflow:
    def __init__(self, state: RemoteBrowserState, view: RemoteBrowserPresentation):
        self.state, self.view = state, view

    async def browse(self, client, remote, folder, *, preserve_path=False):
        state, view = self.state, self.view
        with view.population_paused():
            if view.busy():
                return
            if client is None or not remote:
                view.status('Choose a remote first. Use Manage connections to load your remotes.')
                return False
            if not preserve_path and state.remote and remote != state.remote:
                folder = ''
                view.location(remote, folder)
            previous_rows = state.rows
            previous_remote, previous_path, previous_resource = state.remote, state.path, state.resource
            candidate = None
            published = False
            cancelled = Event()
            previous_labels, previous_selected = view.selection()
            generation = getattr(client, 'generation', 0)
            def restore_previous():
                if view.has_listing() and view.current(client, generation):
                    state.remote, state.path, state.resource = previous_remote, previous_path, previous_resource
                    view.location(previous_remote, previous_path)
                    state.rows = previous_rows
                    view.labels(previous_labels, previous_selected)
                else:
                    view.stop()
                    if state.resource is not None:
                        state.resource.close()
                    state.resource = None
                    state.rows = {}
                    view.labels([])
                    state.remote, state.path = None, ''
                    view.location(None, '')
            view.status(f'Opening {remote}:{folder}…')
            state.reading = True
            view.set_busy(True)
            state.rows = {}
            view.labels([])
            try:
                async with view.activity(f'Listing {remote}:{folder or "/"}') as progress:
                    task = asyncio.create_task(asyncio.to_thread(_list_remote, client,
                        NativeRemoteLocation(remote, generation=generation), folder, cancelled))
                    try:
                        candidate, rows = await asyncio.shield(task)
                    except asyncio.CancelledError:
                        cancelled.set()
                        task.add_done_callback(_retire_listing)
                        raise
                    progress(f'Displaying {len(rows)} items from {remote}:{folder or "/"}')
                    await asyncio.sleep(0)
                    if not view.current(client, generation):
                        raise ValueError('Credentials changed while browsing. Reopen the remote.')
                    state.rows = {f'{index + 1}. {"Folder" if row["directory"] else "File"}: {row["path"]}': row
                                  for index, row in enumerate(rows)}
                    view.labels(list(state.rows))
                    view.publish(candidate, rows, remote, folder)
                    state.remote, state.path, state.resource = remote, folder, candidate
                    candidate = None
                    published = True
                view.record(remote, folder)
                view.status('')
                return True
            except asyncio.CancelledError:
                if not published:
                    restore_previous()
                raise
            except Exception as error:
                if published:
                    view.status('Opened folder; navigation history failed: ' + str(error)[:300])
                    return True
                view.status('Browse failed: ' + str(error)[:300])
                restore_previous()
                return False
            finally:
                if candidate is not None:
                    candidate.close()
                view.set_busy(False)
                state.reading = False
