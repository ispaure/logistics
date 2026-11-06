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
        self.worker = None
        self.generation = 0

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

    def available(self):
        owner = self.owner
        app = getattr(owner, 'app', owner)
        document = owner.__dict__.get('_provider_document')
        manager = getattr(owner, 'manager', None)
        return (not self.closed and self.live and getattr(app, 'active_host', True)
                and not getattr(document, 'terminal', False) and not getattr(manager, 'terminal', False))

    def snapshot(self):
        owner = self.owner
        reader = getattr(owner, "crypt_reader", None)
        if not self.available() or reader is None:
            return
        value = getattr(owner.crypt_page, "value", None)
        if value not in reader.labels:
            return
        return dict(
            page=reader.labels.index(value),
            locations=deepcopy(getattr(owner, "_provider_epub_locations", {})),
            half=getattr(owner, "_provider_displayed_half", 0),
            bookmarks=sorted(getattr(owner, "crypt_bookmarks", set())),
            epub_bookmarks=sorted(getattr(owner, "epub_session_bookmarks", set())),
        )
    def capture(self):
        state = self.snapshot()
        if state is None:
            return
        self.pending = state
        self.generation += 1
        if self.task is None or self.task.done():
            app = getattr(self.owner, "app", self.owner)
            self.task = app.loop.create_task(self.write())

    def require_idle(self):
        if self.closed or self.worker is not None or (self.task is not None and not self.task.done()):
            raise OSError('Finish saving reader progress before replacing this workspace.')

    async def prepare_replacement(self):
        """Persist the final observed position with its source still owned/live.

        Existing queued/writing progress conservatively vetoes replacement. This
        prevents an older worker from overwriting this final capture.
        """
        self.require_idle()
        state = self.snapshot()
        if state is None:
            return
        self.pending = state
        self.generation += 1
        generation = self.generation
        app = getattr(self.owner, 'app', self.owner)
        task = self.task = app.loop.create_task(self.write(delay=False, strict=True))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            from services.worker_retirement import drain_worker
            await drain_worker(task)
            raise
        if self.generation != generation or self.snapshot() != state:
            raise OSError('Reader progress changed during replacement.')

    def checkpoint_replacement(self):
        """Synchronous route: no previous worker may overlap this checkpoint."""
        self.require_idle()
        state = self.snapshot()
        if state is not None:
            self.state.save(state)
            self.generation += 1
            self.pending = None
            if self.snapshot() != state:
                raise OSError('Reader progress changed during replacement.')

    async def write(self, *, delay=True, strict=False):
        if not self.available():
            return
        if delay:
            await asyncio.sleep(0.4)
        while self.pending is not None and self.available():
            idle = getattr(self.owner, 'operation_idle', None)
            if idle is not None:
                await idle.wait()
            if not self.available() or self.pending is None:
                return
            state, self.pending = self.pending, None
            worker = self.worker = asyncio.create_task(asyncio.to_thread(self.state.save, state))
            try:
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    from services.worker_retirement import drain_worker
                    await drain_worker(worker)
                    raise
            except (OSError, ValueError):
                if strict:
                    raise
                # Locked/passwordless credentials never publish weaker state.
            finally:
                self.worker = None
                owner = self.owner
                manager = getattr(owner, 'manager', None)
                app = getattr(owner, 'app', owner)
                if (manager is not None and getattr(app, 'active_host', False)
                        and getattr(app, 'private_sessions', None) is manager
                        and manager.controllers.get(owner.session.id) is owner and not manager.terminal):
                    manager.revoke_stale()

    def retire(self):
        """Terminal replacement cleanup only; preparation owns persistence."""
        if self.closed:
            return
        self.require_idle()
        self.closed = True
        self.pending = None

    def close(self):
        if self.worker is not None:
            raise OSError('Reader progress is still using this document.')
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
