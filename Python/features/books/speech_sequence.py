"""Resolve an approximate speech position against the EPUB spine lazily."""

from commonUtils.runtime.speech import seek_boundary


class ChapterSeek:
    def __init__(self, index, count, target, words):
        self.count = count
        self.direction, self.remainder = seek_boundary(target, len(words))
        self.index = index
        self.landing = None
        self._visit(words, None, target)

    def _visit(self, words, prepared, target):
        if words:
            offset = words[max(0, min(len(words) - 1, target))]
            self.landing = self.index, offset, prepared
        step, self.remainder = seek_boundary(target, len(words))
        next_index = self.index + step
        self.index = next_index if step and 0 <= next_index < self.count else None

    def accept(self, words, prepared):
        target = self.remainder + len(words) if self.direction < 0 else self.remainder
        self._visit(words, prepared, target)
