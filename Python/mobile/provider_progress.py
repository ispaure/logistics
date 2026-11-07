"""Restore and checkpoint the last displayed location of a mobile file reader."""

import asyncio
from copy import deepcopy
from hashlib import sha256

from services.documents.mobile_reading import reading_capabilities

from services.documents.progress import ProgressStatus, document_identity, open_progress
from services.worker_retirement import drain_worker


# A standalone archive password authorizes viewing, not credential-history ZIP
# publication. Use an explicit memory namespace independent of reader instances.
PASSWORD_READER = object()


def archive_revision(archive, names):
    from json import dumps
    rows = []
    for name in sorted(set(names)):
        member = archive.getinfo(name)
        rows.append((name, member.CRC, member.file_size))
    return ('mobile-readable-archive', sha256(dumps(rows, ensure_ascii=True).encode()).hexdigest())


def provider_revision(copies, reader):
    source = reader.source
    if reading_capabilities(copies).private or getattr(reader, 'password', ''):
        # Existing protected checkpoints are bound to the provider revision.
        return getattr(source, 'expected', None)
    if getattr(reader, 'book', None) is not None or reader.kind in {'.cbz', '.zip'}:
        book = getattr(reader, 'book', None)
        names = book.spine if book is not None else getattr(reader, 'pages', ())
        try:
            with source.open_archive(source.path) as archive:
                return archive_revision(archive, names)
        except (OSError, ValueError, KeyError, AttributeError):
            return getattr(source, 'expected', None)
    if reader.editable:
        return ('mobile-text', sha256(reader.text.encode('utf-8')).hexdigest())
    data = getattr(reader, 'data', None)
    if isinstance(data, bytes) and (reader.kind == '.pdf' or getattr(reader, 'image_document', False)):
        # The renderer already reads these bytes. Keep a bounded sample so an
        # iOS container relocation does not reset the same PDF.
        mid = len(data) // 2
        sample = data[:65536] + data[max(0, mid - 32768):mid + 32768] + data[-65536:]
        return ('mobile-image' if getattr(reader, 'image_document', False) else 'mobile-pdf',
                len(data), sha256(sample).hexdigest())
    return getattr(source, 'expected', None)


_WRITE_ERRORS = {ProgressStatus.WRITE_FAILED, ProgressStatus.ERROR, ProgressStatus.LOCKED}


class ProgressWrites:
    """Debounce observations on the UI thread and drain each borrowed worker."""

    def __init__(self, owner, state):
        self.owner, self.state = owner, state
        self.closed = False
        self.pending = self.task = self.worker = None
        self.generation = 0
        self._wake = asyncio.Event()

    def available(self):
        return not self.closed and self.owner.active_host

    def notice(self, message):
        app = getattr(self.owner, 'app', self.owner)
        target = getattr(app, 'recovery_notice', None)
        if target is not None:
            target.text = message
        target = getattr(self.owner, 'book_status', None)
        if target is not None:
            target.text = message

    def report_load(self):
        status = self.state.load_status
        if self.state.locked_state:
            self.notice('Saved reader history is locked. Use Settings → Workspaces → Migrate protected reader history if the ZIP password changed.')
        elif status is ProgressStatus.SESSION_ONLY:
            self.notice('Reading progress for this source is kept until this app closes.')
        elif status is ProgressStatus.ERROR:
            self.notice('Saved reading progress could not be read.')

    def observe(self, value, *, bookmarks=False):
        if not self.available():
            return
        status = self.state.bookmark_status if bookmarks else self.state.load_status
        if status in {ProgressStatus.LOCKED, ProgressStatus.ERROR}:
            return
        observation = self.state.observe_bookmarks(value) if bookmarks else self.state.observe(value)
        self.queue(observation)

    def queue(self, observation):
        if observation is not None:
            self.pending = observation
            self.generation += 1
            self.schedule()

    def schedule(self, *, immediate=False):
        if self.pending is None or not self.available():
            return
        if immediate:
            self._wake.set()
        if self.task is None or self.task.done():
            if self.owner.loop.is_closed():
                return
            if not immediate:
                self._wake.clear()
            self.task = self.owner.loop.create_task(self.write())
        return self.task

    async def write(self, *, delay=True):
        if delay:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=.35)
            except asyncio.TimeoutError:
                pass
        while self.pending is not None and self.available():
            idle = getattr(self.owner, 'operation_idle', None)
            if idle is not None:
                await idle.wait()
            if self.pending is None or not self.available():
                return
            observation = self.pending
            worker = self.worker = asyncio.create_task(asyncio.to_thread(self.state.flush, observation))
            try:
                try:
                    status = await asyncio.shield(worker)
                except asyncio.CancelledError:
                    await drain_worker(worker)
                    raise
                except (OSError, ValueError):
                    status = ProgressStatus.WRITE_FAILED
                if status in _WRITE_ERRORS:
                    self.notice('Could not save reading progress. The latest position will be retried at the next checkpoint.')
                    if self.pending is observation:
                        return status
                if self.pending is observation:
                    self.pending = None
            finally:
                self.worker = None
                self.worker_finished()
        return getattr(self.state, 'write_status', None)

    def worker_finished(self):
        pass

    async def flush(self):
        task = self.schedule(immediate=True)
        if task is None:
            return
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await drain_worker(task)
            raise

    def checkpoint_sync(self):
        if self.pending is None:
            return
        loop = self.owner.loop
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if not loop.is_closed():
                status = loop.run_until_complete(self.flush())
                if status not in _WRITE_ERRORS:
                    return
        else:
            self.schedule(immediate=True)
        raise OSError('Finish saving reader progress before replacing this workspace.')

    def require_idle(self):
        if self.closed or self.worker is not None or (self.task is not None and not self.task.done()):
            raise OSError('Finish saving reader progress before replacing this workspace.')

    def retire(self):
        if self.closed:
            return
        self.require_idle()
        self.closed = True
        self.pending = None
        self.state.retire()

    def close(self):
        if self.closed:
            return
        if self.worker is not None:
            raise OSError('Reader progress is still using this document.')
        self.closed = True
        self.pending = None
        if self.task is not None and not self.task.done():
            self.task.cancel()
        self.state.retire()


