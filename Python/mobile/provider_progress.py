"""One password-bound progress adapter for provider EPUB/comic/PDF/text readers."""

import asyncio
from copy import deepcopy

from services.documents.credential_state import CredentialState


class ProviderProgress:
    def __init__(self, owner, copies, reader, key):
        self.owner, self.pending, self.closed, self.task = owner, None, False, None
        app = getattr(owner, "app", owner)
        self.state = CredentialState(
            copies,
            key,
            app.private_root,
            kind=reader.kind,
            revision=getattr(reader.source, "expected", None),
            app=app,
        )
        self.restored = {}
        self.live = False

    def load(self):
        self.restored = self.state.load()
        return self.restored

    def restore(self, view):
        state = self.restored
        index = state.get("page", 0)
        if type(index) is int and 0 <= index < len(view.crypt_reader.labels):
            view.crypt_page.value = view.crypt_reader.labels[index]
        locations = state.get("locations", {})
        view._provider_epub_locations = (
            {
                str(k): v
                for k, v in locations.items()
                if isinstance(k, str) and type(v) is int and 0 <= v <= 16 * 1024 * 1024
            }
            if isinstance(locations, dict)
            else {}
        )
        view.crypt_bookmarks = {
            v
            for v in state.get("bookmarks", [])
            if type(v) is int and 0 <= v < len(view.crypt_reader.labels)
        }
        view.epub_session_bookmarks = {
            tuple(v)
            for v in state.get("epub_bookmarks", [])
            if isinstance(v, list)
            and len(v) == 2
            and all(type(x) is int and x >= 0 for x in v)
        }
        navigation = getattr(view.crypt_reader, "comic_navigation", None)
        if navigation is not None:
            navigation.requested_half = 1 if state.get("half") == 1 else 0

    def capture(self):
        owner = self.owner
        reader = getattr(owner, "crypt_reader", None)
        if self.closed or not self.live or reader is None:
            return
        value = getattr(owner.crypt_page, "value", None)
        if value not in reader.labels:
            return
        self.pending = dict(
            page=reader.labels.index(value),
            locations=deepcopy(getattr(owner, "_provider_epub_locations", {})),
            half=getattr(owner, "_provider_displayed_half", 0),
            bookmarks=sorted(getattr(owner, "crypt_bookmarks", set())),
            epub_bookmarks=sorted(getattr(owner, "epub_session_bookmarks", set())),
        )
        if self.task is None or self.task.done():
            app = getattr(owner, "app", owner)
            self.task = app.loop.create_task(self.write())

    async def write(self):
        await asyncio.sleep(0.4)
        while self.pending is not None and not self.closed:
            state, self.pending = self.pending, None
            try:
                await asyncio.to_thread(self.state.save, state)
            except (OSError, ValueError):
                pass  # Locked/passwordless credentials never publish weaker state.

    def close(self):
        self.capture()
        # The source must still be active for publication. Closing never schedules
        # a delayed write against a reader whose credential grant has retired.
        if self.pending is not None:
            try:
                self.state.save(self.pending)
            except (OSError, ValueError):
                pass
        self.closed = True
        self.pending = None
        if self.task is not None:
            self.task.cancel()
