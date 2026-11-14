"""Mobile Notes Library playback through the retained native speech session."""

import asyncio
from uuid import uuid4

from commonUtils.runtime.operations import OperationCancelled
from services.access_policy import speech_allowed

from ..playlist_queue import MAX_PREPARED, NeedsUnlock, PlaylistQueue, prepare_passage


def playlist_panel_type(read_aloud_panel):
    class PlaylistPanel(read_aloud_panel):
        def __init__(self, owner, app):
            self.playlist = owner
            self.private_metadata = owner.catalog.private
            super().__init__(loop=app.loop, source=None, on_range=owner.follow, close=owner.close, app=app,
                             valid=owner.valid, seek=owner.skip,
                             document_title=owner.document_title)
            self.session.on_exhausted = owner.exhausted

        def allows_background(self):
            return self.playlist.allows_media()

        def playback_allowed(self):
            return self.playlist.playback_allowed()

        def enforce_playlist_access(self):
            self.playlist.enforce_access()

        async def play(self, widget=None, **kwargs):
            await self.playlist.start()

        def pause_playback(self, *args, **kwargs):
            transition = self.playlist.in_transition
            self.playlist.invalidate_work()
            super().pause_playback(*args, **kwargs)
            if transition and self.playlist.waiting is None:
                self.playlist.waiting = transition
            self.playlist.flush()

        def resume_playback(self, *, explicit=True):
            if self.playlist.waiting is not None:
                if self.playlist.can_read() and (self.playback is None or
                        (self.playback.request_start() if explicit else self.playback.can_start())):
                    self.playlist.continue_waiting()
                return
            super().resume_playback(explicit=explicit)
            self.playlist.warm()

        def stop_playback(self, *args, **kwargs):
            self.playlist.invalidate_work()
            self.playlist.waiting = None
            self.playlist.flush()
            super().stop_playback(*args, **kwargs)

        def timer_expired(self):
            self.pause_playback()
            self.set_status('Timer finished · Play to start a new timer.')

        def state(self, state, message):
            super().state(state, message)
            if getattr(self.playlist, 'panel', None) is self:
                self.playlist.state_changed(state)

    return PlaylistPanel