class ProviderProgress(ProgressWrites):
    def __init__(self, owner, copies, reader, key, *, check=None):
        app = owner.app
        revision = provider_revision(copies, reader)
        provider = copies
        legacy = str(key)
        if getattr(reader, 'password', '') and not reading_capabilities(copies).private:
            provider = PASSWORD_READER
            key = repr(document_identity(copies, key, app=app))
        state = open_progress(provider, key, app.private_root, kind=reader.kind or 'text',
                              revision=revision, legacy_path=legacy, app=app, check=check or owner.document_access)
        super().__init__(owner, state)
        self.restored = {}
        self.reader = reader
        self.live = False
        self.last_location = None
        self.surface = self.surface_task = None
        self.surface_ready = False
        self.image_viewport = None

    def load(self):
        self.restored = self.state.load()
        if getattr(self.reader, 'image_document', False):
            from features.images.mobile.progress import ImageViewport
            self.image_viewport = ImageViewport(self.state, self.restored)
        return self.restored

    def replace_with(self, successor):
        """Carry a verified in-app edit's last visible location to its new revision."""
        successor.live = True
        owner = self.owner
        if (self.state.revision == successor.state.revision
                and self.state.identity == successor.state.identity
                and self.state.mode == successor.state.mode):
            successor.close()
            self.reader = successor.reader
            return self
        value = self.last_location
        same_generation = self.state.generation == successor.state.generation
        self.close()
        owner._provider_progress = successor
        if same_generation and value is not None:
            successor.last_location = value
            successor.observe(value)
            if self.state.identity == successor.state.identity and (
                    owner.crypt_bookmarks or owner.epub_session_bookmarks):
                successor.bookmarks_changed()
        return successor

    def page(self):
        state, reader = self.restored, self.reader
        resource = state.get('resource')
        names = reader.book.spine if getattr(reader, 'book', None) is not None else getattr(reader, 'pages', ())
        index = state.get('page', 0)
        valid_index = type(index) is int and 0 <= index < len(reader.labels)
        if isinstance(resource, str) and resource in names:
            return index if valid_index and names[index] == resource else names.index(resource)
        return index if valid_index else 0

    def restore(self, view):
        state = self.restored
        index = self.page()
        view.crypt_page.value = self.reader.labels[index]
        locations = state.get('locations', {})
        view._provider_epub_locations = {
            k: v for k, v in locations.items()
            if isinstance(k, str) and type(v) is int and 0 <= v <= 16 * 1024 * 1024
        } if isinstance(locations, dict) else {}
        resource, offset = state.get('resource'), state.get('offset')
        if self.reader.book is not None and resource in self.reader.book.spine and type(offset) is int:
            view._provider_epub_locations[resource] = max(0, min(offset, 16 * 1024 * 1024))
        bookmarks = state.get('bookmarks')
        epub_bookmarks = state.get('epub_bookmarks')
        view.crypt_bookmarks = {
            v for v in (bookmarks if isinstance(bookmarks, list) else ()) if type(v) is int and 0 <= v < len(self.reader.labels)
        }
        view.epub_session_bookmarks = {
            tuple(v) for v in (epub_bookmarks if isinstance(epub_bookmarks, list) else ())
            if isinstance(v, list) and len(v) == 2 and type(v[0]) is int and 0 <= v[0] < len(self.reader.labels)
            and type(v[1]) is int and 0 <= v[1] <= 16 * 1024 * 1024
        }

    def available(self):
        if not self.live or not super().available():
            return False
        owner = self.owner
        if owner.__dict__.get('_provider_progress') is not self or owner.crypt_reader is not self.reader:
            return False
        return owner.provider_document().capture()()

    def visible(self):
        owner = self.owner
        return self.available() and owner.manager.active is owner and owner.app.visible_reader() == owner.session.id

    def worker_finished(self):
        owner = self.owner
        manager = owner.manager
        if owner.active_host and owner.app.private_sessions is manager and not manager.terminal:
            manager.revoke_stale()

    def snapshot(self):
        return deepcopy(self.last_location)

    def _position(self, value, *, initial=False):
        if not self.visible() or value == self.last_location:
            return
        self.last_location = value
        if not initial:
            self.observe(value)

    def capture(self, *, initial=False):
        if not self.visible():
            return
        owner, reader = self.owner, self.reader
        index = getattr(owner, '_provider_displayed_index', None)
        if index is None or getattr(owner, 'page_suspended', False):
            return
        if reader.editable or reader.kind == '.pdf' or self.image_viewport is not None:
            if reader.kind == '.pdf' and not initial and (self.last_location or {}).get('page') != index:
                self._position(dict(page=index))
            self.watch_surface(initial=initial)
            return
        value = dict(page=index)
        if reader.book is not None:
            panel = getattr(owner, 'provider_epub_view', None)
            if panel is None or not getattr(panel, 'position_ready', True):
                return
            value.update(resource=reader.book.spine[index], offset=panel.offset)
        elif reader.kind in {'.cbz', '.zip'}:
            value.update(resource=reader.pages[index], half=owner._provider_displayed_half)
        self._position(value, initial=initial)

    def bookmarks_changed(self):
        owner = self.owner
        self.observe(dict(bookmarks=sorted(owner.crypt_bookmarks),
                          epub_bookmarks=[list(v) for v in sorted(owner.epub_session_bookmarks)]),
                     bookmarks=True)

    def surface_value(self):
        owner = self.owner
        if self.reader.kind == '.pdf':
            return owner.crypt_image, 'viewport'
        if self.image_viewport is not None:
            return owner.crypt_image, 'image'
        for control, mode in ((getattr(owner, 'crypt_preview', None), 'preview'),
                              (getattr(getattr(owner, 'crypt_formatted', None), 'view', None), 'formatted'),
                              (owner.crypt_text, 'source')):
            if control is not None and control in owner.crypt_content.children:
                return control, mode
        return None, None

    def watch_surface(self, *, initial=False):
        widget, mode = self.surface_value()
        if widget is None:
            self.stop_surface()
            self.surface_task = self.owner.loop.create_task(self._wait_for_surface(initial=initial))
            return
        index = self.owner._provider_displayed_index
        key = widget, mode, index
        if key == self.surface and self.surface_task is not None and not self.surface_task.done():
            return
        self.stop_surface()
        self.surface = key
        self.surface_task = self.owner.loop.create_task(self._watch_surface(key, initial=initial))

    async def _wait_for_surface(self, *, initial):
        while self.visible():
            await asyncio.sleep(.05)
            widget, _ = self.surface_value()
            if self.visible() and widget is not None:
                self.surface_task = None
                self.watch_surface(initial=initial)
                return

    async def _watch_surface(self, key, *, initial):
        from commonUtils.ui.native.draw_ready import wait_for_draw
        from .reader_lifecycle import restore_reading_scroll
        widget, mode, index = key

        def current():
            return (self.surface == key and self.visible()
                    and self.surface_value() == (widget, mode)
                    and self.owner._provider_displayed_index == index)

        if mode == 'preview':
            while current() and not getattr(self.owner.crypt_preview_search, 'ready', False):
                await asyncio.sleep(.05)
        elif mode == 'formatted':
            formatted = self.owner.crypt_formatted
            from commonUtils.ui.native.text_size import native_backend
            if not native_backend(widget).startswith(('toga_iOS.', 'toga_android.')):
                return
            while current():
                ready = await widget.evaluate_javascript('!!document.getElementById("document")')
                if ready is True or ready == 'true':
                    break
                await asyncio.sleep(.05)
        if not current():
            return
        from commonUtils.ui.native.text_size import native_backend
        target = self.owner.crypt_content
        if native_backend(target).startswith(('toga_iOS.', 'toga_android.')):
            while current() and not await wait_for_draw(target):
                pass
        else:
            await wait_for_draw(target)
        if not current():
            return
        saved = self.last_location or self.restored
        if mode == 'image':
            self.image_viewport.restore(widget)
        elif mode == 'viewport':
            if saved.get('page') == index:
                viewport = saved.get('viewport')
                if saved.get('spread') != list(self.reader.pdf_navigation.indices) and isinstance(viewport, dict):
                    viewport = {'zoom': viewport.get('zoom')}
                widget.restore_viewport(viewport)
        elif mode == 'formatted':
            if saved.get('mode') == mode:
                scroll = saved.get('scroll')
                if isinstance(scroll, list) and len(scroll) == 2 and type(scroll[1]) in (int, float) and 0 <= scroll[1] <= 1:
                    await widget.evaluate_javascript(
                        '(()=>{const root=document.getElementById("document");'
                        'if(root)root.scrollTop=(root.scrollHeight-root.clientHeight)*' + str(scroll[1]) + '})()')
        elif saved.get('mode') == mode:
            await restore_reading_scroll(widget, saved.get('scroll'), current,
                                         source_anchor=saved.get('anchor') if mode == 'source' else None)
        if not current():
            return
        if mode == 'formatted':
            await self.sample_formatted(widget, current, initial=initial)
            while current():
                await asyncio.sleep(.25)
                if current():
                    await self.sample_formatted(widget, current)
            return
        self.surface_ready = True
        self.sample_surface(initial=initial)
        while current():
            await asyncio.sleep(.2)
            if current():
                self.sample_surface()

    def sample_surface(self, *, initial=False):
        if self.surface is None or not self.visible():
            return
        from .reader_lifecycle import normalized_scroll, source_scroll_anchor
        widget, mode, index = self.surface
        if self.surface_value() != (widget, mode) or self.owner._provider_displayed_index != index:
            return
        if not self.surface_ready:
            # An explicit close can race the first layout acknowledgement.
            # A mounted, scrolled surface with no restore pending is observable.
            if self.restored or mode not in {'source', 'preview'}:
                return
            if mode == 'preview' and not getattr(self.owner.crypt_preview_search, 'ready', False):
                return
        if mode == 'image':
            if not initial:
                self.queue(self.image_viewport.observe(widget))
            return
        if mode == 'viewport':
            value = dict(page=index)
            viewport = widget.reading_viewport()
            if viewport is not None:
                value.update(viewport=viewport, spread=list(self.reader.pdf_navigation.indices))
        else:
            scroll = normalized_scroll(widget)
            if scroll is None or (not self.surface_ready and not any(scroll)):
                return
            if (self.last_location is not None and self.last_location.get('mode') == mode
                    and self.last_location.get('scroll') == scroll):
                return
            value = dict(page=0, mode=mode, scroll=scroll)
            if mode == 'source':
                anchor = source_scroll_anchor(widget)
                if anchor is not None:
                    value['anchor'] = anchor
            if initial and not self.restored and any(scroll):
                initial = False
        self._position(value, initial=initial)

    async def sample_formatted(self, widget, current, *, initial=False):
        raw = await widget.evaluate_javascript(
            '(()=>{const root=document.getElementById("document");'
            'return root ? root.scrollTop/Math.max(1,root.scrollHeight-root.clientHeight) : -1})()')
        try:
            fraction = float(raw)
        except (ValueError, TypeError):
            return
        if current() and 0 <= fraction <= 1:
            self._position(dict(page=0, mode='formatted', scroll=[0, round(fraction, 5)]), initial=initial)

    def stop_surface(self):
        self.surface = None
        self.surface_ready = False
        if self.surface_task is not None:
            self.surface_task.cancel()
            self.surface_task = None

    async def prepare_replacement(self):
        self.sample_surface()
        generation = self.generation
        status = await self.flush()
        if status in _WRITE_ERRORS:
            raise OSError('Could not preserve private reader progress.')
        if generation != self.generation:
            raise OSError('Reader progress changed during replacement.')

    def checkpoint_replacement(self):
        self.sample_surface()
        self.checkpoint_sync()

    def retire(self):
        super().retire()
        self.stop_surface()

    def close(self):
        super().close()
        self.stop_surface()
