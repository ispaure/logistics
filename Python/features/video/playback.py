"""Local and remote video admission and provider-owned, seekable playback content."""
from contextlib import contextmanager
from pathlib import PurePosixPath

from commonUtils.runtime.resources.content import ProviderContent
from services.documents.storage import document_remote, document_sources
from services.access_policy import session_only

from .formats import VIDEO_EXTENSIONS
from .buffering import DEFAULT_BUFFERING, MemoryRanges



class VideoContent:
    """Own one retained grant, revision and bounded decoder stream.

    ProviderContent chooses native decoded ranges for mobile LocalCrypt, whose
    ordinary open() is a ciphertext transfer stream rather than video content.
    """
    extensions = VIDEO_EXTENSIONS
    retain_ranges = True

    def __init__(self, provider, path, *, buffering=DEFAULT_BUFFERING):
        if PurePosixPath(str(path)).suffix.lower() not in self.extensions:
            raise ValueError('Choose a supported video file (MP4, MKV, AVI, MOV, WebM or MPEG).')
        self.source = ProviderContent(provider, path)
        self.provider, self.path = self.source.provider, self.source.path
        self.remote = document_remote(self.provider)
        self.closed = False
        self.buffering, self.memory = buffering, None
        try:
            self._restricted = session_only(self.provider)
            self.gate = next((source.privacy_gate for source in document_sources(self.provider)
                              if getattr(source, 'privacy_gate', None) is not None), None)
            self.check()
            with self.source.open(self.path) as stream:
                if not stream.seekable():
                    raise ValueError('Video playback requires seekable content.')
                stream.seek(0, 2)
                self.size = stream.tell()
            if not self.size:
                raise ValueError('This video is empty.')
            if self.remote and self.retain_ranges:
                self.memory = MemoryRanges(self.size, buffering, self.check_access)
        except BaseException:
            self.close()
            raise

    @property
    def restricted(self):
        return self._restricted

    def require_external(self):
        self.check_access()
        if self.restricted:
            raise PermissionError('Casting and floating playback are unavailable with session-only credentials.')

    def check_access(self):
        """Fast credential/gate checks for native controls; no network metadata."""
        if self.closed or (self.gate is not None and self.gate.locked):
            raise PermissionError('Unlock the credential session before resuming video.')
        self.source.check_access()

    def check(self):
        self.check_access()
        self.source.check()

    @contextmanager
    def open(self):
        self.check()
        with self.source.open(self.path) as stream:
            from commonUtils.runtime.resources.range_reader import RangeReader
            if self.memory is None:
                yield stream
                return
            if isinstance(stream, RangeReader):
                stream.block_size = self.buffering.range_bytes
                stream.cache_blocks = 0  # The shared cache owns retention.
            with RangeReader(self.size, lambda offset, count: self.memory.read(offset, count, stream),
                    block_size=self.buffering.range_bytes, cache_blocks=0,
                    max_read=16 * 1024 * 1024, validate=self.check_access) as buffered:
                yield buffered

    def buffered_ranges(self):
        self.check_access()
        return dict(local=not self.remote,approximate=True,ranges=self.memory.ranges() if self.memory else [])

    def close(self):
        if not self.closed:
            self.closed = True
            if self.memory is not None:
                self.memory.close()
            self.source.close()


class SubtitleContent(VideoContent):
    retain_ranges = False  # Sidecars must not each allocate a movie rewind budget.
    extensions = frozenset({'.srt', '.vtt', '.ass', '.ssa'})
