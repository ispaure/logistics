"""Playback sequence over admitted Notes Library speech segments."""

from dataclasses import dataclass
from hashlib import sha256
from time import time_ns

from commonUtils.runtime.speech import seek_boundary, speech_word_starts

# A prepared sequence may retain the current file and one file on each side.
# Keep this smaller than the document opening budget, including generated text.
MAX_PREPARED = 128 * 1024


class NeedsUnlock(PermissionError):
    """This step would require admitting a new document."""


@dataclass(frozen=True)
class Passage:
    entry: object
    prepared: object
    revision: str
    words: tuple
    units: bytes

    @property
    def text(self):
        return self.prepared.text

    @property
    def breaks(self):
        return self.prepared.breaks


def prepare_passage(entry, source, prepared=None):
    from commonUtils.formats.markdown.speech import prepare_markdown

    if prepared is None:
        prepared = prepare_markdown(source)
    revision = sha256(prepared.text.encode()).hexdigest()
    words = tuple(speech_word_starts(prepared.text, prepared.breaks))
    return Passage(entry, prepared, revision, words, prepared.text.encode('utf-16-le'))


class PlaylistQueue:
    def __init__(self, catalog):
        self.catalog = catalog
        self.record = None
        self.current = None
        self.position = 0
        self.observation = None
        self.prepared = {}
        self.unavailable = set()

    def select(self, record, entry_id=None):
        self.clear()
        self.record = record
        wanted = entry_id or record.active_id
        return next((entry for entry in record.entries if entry.id == wanted),
                    next(iter(record.entries), None))

    def clear(self):
        self.record = self.current = self.observation = None
        self.position = 0
        self.prepared.clear()
        self.unavailable.clear()

    def edited(self, record):
        """Keep a moved entry. Stop on removal, repair or deletion."""
        self.record = record
        self.prepared = {entry: passage for entry, passage in self.prepared.items()
                         if record is not None and entry in record.entries}
        remaining = {entry.id for entry in record.entries} if record is not None else set()
        self.unavailable.intersection_update(remaining)
        return self.current is None or (record is not None and self.current.entry in record.entries)

    def load(self, entry, cancelled, *, limit=None):
        data = self.catalog.library.read(entry.path, cancelled=cancelled, limit=limit)
        return prepare_passage(entry, data.decode('utf-8-sig'))

    def activate(self, passage, position=None):
        if position is None:
            row = self.record
            position = row.position if row.active_id == passage.entry.id and row.revision == passage.revision else 0
        self.current = passage
        self.position = min(position, len(passage.units) // 2)
        self.prune()
        self.observe(self.position)
        return self.position

    def adjacent(self):
        if self.current is None or self.record is None:
            return ()
        entries = self.record.entries
        index = entries.index(self.current.entry)
        return entries[max(0, index - 1):index] + entries[index + 1:index + 2]

    def prune(self):
        adjacent = self.adjacent()
        self.prepared = {entry: passage for entry, passage in self.prepared.items() if entry in adjacent}

    def keep(self, passage):
        if passage.entry in self.adjacent() and len(passage.units) <= 2 * MAX_PREPARED:
            self.prepared[passage.entry] = passage

    def admitted(self, entry):
        if self.current is not None and self.current.entry == entry:
            return self.current
        return self.prepared.get(entry)

    def observe(self, position):
        if self.current is not None and self.record is not None and position >= 0:
            self.position = position
            self.observation = (self.record.id, self.current.entry, position, self.current.revision, time_ns())

    def spoken_line(self, start, end):
        """Return a bounded excerpt around a UTF-16 speech range."""
        if self.current is None:
            return ''
        left = max(0, start - 52) * 2
        right = (end + 76) * 2
        return ' '.join(self.current.units[left:right].decode('utf-16-le', 'ignore').split())

    def flush(self, observation=None):
        observation = self.observation if observation is None else observation
        if observation is not None:
            self.catalog.checkpoint(*observation)
            if self.observation is observation:
                self.observation = None

    def scan(self, entry, word_index=None):
        """Yield requested entries, accepting each admitted passage from the host.

        Natural advancement starts at the first playable word. A seek carries
        the signed residual across unavailable and empty entries and clamps at
        the last admitted playable word on the appropriate edge.
        """
        entries = self.record.entries
        origin = index = entries.index(entry)
        step = -1 if word_index is not None and word_index < 0 else 1
        clamp = None
        while 0 <= index < len(entries):
            passage = yield entries[index]
            if passage is not None and passage.words:
                if word_index is None:
                    return passage, 0
                if step < 0 and index != origin:
                    word_index += len(passage.words)
                direction, residual = seek_boundary(word_index, len(passage.words))
                if not direction:
                    return passage, passage.words[residual]
                word_index = residual
                clamp = passage, passage.words[-1 if step > 0 else 0]
            index += step
        return clamp
