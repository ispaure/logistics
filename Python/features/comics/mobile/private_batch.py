"""Session-only recursive ComicInfo batches over a host's encrypted publisher."""
from threading import Event, RLock
from types import SimpleNamespace

from commonUtils.runtime.operations import check_cancelled, MutationIncomplete
from features.comics.comicinfo import ComicInfoXML
from .collection import scan_comics


class PrivateCollectionBatch:
    """Retain metadata snapshots, opening only one private archive at a time."""
    def __init__(self, *, valid, open_reader, revision, publish, release_reader=lambda reader: None):
        self.valid, self.open_reader = valid, open_reader
        self.revision, self.publish = revision, publish
        self.release_reader = release_reader
        self.cancel = Event()
        self.lock = RLock()
        self.closed = False
        self.requires_reopen = False
        self.entries, self.documents = [], []
        self.view = None

    def check(self):
        check_cancelled(lambda: self.closed or self.cancel.is_set() or not self.valid())

    def prepare(self, provider, folder):
        rows = scan_comics(provider, folder, cancelled=lambda: self.closed or self.cancel.is_set() or not self.valid())
        if not rows:
            raise ValueError('No CBZ/ZIP comics found in this folder.')
        metadata_bytes = 0
        for row in rows:
            self.check()
            with self.open_reader(row['path']) as reader:
                data = reader.comic.info.to_bytes()
                metadata_bytes += len(data)
                if metadata_bytes > 8 * 1024 * 1024:
                    raise ValueError('Choose a smaller batch: metadata exceeds 8 MiB.')
                info = ComicInfoXML.from_bytes(data)
                if self.revision(row['path']) != row['revision']:
                    raise ValueError('A selected comic changed. Reopen the batch.')
            with self.lock:
                self.check()
                self.entries.append(dict(row))
                self.documents.append(SimpleNamespace(info=info))
        return self

    def apply(self, changes):
        self.check()
        if self.requires_reopen:
            raise ValueError('A published revision needs reopening. Reopen the batch before retrying.')
        with self.lock:
            selected = list(self.entries)
        # Reopen every baseline and validate the patch before the first write.
        for row in selected:
            self.check()
            if self.revision(row['path']) != row['revision']:
                raise ValueError('A selected comic changed. Reopen the batch.')
            with self.open_reader(row['path']) as reader:
                reader.comic.prepare_metadata(changes)
            self.check()
        completed, failures = [], []
        for row in selected:
            if self.closed or self.cancel.is_set() or not self.valid():
                break
            published = False
            try:
                if self.revision(row['path']) != row['revision']:
                    raise ValueError('Comic changed; reopen the batch.')
                with self.open_reader(row['path']) as reader:
                    self.check()
                    # The injected transaction verifies ciphertext and its baseline
                    # again, including cancellation immediately before publication.
                    updated = self.publish(reader, changes, cancelled=lambda: self.closed or self.cancel.is_set() or not self.valid())
                    published = True
                    try:
                        info = ComicInfoXML.from_bytes(updated.comic.info.to_bytes())
                    finally:
                        # Host scope releases any returned reader's source caches.
                        if updated is not reader:
                            self.release_reader(updated)
                with self.lock:
                    if not self.closed:
                        index = self.entries.index(row)
                        row['revision'] = self.revision(row['path'])
                        self.documents[index].info = info
                completed.append(row['path'])
            except Exception as error:
                # Private paths/metadata and backend diagnostics stay out of labels.
                failures.append(row['path'])
                if published or (isinstance(error, MutationIncomplete) and error.result.destination_published):
                    self.requires_reopen = True
                    break
        return completed, failures

    def close(self):
        self.closed = True
        self.cancel.set()
        with self.lock:
            self.entries.clear()
            for document in self.documents:
                document.info = ComicInfoXML.from_bytes(b'<ComicInfo/>')
            self.documents.clear()
        if self.view is not None:
            self.view.dispose_metadata()
            self.view = None
