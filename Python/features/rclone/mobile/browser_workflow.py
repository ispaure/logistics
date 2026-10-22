"""Remote-listing state and request lifetime without application/widget access."""
import asyncio
from dataclasses import dataclass, field
from typing import Protocol, ContextManager, AsyncContextManager, Callable


@dataclass
class RemoteBrowserState:
    path: str = ''
    remote: str | None = None
    rows: dict = field(default_factory=dict)
    reading: bool = False


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
    def publish(self, rows: list[dict], remote: str, folder: str) -> None: ...
    def record(self, remote: str, folder: str) -> None: ...
    def stop(self) -> None: ...


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
            previous_labels, previous_selected = view.selection()
            generation = getattr(client, 'generation', 0)
            view.status(f'Opening {remote}:{folder}…')
            state.reading = True
            view.set_busy(True)
            state.rows = {}
            view.labels([])
            try:
                async with view.activity(f'Listing {remote}:{folder or "/"}') as progress:
                    rows = await asyncio.to_thread(client.entries, remote, folder)
                    progress(f'Displaying {len(rows)} items from {remote}:{folder or "/"}')
                    await asyncio.sleep(0)
                    if not view.current(client, generation):
                        raise ValueError('Credentials changed while browsing. Reopen the remote.')
                    state.rows = {f'{index + 1}. {"Folder" if row["directory"] else "File"}: {row["path"]}': row
                                  for index, row in enumerate(rows)}
                    view.labels(list(state.rows))
                    state.remote, state.path = remote, folder
                    view.publish(rows, remote, folder)
                view.record(remote, folder)
                view.status('')
                return True
            except Exception as error:
                view.status('Browse failed: ' + str(error)[:300])
                if view.has_listing() and view.current(client, generation):
                    view.location(state.remote, state.path)
                    state.rows = previous_rows
                    view.labels(previous_labels, previous_selected)
                else:
                    view.stop()
                    state.rows = {}
                    view.labels([])
                    state.remote, state.path = None, ''
                    view.location(None, '')
                return False
            finally:
                view.set_busy(False)
                state.reading = False
