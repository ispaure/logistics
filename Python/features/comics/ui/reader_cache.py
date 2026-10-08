"""Bounded decoded-page lookahead; archive reads stay off the GUI thread."""

from collections import OrderedDict
from commonUtils.ui import pyside as qt
from commonUtils.ui.operations import Operation
from features.comics.archive_io import archive_unchanged
from .reader_pages import read_image, read_candidates, read_previous

PRELOAD_RADIUS = 3
CACHE_BYTES = 128 * 1024 * 1024
CACHE_PAGES = 10


class ReaderPageCache(qt.QObject):
    idle = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pages = None
        self.images = OrderedDict()
        self.failed = set()
        self.skipped = set()
        self.wanted = ()
        self.busy = False
        self.stopped = False

    def set_pages(self, pages):
        self.pages = pages
        self.images.clear()
        self.failed.clear()
        self.skipped.clear()
        self.wanted = ()

    def lookup(self, index, previous, viewport, mode):
        if not archive_unchanged(self.pages.path, self.pages.document.snapshot):
            self.images.clear()
            return None
        def cached(pages, index):
            return self.images[index]
        try:
            if previous:
                return read_previous(self.pages, index, viewport, mode, decode=cached)
            return index, read_candidates(self.pages, index, decode=cached)
        except KeyError:
            return None

    def update(self, images, start, end):
        if self.stopped:
            return
        ahead = range(end + 1, min(len(self.pages.pages), end + PRELOAD_RADIUS + 1))
        behind = range(start - 1, max(-1, start - PRELOAD_RADIUS - 1), -1)
        self.wanted = tuple(range(start, end + 1)) + tuple(ahead) + tuple(behind)
        self.failed.intersection_update(self.wanted)
        self.skipped.clear()
        for index in list(self.images):
            if index not in self.wanted:
                del self.images[index]
        for index, image in images.items():
            if index in self.wanted:
                self._store(index, image)
        self._next()

    def _store(self, index, image):
        if image.sizeInBytes() > CACHE_BYTES:
            self.failed.add(index)  # Keep large displayed images outside the preload budget.
            return
        self.failed.discard(index)
        self.images[index] = image
        self.images.move_to_end(index)
        while len(self.images) > CACHE_PAGES or sum(image.sizeInBytes() for image in self.images.values()) > CACHE_BYTES:
            # Preserve current pages and the nearest lookahead first.
            evicted = max(self.images, key=self.wanted.index)
            del self.images[evicted]
            self.skipped.add(evicted)

    def _next(self):
        if self.busy or self.stopped:
            return
        index = next((index for index in self.wanted if index not in self.images and index not in self.failed and index not in self.skipped), None)
        if index is None:
            return
        pages = self.pages
        self.busy = True
        self.operation = Operation(lambda: read_image(pages, index), self)
        self.operation.completed.connect(lambda image, error: self._loaded(pages, index, image, error))
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _loaded(self, pages, index, image, error):
        if self.stopped or pages is not self.pages or index not in self.wanted:
            return
        if error:
            self.failed.add(index)
        else:
            self._store(index, image)

    def _finished(self):
        self.busy = False
        self.operation.deleteLater()
        if self.stopped:
            self.idle.emit()
        else:
            self._next()

    def stop(self):
        self.stopped = True
        self.wanted = ()
        self.images.clear()
