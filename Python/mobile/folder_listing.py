"""Per-browser folder read ownership; presentation and navigation stay in hosts."""
import asyncio
from dataclasses import dataclass
from threading import Event


@dataclass
class ListingWork:
    cancel: Event
    context: object
    client: object
    credential_generation: object
    task: object = None


@dataclass(frozen=True)
class ListingRequest:
    work: ListingWork
    provider: object
    source: object
    folder: str
    location: tuple


class FolderListing:
    def __init__(self, *, active, context, location, credentials):
        self.active = active
        self.context = context
        self.location = location
        self.credentials = credentials
        self.work = None

    def invalidate(self):
        if self.work is not None:
            self.work.cancel.set()
        self.work = None

    def begin(self):
        self.invalidate()
        client, generation = self.credentials()
        self.work = ListingWork(Event(), self.context(), client, generation)
        return self.work

    def accepts(self, work, request=None, *, private=False):
        if (self.work is not work or work.cancel.is_set() or not self.active()
                or work.context != self.context()):
            return False
        if request is not None:
            if request.location != self.location():
                return False
            private = private or getattr(request.provider, 'private', False)
        if private:
            client, generation = self.credentials()
            if client is not work.client or generation != work.credential_generation:
                return False
        return True

    def capture(self, work, provider, folder, location, *, source=None):
        return ListingRequest(work, provider, source if source is not None else provider,
                              folder, location)

    async def read(self, request):
        work = request.work
        if not self.accepts(work, request):
            return None
        work.task = asyncio.current_task()
        try:
            rows = await asyncio.to_thread(request.source.list, request.folder,
                                           cancelled=work.cancel.is_set)
            return rows if self.accepts(work, request) else None
        except asyncio.CancelledError:
            work.cancel.set()
            raise
        except Exception:
            if not self.accepts(work, request):
                return None
            raise
        finally:
            work.task = None
