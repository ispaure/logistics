"""Async/mobile transport scheduling over the shared generation/session contract."""
import asyncio
from time import monotonic


class MobileGenerationTransport:
    def __init__(self, client, session, *, current):
        self.client, self.session, self.current = client, session, current
        self.task = None
        self.pending = []
        self.alive = True

    def start(self, profile, token, payload):
        loop = asyncio.get_running_loop()
        response = self.session.response_token
        def accept(text):
            if self.alive and self.current() and self.session.accepts_response(response):
                self.pending.append(text)
        def fragment(text):
            loop.call_soon_threadsafe(accept, text)
        self.task = loop.create_task(asyncio.to_thread(self.client.stream, payload, fragment))

    async def drain(self, *, changed, checkpoint):
        response = self.session.response_token
        saved_at = monotonic()
        while not self.task.done() or self.pending:
            if self.pending:
                text = ''.join(self.pending)
                self.pending.clear()
                if self.current() and self.session.append_delta(text, token=response):
                    changed()
                    if monotonic() - saved_at > .5:
                        if not checkpoint():
                            self.client.cancel()
                        saved_at = monotonic()
            await asyncio.sleep(.05)
        return await self.task

    async def retire(self):
        self.alive = False
        self.client.cancel()
        if self.task is not None:
            await asyncio.gather(self.task, return_exceptions=True)
        self.pending.clear()
