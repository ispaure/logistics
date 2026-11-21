"""Retain worker-owned resources until asynchronous preparation actually ends."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio


async def read_prepared(read):
    task = asyncio.create_task(asyncio.to_thread(read))
    try:
        return await asyncio.shield(task)
    except BaseException:
        def retire(finished):
            if not finished.cancelled() and finished.exception() is None:
                finished.result().close()
        task.add_done_callback(retire)
        raise
