"""Transfer execution state, worker retirement and progress delivery without widgets."""
import asyncio
from dataclasses import dataclass
from threading import Event, Lock
from typing import Protocol
from .models import TransferOutcome


def coalesced_progress(loop, publish, *, interval=1.0):
    """Keep the latest snapshot and leave UI time between native renders."""
    lock = Lock()
    latest, scheduled = None, False
    next_render = 0

    def schedule():
        delay = next_render - loop.time()
        if delay > 0:
            loop.call_later(delay, drain)
        else:
            drain()

    def drain():
        nonlocal latest, scheduled, next_render
        with lock:
            values, latest = latest, None
        # Keep admission while rendering, without holding the worker lock. A
        # slow render must not queue an immediate successor and starve input.
        try:
            publish(values)
        finally:
            next_render = loop.time() + interval
            with lock:
                pending = latest is not None
                scheduled = pending
            if pending:
                loop.call_later(interval, drain)

    def progress(**values):
        nonlocal latest, scheduled
        with lock:
            latest = values
            if scheduled:
                return
            scheduled = True
        loop.call_soon_threadsafe(schedule)

    return progress


async def wait_for_transfer(worker, cancel, client):
    """Cancellation keeps ownership until the native writer has retired."""
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel.set()
        try:
            client.cancel()
        except (OSError, ValueError):
            pass
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        # Consume a late failure without replacing the caller's cancellation.
        try:
            worker.result()
        except BaseException:
            pass
        raise


@dataclass
class TransferState:
    """Retained execution state shared with the presentation adapter.

    busy lasts through worker retirement; complete means a verified outcome.
    epoch rejects queued progress from older runs. notification can remain visible
    after execution ends until the user dismisses it or its timeout expires.
    """
    busy: bool = False
    notification: bool = False
    complete: bool = False
    percentage: float | None = None
    epoch: int = 0
    message: str = 'No transfer is running.'
    endpoints: tuple[str, str] | None = None
    cancel: Event | None = None


class TransferPresentation(Protocol):
    async def ready(self) -> bool: ...
    def connection(self) -> tuple: ...
    def current(self, client, generation: int) -> bool: ...
    def unavailable(self) -> None: ...
    def started(self) -> None: ...
    def progress(self, epoch: int, values: dict) -> None: ...
    def finished(self) -> None: ...


def completion_message(operation, result):
    """Format one validated outcome, accepting legacy programmatic worker results."""
    outcome = TransferOutcome.from_result(operation, result)
    if outcome.operation == 'download':
        return 'Download complete. The selected item is saved locally.'
    if outcome.operation == 'push':
        return f'Push sync verified: {outcome.files} file(s) sent. Destination-only entries were removed.'
    return ('Files changed during the operation; inspect the local destination.'
            if outcome.status == 'conflict' else 'Pull sync complete. The local folder now matches the remote.')


class TransferExecution:
    def __init__(self, state: TransferState, view: TransferPresentation):
        self.state, self.view = state, view

    async def run(self, work, operation, *, source=None, destination=None):
        state, view = self.state, self.view
        if state.busy:
            return False
        if not await view.ready():
            view.unavailable()
            return False
        # Two callers can both have awaited credential restoration. Admit only
        # one native writer after that wait, before yielding to its worker.
        if state.busy:
            return False
        client, generation = view.connection()
        state.endpoints = (source, destination) if source is not None and destination is not None else None
        state.busy, state.notification, state.complete = True, True, False
        state.percentage = None
        state.cancel = cancel = Event()
        state.message = 'Preparing transfer…'
        state.epoch += 1
        epoch = state.epoch
        progress = coalesced_progress(asyncio.get_running_loop(), lambda values: view.progress(epoch, values))
        try:
            view.started()
            worker = asyncio.create_task(asyncio.to_thread(work, client, cancel.is_set, progress))
            result = await wait_for_transfer(worker, cancel, client)
            if not view.current(client, generation):
                state.message = 'Sync stopped because the connection changed; completed destination changes remain.'
                return False
            outcome = TransferOutcome.from_result(operation, result)
            complete = outcome.status != 'conflict'
            prefix = '100% · ' if complete else ''
            message = prefix + completion_message(operation, outcome)
            state.message = message
            state.complete = complete
            return complete
        except asyncio.CancelledError:
            state.message = 'Sync cancelled; completed destination changes remain.'
            raise
        except Exception as error:
            state.message = 'Sync stopped; completed destination changes remain. ' + str(error)[:350]
            return False
        finally:
            state.epoch += 1
            state.cancel = None
            state.busy = False
            view.finished()


@dataclass(frozen=True)
class TransferProgress:
    message: str
    percentage: float | None
    done: int
    total: int


def transfer_progress(values):
    phase, files = values['phase'], values['files']
    done, total = values['done'], values['total']
    total_files = values.get('total_files', 0)
    # Rclone discovers work while syncing. Prefer bytes; zero-byte files
    # can still supply a useful file-based total. Completion is verified
    # separately, so keep live progress below 100%.
    numerator, denominator = (done, total) if total > 0 else (files, total_files)
    percentage = min(99, max(0, 100 * numerator / denominator)) if denominator > 0 else None
    phase = {'Discovering / checking files': 'Finding and comparing files…',
             'Checking / finishing sync': 'Finishing and checking the destination…',
             'Sync complete; verifying local copy': 'Verifying the local copy…',
             'Transferring': 'Copying files…'}.get(phase, phase)
    message = f'{phase} · Files copied: {files:,}'
    if total_files > 0:
        message += f' of {total_files:,} found so far'
    if percentage is not None:
        message += f' · {percentage:.0f}% of known work'
    if values.get('attempt', 0) > 1 or values.get('retrying'):
        state = 'Retrying' if values.get('retrying') else 'Attempt'
        message += f' · {state} {values["attempt"]}/{values["max_attempts"]}'
    if values.get('active', 0):
        message += f' · Copying now: {values["active"]:,} files'
    if values.get('listed', 0) or values.get('checks', 0):
        message += f' · Files found: {values.get("listed", 0):,} · Files compared: {values.get("checks", 0):,}'
    if total > 0:
        message += f' · {done / 1_000_000:,.2f} / {total / 1_000_000:,.2f} MB (known so far)'
    elif done > 0:
        message += f' · {done / 1_000_000:,.2f} MB transferred'
    return TransferProgress(message, percentage, done, total)