class PlaylistSpeech:
    def __init__(self, owner, catalog, changed, *, app, panel_type, stop_markdown_speech,
                 prepare_view, highlight_view, clear_view):
        self.owner, self.catalog, self.changed, self.app = owner, catalog, changed, app
        self.panel_type = panel_type
        self.stop_markdown_speech = stop_markdown_speech
        self.prepare_view = prepare_view
        self.highlight_view = highlight_view
        self.clear_view = clear_view
        self.queue = PlaylistQueue(catalog)
        self.panel = None
        self.epoch = 0
        self.read_epoch = 0
        self.work = self.preload = self.checkpoint_task = None
        self.save_task = None
        self.pending_skips = []
        self.waiting = None
        self.in_transition = None
        self.initial = None
        self.resume_position = None
        self.snapshot = None
        self.spoken_line = ''
        self.caption_at = -1
        self.unsubscribe = catalog.subscribe(lambda: app.loop.call_soon_threadsafe(self.edited))

    @property
    def playlist_id(self):
        return self.queue.record.id if self.queue.record is not None else None

    @property
    def active_id(self):
        return self.queue.current.entry.id if self.queue.current is not None else None

    @property
    def unavailable(self):
        return self.queue.unavailable

    @property
    def state(self):
        return self.panel.session.state if self.panel is not None else 'stopped'

    def document_title(self):
        return self.queue.record.name if self.queue.record is not None else ''

    def privacy(self):
        return getattr(self.app, 'screen_privacy', None)

    def opted_in(self):
        privacy = self.privacy()
        protected = self.catalog.private or (privacy is not None and privacy.sensitive())
        key = 'session_speech_when_locked' if protected else 'playlist_speech_when_locked'
        return self.app.preferences.values.get(key) == 'true'

    def allows_media(self):
        return self.playback_allowed() and (self.can_read() or self.opted_in())

    def valid(self):
        return (self.panel is not None and getattr(self.app, 'active_host', True)
                and not self.owner.cancelled.is_set() and not self.catalog.revoked())

    def can_read(self):
        privacy = self.privacy()
        return (self.valid() and self.owner.valid()
                and (privacy is None or not (privacy.inactive or privacy.interrupted
                                             or privacy.captured or privacy.resume_locked)))

    def playback_allowed(self):
        if not self.valid():
            return False
        privacy = self.privacy()
        inactive = bool(privacy is not None and (privacy.inactive or privacy.interrupted))
        locked = bool(privacy is not None and privacy.resume_locked)
        captured = bool(privacy is not None and privacy.captured)
        return speech_allowed(protected=True, inactive=inactive, captured=captured, locked=locked,
                              continue_locked=self.opted_in())

    def enforce_access(self):
        if not self.can_read():
            self.read_epoch += 1
        if not self.valid():
            self.close()
        elif not self.playback_allowed():
            if self.state in ('speaking', 'paused') or self.in_transition is not None:
                self.panel.stop_playback()
            self.queue.prepared.clear()
            self.clear_snapshot()
            self.spoken_line = ''
            self.panel.set_status('Play to continue when the app is active.')
            self.changed()
        elif not self.can_read():
            # Unlocked preparation in flight must pass a fresh check at publication.
            if self.preload is not None:
                self.preload.cancel()
                self.preload = None
            self.clear_snapshot()
            self.spoken_line = ''
            self.changed()
        else:
            if self.waiting is not None:
                self.panel.set_status('Press Play to continue the playlist.')
            self.warm()

    def play(self, playlist_id, entry_id=None, *, anchor=None):
        if not self.owner.valid():
            return
        if self.panel is not None and playlist_id == self.playlist_id and (
                entry_id is None or entry_id in (self.active_id, getattr(self.initial, 'id', None))):
            if self.panel.overlay is None:
                self.panel.show_over(self.owner.view, anchor=anchor)
            elif self.state == 'stopped' and (self.work is None or self.work.done()):
                self.schedule(self.start())
            return
        self._retire_panel()
        self.stop_markdown_speech()
        self.panel = self.panel_type(self, self.app)
        self.panel.show_over(self.owner.view, anchor=anchor)
        self.schedule(self.select(playlist_id, entry_id))

    def schedule(self, coroutine):
        self.work = self.app.loop.create_task(coroutine)
        return self.work

    def invalidate_work(self):
        self.epoch += 1
        current = asyncio.current_task(loop=self.app.loop)
        for task in (self.work, self.preload):
            if task is not None and task is not current:
                task.cancel()
        self.work = self.preload = None
        self.pending_skips.clear()
        self.in_transition = None

    async def select(self, playlist_id, entry_id):
        epoch, panel = self.epoch, self.panel
        try:
            record = await asyncio.to_thread(self.catalog.get, playlist_id)
            if not self.valid() or epoch != self.epoch:
                return
            if record is None:
                panel.set_status('This playlist is unavailable.')
                return
            self.initial = self.queue.select(record, entry_id)
            self.changed()
            await asyncio.shield(panel.ready_task)
            if self.valid() and epoch == self.epoch and panel.engine.ready:
                await self.start()
        except (OSError, ValueError):
            if self.valid():
                self.panel.set_status('Playlist settings could not be read.')

    async def start(self):
        if not self.can_read() or (self.panel.playback is not None and not self.panel.playback.request_start()):
            return
        entry = self.queue.current.entry if self.queue.current is not None else self.initial
        if entry is None:
            self.panel.set_status('Add a Markdown document to start listening.')
            return
        self.waiting = None
        position = self.queue.position if self.queue.current is not None else self.resume_position
        await self.move(entry, position=position)
        await self.apply_skips()

    async def load(self, entry, epoch):
        admitted = self.queue.admitted(entry)
        if admitted is not None:
            return admitted
        if not self.can_read():
            raise NeedsUnlock
        read_epoch = self.read_epoch
        if self.owner.path == entry.path and not self.owner.editing and not getattr(self.owner, 'data_views_loading', False):
            base = self.owner.base
            key = 'logisticsPlaylistSpeech-' + uuid4().hex
            try:
                prepared = await self.prepare_view(self.owner.web, selection=False, key=key)
                if epoch != self.epoch:
                    raise asyncio.CancelledError
                if not self.can_read() or read_epoch != self.read_epoch:
                    raise NeedsUnlock
                if self.owner.base == base and prepared.text:
                    self.clear_snapshot()
                    self.snapshot = entry, base, prepared, key
                    passage = await asyncio.to_thread(prepare_passage, entry, '', prepared)
                    if self.can_read() and read_epoch == self.read_epoch:
                        return passage
                    raise NeedsUnlock
            finally:
                if self.snapshot is None or self.snapshot[3] != key:
                    self.clear_view(self.owner.web, key=key)

        def cancelled():
            return epoch != self.epoch or read_epoch != self.read_epoch or not self.can_read()

        try:
            passage = await asyncio.to_thread(self.queue.load, entry, cancelled)
        except OperationCancelled:
            if read_epoch != self.read_epoch:
                raise NeedsUnlock from None
            raise
        if epoch != self.epoch:
            raise asyncio.CancelledError
        if read_epoch != self.read_epoch or not self.can_read():
            raise NeedsUnlock
        return passage

    async def move(self, entry, word_index=None, *, paused=False, position=None):
        epoch = self.epoch
        record = self.queue.record
        if record is None or entry not in record.entries:
            return
        scanning = self.queue.scan(entry, word_index)
        candidate = None
        transition = entry, word_index, paused
        self.in_transition = transition
        try:
            candidate = next(scanning)
            while True:
                try:
                    passage = await self.load(candidate, epoch)
                    self.queue.unavailable.discard(candidate.id)
                except NeedsUnlock:
                    raise
                except (OSError, ValueError, OperationCancelled):
                    if not self.can_read():
                        raise NeedsUnlock
                    self.queue.unavailable.add(candidate.id)
                    passage = None
                if epoch != self.epoch or not self.valid():
                    return
                candidate = scanning.send(passage)
        except StopIteration as done:
            if done.value is None:
                self.panel.stop_playback()
                self.panel.set_status('Finished playlist.' if self.queue.current is not None
                                      else 'This playlist has no available spoken text.')
                self.changed()
                return
            passage, offset = done.value
            if word_index is None:
                offset = position if passage.entry == entry else 0
            if isinstance(offset, tuple):
                revision, saved = offset
                offset = saved if passage.revision == revision else 0
            if offset is None:
                offset = record.position if record.active_id == passage.entry.id and record.revision == passage.revision else 0
            if offset >= len(passage.units) // 2:
                offset = passage.words[-1]
            self.flush()
            previous = self.queue.current
            self.queue.activate(passage, offset)
            self.caption_at = -1
            if previous is not None and previous.entry != passage.entry:
                self.queue.keep(previous)
            if not await self.panel.play_passage(passage, self.queue.position, paused=paused,
                                                valid=lambda: self.valid() and self.epoch == epoch):
                if self.valid() and self.epoch == epoch:
                    session = self.panel.session
                    if session.state == 'speaking':
                        session.pause()
            self.flush()
            self.warm()
            self.changed()
        except NeedsUnlock:
            if self.valid() and self.epoch == epoch:
                self.waiting = (entry, word_index, paused)
                self.panel.session.pause()
                self.panel.set_status('Unlock and press Play to continue.')
                self.changed()
        finally:
            scanning.close()
            if self.in_transition is transition:
                self.in_transition = None

    def continue_waiting(self):
        entry, index, _ = self.waiting
        self.waiting = None
        self.schedule(self.move_then_skip(entry, index))

    async def move_then_skip(self, entry, index=None):
        await self.move(entry, index)
        await self.apply_skips()

    def skip(self, seconds):
        if not self.playback_allowed() or self.queue.current is None:
            return
        self.pending_skips.append(seconds)
        if self.work is None or self.work.done():
            self.schedule(self.apply_skips())

    async def apply_skips(self):
        while self.pending_skips and self.valid():
            index = self.panel.session.seek_position(self.pending_skips.pop(0))
            if index is not None:
                await self.move(self.queue.current.entry, index, paused=self.state == 'paused')
            if self.waiting is not None:
                self.pending_skips.clear()

    def exhausted(self):
        if self.in_transition is not None:
            return True
        if not self.valid() or self.queue.current is None:
            return False
        entries = self.queue.record.entries
        index = entries.index(self.queue.current.entry) + 1
        if index == len(entries):
            self.flush()
            self.app.loop.call_soon(self.show_finished, self.panel)
            return False
        self.schedule(self.move_then_skip(entries[index]))
        return True

    def show_finished(self, panel):
        if panel is self.panel and self.state == 'stopped':
            panel.set_status('Finished playlist.')

    def warm(self):
        if not self.opted_in() or not self.can_read() or (self.preload is not None and not self.preload.done()):
            return
        epoch = self.epoch

        async def preload():
            for entry in self.queue.adjacent():
                if not self.can_read() or epoch != self.epoch:
                    return
                if self.queue.admitted(entry) is not None:
                    continue
                try:
                    passage = await asyncio.to_thread(self.queue.load, entry,
                        lambda: epoch != self.epoch or not self.can_read(), limit=MAX_PREPARED)
                except (OSError, ValueError, OperationCancelled):
                    continue
                if self.can_read() and epoch == self.epoch:
                    self.queue.keep(passage)

        self.preload = self.app.loop.create_task(preload())

    def edited(self):
        if self.panel is None or self.queue.record is None:
            return
        if not self.catalog.has_protected_bucket(self.queue.record):
            self._retire_panel()
            self.changed()
        elif self.can_read():
            self.app.loop.create_task(self.refresh(self.playlist_id))

    async def refresh(self, playlist_id):
        try:
            record = await asyncio.to_thread(self.catalog.get, playlist_id)
        except (OSError, ValueError):
            return
        if self.panel is None or playlist_id != self.playlist_id:
            return
        if record is not None and record.entries != self.queue.record.entries:
            previous = self.in_transition
            self.invalidate_work()
        else:
            previous = None
        if not self.queue.edited(record):
            self._retire_panel()
        elif previous is not None and self.queue.current is not None:
            self.panel.session.pause()
            self.panel.set_status('Playlist changed · Play to continue.')
        else:
            self.warm()
        self.changed()

    def follow(self, start, end):
        if start < 0:
            if self.can_read() and self.snapshot is not None:
                _, base, prepared, key = self.snapshot
                if self.owner.base == base:
                    self.highlight_view(self.owner.web, prepared, start, end, key=key)
            return
        self.queue.observe(start)
        if self.can_read() and self.snapshot is not None and self.queue.current is not None:
            entry, base, prepared, key = self.snapshot
            if self.owner.base == base and entry == self.queue.current.entry:
                self.highlight_view(self.owner.web, prepared, start, end, key=key)
        if self.can_read() and (self.caption_at < 0 or abs(start - self.caption_at) > 38):
            self.caption_at = start
            self.spoken_line = self.queue.spoken_line(start, end)
            self.changed()
        if self.checkpoint_task is None:
            self.checkpoint_task = self.app.loop.call_later(2, self.flush)

    def flush(self):
        if self.checkpoint_task is not None:
            self.checkpoint_task.cancel()
            self.checkpoint_task = None
        if self.queue.observation is not None and self.valid():
            observation = self.queue.observation
            if observation is not getattr(self, 'saving', None):
                self.saving = observation
                self.save_task = self.app.loop.create_task(self.save_progress(observation))

    async def save_progress(self, observation):
        try:
            await asyncio.to_thread(self.queue.flush, observation)
        except (OSError, ValueError):
            pass
        finally:
            if self.saving is observation:
                self.saving = None

    def state_changed(self, state):
        if state in ('paused', 'stopped', 'unavailable'):
            self.flush()
        if state in ('stopped', 'unavailable'):
            self.invalidate_work()
            self.clear_snapshot()
            self.queue.prepared.clear()
            if self.queue.current is not None:
                self.initial = self.queue.current.entry
                self.resume_position = (self.queue.current.revision, self.queue.position)
            self.queue.current = None
            self.spoken_line = ''
        self.changed()

    def clear_snapshot(self):
        if self.snapshot is not None:
            self.clear_view(self.owner.web, key=self.snapshot[3])
            self.snapshot = None

    def _retire_panel(self):
        self.invalidate_work()
        self.flush()
        self.clear_snapshot()
        panel, self.panel = self.panel, None
        if panel is not None:
            panel.dispose()
        self.initial = self.waiting = None
        self.resume_position = None
        self.spoken_line = ''
        self.queue.clear()

    def close(self, *args, **kwargs):
        self._retire_panel()
        self.catalog.retire_memory()
        self.unsubscribe()
        self.changed()
