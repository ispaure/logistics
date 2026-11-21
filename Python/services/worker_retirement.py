"""Wait for an already scheduled mobile worker to retire."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

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
