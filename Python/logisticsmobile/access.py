"""Scoped import adapters. Native pickers supply references to this boundary."""
from contextlib import contextmanager
from pathlib import Path


class LocalDocuments:
    @contextmanager
    def open(self, reference):
        path = Path(reference)
        with path.open('rb') as stream:
            yield path.name, stream


class IOSDocuments:
    """Accept an NSURL supplied by a document picker; balance scoped access."""
    @contextmanager
    def open(self, url):
        granted = bool(url.startAccessingSecurityScopedResource())
        if not granted:
            raise PermissionError('The selected document did not grant security-scoped access.')
        try:
            path = Path(str(url.path))
            with path.open('rb') as stream:
                yield path.name, stream
        finally:
            url.stopAccessingSecurityScopedResource()


class AndroidInput:
    def __init__(self, stream):
        self.stream = stream

    def read(self, limit):
        # Chaquopy converts Python bytes to Java byte[] for native stream calls.
        from java import jarray, jbyte
        chunks, remaining = [], limit
        while remaining:
            buffer = jarray(jbyte)(min(16384, remaining))
            count = self.stream.read(buffer)
            if count < 0:
                break
            if count == 0:
                raise OSError('The document provider returned an empty read without EOF.')
            chunks.append(bytes(int(value) & 255 for value in buffer[:count]))
            remaining -= count
        return b''.join(chunks)


class AndroidDocuments:
    """Accept an android.net.Uri and its granted ContentResolver access."""
    def __init__(self, resolver):
        self.resolver = resolver

    @contextmanager
    def open(self, uri):
        cursor = self.resolver.query(uri, ['_display_name'], None, None, None)
        try:
            if cursor is None or not cursor.moveToFirst():
                raise OSError('The selected document has no display name.')
            name = str(cursor.getString(cursor.getColumnIndexOrThrow('_display_name')))
        finally:
            if cursor is not None:
                cursor.close()
        stream = self.resolver.openInputStream(uri)
        if stream is None:
            raise OSError('The selected document could not be opened.')
        try:
            yield name, AndroidInput(stream)
        finally:
            stream.close()
