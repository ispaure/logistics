"""Retain worker-owned resources until asynchronous preparation actually ends."""
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
