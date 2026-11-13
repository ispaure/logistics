"""Qt playback controls for an ordered Notes Library playlist."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown.speech import prepare_document
from commonUtils.ui.readers.read_aloud import ReadAloud

from ..playlist_queue import PlaylistQueue, prepare_passage


class PlaylistReadAloud(ReadAloud):
    def __init__(self, playlist):
        self.playlist = playlist
        super().__init__(playlist.owner, lambda: '', scope='the playlist')

    def start(self):
        self.playlist.start()

    def skip(self, seconds):
        self.playlist.skip(seconds)

    def _range_changed(self, start, end):
        snapshot = self.playlist.snapshot
        if start >= 0 and snapshot is not None:
            path, revision = snapshot
            owner = self.playlist.owner
            if owner.storage.path != path or owner.viewer.browser.document().revision() != revision:
                self._clear_highlight()
        super()._range_changed(start, end)
        self.playlist.follow(start, end)

    def _session_state(self, state, message):
        super()._session_state(state, message)
        self.playlist.state_changed(state)

    def stop(self):
        self.playlist.invalidate()
        self.playlist.flush()
        super().stop()


class PlaylistSpeech(qt.QObject):
    delivered = qt.Signal(object, object)
    edited = qt.Signal()

    def __init__(self, owner, catalog, changed):
        super().__init__(owner)
        self.owner, self.catalog, self.changed = owner, catalog, changed
        self.queue = PlaylistQueue(catalog)
        self.controls = PlaylistReadAloud(self)
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='playlist')
        self.epoch = 0
        self.initial = self.snapshot = self.task = None
        self.pending_skips = []
        self.spoken_line = ''
        self.caption_at = -1
        self.resume_position = None
        self.closed = False
        self.delivered.connect(self.complete, qt.Qt.ConnectionType.QueuedConnection)
        self.edited.connect(self.refresh, qt.Qt.ConnectionType.QueuedConnection)
        self.unsubscribe = catalog.subscribe(self.edited.emit)
        self.checkpoint_timer = qt.QTimer(self)
        self.checkpoint_timer.setSingleShot(True)
        self.checkpoint_timer.setInterval(2000)
        self.checkpoint_timer.timeout.connect(self.flush)

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
        return self.controls.session.state if self.controls.session is not None else 'stopped'

    def valid(self):
        return not self.closed and not self.owner.locked and not self.owner.closing and not self.catalog.revoked()

    def play(self, playlist_id, entry_id=None, *, anchor=None):
        if not self.valid():
            return
        self.controls.anchor = anchor
        if self.controls.panel is None or not self.controls.panel.isVisible():
            self.controls.show()
        if self.controls.session is None:
            return
        if playlist_id == self.playlist_id and entry_id in (None, self.active_id, getattr(self.initial, 'id', None)):
            if self.state == 'stopped' and self.task is None:
                self.start()
            return
        self.controls.stop()
        self.owner.viewer.speech.stop()
        try:
            record = self.catalog.get(playlist_id)
        except (OSError, ValueError):
            record = None
        if record is None:
            self.controls.message.setText('This playlist is unavailable.')
            return
        self.initial = self.queue.select(record, entry_id)
        self.resume_position = None
        self.controls.session.on_exhausted = self.exhausted
        self.start()
        self.changed()

    def start(self):
        if not self.valid() or self.task is not None:
            return
        entry = self.queue.current.entry if self.queue.current is not None else self.initial
        if entry is None:
            self.controls.message.setText('Add a Markdown document to start listening.')
            return
        self.move(entry, position=self.queue.position if self.queue.current is not None else self.resume_position)

    def invalidate(self):
        self.epoch += 1
        if self.task is not None:
            self.task.cancel()
            self.task = None
        self.pending_skips.clear()

    def rendered(self):
        storage = self.owner.storage
        if storage.path is not None and not self.owner.viewer.edit_button.isChecked():
            try:
                path = Path(storage.path).relative_to(self.owner.provider.root.resolve()).as_posix()
            except ValueError:
                return None
            browser = self.owner.viewer.browser
            return path, prepare_document(browser, selection=False), browser.document().revision()

    def move(self, entry, index=None, *, paused=False, position=None):
        epoch, record = self.epoch, self.queue.record
        if record is None or entry not in record.entries:
            return
        rendered, current = self.rendered(), self.queue.current
        scanning = self.queue.scan(entry, index)

        def work():
            unavailable = set()
            try:
                candidate = next(scanning)
                while self.valid() and self.epoch == epoch:
                    try:
                        if current is not None and candidate == current.entry:
                            passage = current
                        elif rendered is not None and rendered[0] == candidate.path:
                            passage = prepare_passage(candidate, '', rendered[1])
                        else:
                            passage = self.queue.load(candidate, lambda: self.epoch != epoch or not self.valid())
                    except (OSError, ValueError, OperationCancelled):
                        unavailable.add(candidate.id)
                        passage = None
                    candidate = scanning.send(passage)
            except StopIteration as done:
                return done.value, unavailable
            finally:
                scanning.close()
            return None, unavailable

        future = self.worker.submit(work)
        self.task = future
        future.add_done_callback(lambda result: self.deliver(
            (epoch, record, entry, index, position, paused, rendered), result))

    def deliver(self, context, result):
        if not self.closed:
            try:
                self.delivered.emit(context, result)
            except RuntimeError:
                pass  # The widget was destroyed during worker retirement.

    def complete(self, context, future):
        epoch, record, entry, index, position, paused, rendered = context
        if future is not self.task or not self.valid() or epoch != self.epoch:
            return
        self.task = None
        try:
            result, unavailable = future.result()
        except Exception:
            self.controls.stop()
            self.controls.message.setText('Could not prepare playlist speech.')
            return
        self.queue.unavailable.update(unavailable)
        if result is None:
            active = self.queue.current is not None
            self.controls.stop()
            self.controls.message.setText('Finished playlist.' if active else 'This playlist has no available spoken text.')
        else:
            passage, offset = result
            self.queue.unavailable.discard(passage.entry.id)
            if index is None:
                offset = position if passage.entry == entry else 0
            if isinstance(offset, tuple):
                revision, saved = offset
                offset = saved if passage.revision == revision else 0
            if offset is not None and offset >= len(passage.units) // 2:
                offset = passage.words[-1]
            self.flush()
            self.queue.activate(passage, offset)
            self.caption_at = -1
            self.snapshot = (self.owner.storage.path, rendered[2]) if rendered is not None and (
                passage.entry.path == rendered[0] and passage.prepared is rendered[1]) else None
            self.controls._highlight_widget = self.owner.viewer.browser if self.snapshot is not None else None
            self.controls._prepared = passage.prepared if self.snapshot is not None else None
            self.controls.play_passage(passage.text, self.queue.position, paused=paused, breaks=passage.breaks)
            self.flush()
            self.apply_skip()
        self.changed()

    def skip(self, seconds):
        self.pending_skips.append(seconds)
        self.apply_skip()

    def apply_skip(self):
        if self.task is not None or not self.pending_skips or self.queue.current is None:
            return
        index = self.controls.session.seek_position(self.pending_skips.pop(0))
        if index is not None:
            self.move(self.queue.current.entry, index, paused=self.state == 'paused')

    def exhausted(self):
        if self.task is not None:
            return True
        if not self.valid() or self.queue.current is None:
            return False
        entries = self.queue.record.entries
        index = entries.index(self.queue.current.entry) + 1
        if index == len(entries):
            self.flush()
            return False
        self.move(entries[index])
        return True

    def refresh(self):
        if self.playlist_id is None or not self.valid():
            return
        try:
            record = self.catalog.get(self.playlist_id)
        except (OSError, ValueError):
            record = None
        previous = self.queue.record
        if record == previous:
            return
        if record is None or record.entries != self.queue.record.entries:
            moving = self.task is not None
            self.invalidate()
        else:
            moving = False
        if not self.queue.edited(record):
            self.controls.stop()
            self.initial = next((entry for entry in record.entries if entry.id == record.active_id), None) if record else None
        elif moving:
            self.controls.session.pause()
            self.controls.message.setText('Playlist changed · Play to continue.')
        self.changed()

    def follow(self, start, end):
        if start >= 0:
            self.queue.observe(start)
            if self.caption_at < 0 or abs(start - self.caption_at) > 38:
                self.caption_at = start
                self.spoken_line = self.queue.spoken_line(start, end)
                self.changed()
            if not self.checkpoint_timer.isActive():
                self.checkpoint_timer.start()

    def flush(self):
        self.checkpoint_timer.stop()
        if self.queue.observation is not None:
            try:
                self.queue.flush()
            except (OSError, ValueError):
                pass

    def state_changed(self, state):
        if state in ('paused', 'stopped', 'unavailable'):
            self.flush()
        if state in ('stopped', 'unavailable'):
            self.invalidate()
            if self.queue.current is not None:
                self.initial = self.queue.current.entry
                self.resume_position = self.queue.current.revision, self.queue.position
            self.queue.current = self.snapshot = None
            self.spoken_line = ''
        self.changed()

    def close(self):
        self.controls.stop()
        self.closed = True
        self.unsubscribe()
        self.catalog.retire_memory()
        self.worker.shutdown(wait=False, cancel_futures=True)
        if self.controls.panel is not None:
            self.controls.panel.close()
        if self.controls.session is not None:
            self.controls.session.dispose()
        self.queue.clear()
