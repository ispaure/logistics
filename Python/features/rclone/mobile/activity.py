"""UI-loop lifetime of nested remote progress, independent of widgets and I/O."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol


class ActivityPresentation(Protocol):
    def start(self) -> None: ...
    def show(self, message: str) -> None: ...
    def stop(self) -> None: ...


@dataclass(eq=False)
class _Activity:
    stage: str
    started: float
    active: bool = True


class RemoteActivity:
    """One timer per controller; newest active request owns visible status.

    Workers receive only a thread-safe progress callback. Retiring a request
    invalidates that callback before restoring the previous visible request.
    """
    def __init__(self, view: ActivityPresentation, *, interval=1):
        self.view = view
        self.interval = interval
        self._activities = []
        self._timer = None

    def _render(self, loop):
        if self._activities:
            current = self._activities[-1]
            elapsed = int(loop.time() - current.started)
            self.view.show(f'{current.stage} · {elapsed}s')

    async def _tick(self, loop):
        while True:
            await asyncio.sleep(self.interval)
            self._render(loop)

    @asynccontextmanager
    async def track(self, stage):
        loop = asyncio.get_running_loop()
        current = _Activity(stage, loop.time())

        def update(message):
            if current.active:
                current.stage, current.started = message, loop.time()
                self._render(loop)

        def progress(message):
            if current.active and not loop.is_closed():
                loop.call_soon_threadsafe(update, message)

        self._activities.append(current)
        try:
            if self._timer is None:
                self.view.start()
                self._timer = asyncio.create_task(self._tick(loop))
            self._render(loop)
            # Allow native status/spinner drawing before the caller starts work.
            await asyncio.sleep(0)
            yield progress
        finally:
            current.active = False
            self._activities.remove(current)
            if self._activities:
                self._render(loop)
            else:
                timer, self._timer = self._timer, None
                if timer is not None:
                    timer.cancel()
                try:
                    # Stop before yielding: a new request can start while the
                    # old timer retires and must not have its bar stopped later.
                    self.view.stop()
                finally:
                    if timer is not None:
                        try:
                            await timer
                        except asyncio.CancelledError:
                            pass
