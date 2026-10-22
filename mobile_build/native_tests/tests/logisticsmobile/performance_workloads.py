"""Synthetic performance fixtures; reports contain metrics, never document text."""
import asyncio
import inspect
import time
import tracemalloc


async def measure_operation(name, operation):
    """Measure elapsed time, event-loop delay and Python allocations separately."""
    delays = []
    running = True

    async def heartbeat():
        while running:
            started = time.perf_counter()
            await asyncio.sleep(.01)
            delays.append(max(0, time.perf_counter() - started - .01))

    task = asyncio.create_task(heartbeat())
    owned_trace = not tracemalloc.is_tracing()
    if owned_trace:
        tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()
    started = time.perf_counter()
    try:
        await asyncio.sleep(0)
        result = operation()
        if inspect.isawaitable(result):
            await result
        elapsed = time.perf_counter() - started
        # Give the heartbeat a chance to observe a blocked UI callback.
        await asyncio.sleep(.02)
        _, peak = tracemalloc.get_traced_memory()
        return dict(name=name, elapsed_ms=elapsed * 1000,
                    max_loop_delay_ms=max(delays, default=0) * 1000,
                    python_peak_bytes=max(0, peak - baseline))
    finally:
        running = False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if owned_trace:
            tracemalloc.stop()


async def measure_workloads(app):
    """Only call on a disposable QA host with isolated storage and no accounts."""
    from features.lm.domain import message
    from features.lm.mobile.presentation import transcript_entries
    from .fixtures import make_books

    samples = []
    app.show_documents(edit=True)
    def typing():
        app.editor.value = 'Synthetic typing fixture\n' * 1000
        for index in range(20):
            app.editor.value += str(index)
    samples.append(await measure_operation('typing-20-edits', typing))
    folder = app.private_root / 'LocalFiles' / 'Performance'
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(1000):
        (folder / f'fixture-{index:04}.txt').write_text('Synthetic fixture')
    async def browse():
        await app.show_files(local_root=True)
        await app.browser_file_location(('Local files', 'Performance'))
    samples.append(await measure_operation('folder-1000', browse))
    samples.append(await measure_operation('open-text',
        lambda: app.open_download(path=folder / 'fixture-0000.txt')))
    _, comic = make_books(folder)
    await app.open_download(path=comic)
    samples.append(await measure_operation('comic-next-page', app.next_book_page))
    async def streaming():
        previous = []
        for index in range(1, 21):
            data = [message('assistant', '**Synthetic response**\n\n' * (index * 100), status='streaming')]
            previous = transcript_entries(data, previous)
            await asyncio.sleep(.05)
    samples.append(await measure_operation('streaming-20-updates', streaming))
    return samples
