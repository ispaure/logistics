"""Wait for an already scheduled mobile worker to retire."""
import asyncio


async def drain_worker(worker):
    """Wait through repeated caller cancellation and retrieve any worker error.

    The caller owns cancellation signals, the worker's outcome, and re-raising
    its original cancellation.
    """
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if not worker.cancelled():
        worker.exception()
