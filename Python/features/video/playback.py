"""Local and remote video admission and provider-owned, seekable playback content."""
from pathlib import PurePosixPath

from commonUtils.runtime.resources.content import ProviderContent
from services.documents.storage import document_remote, document_sources

VIDEO_EXTENSIONS = frozenset({'.mp4', '.mkv'})


def session_only(provider):
    """Unknown private credential policy fails closed for external playback."""
    sources = tuple(document_sources(provider))
    if any(getattr(source, 'session_only', False) for source in sources):
        return True
    if not any(getattr(source, 'private', False) for source in sources):
        return False
    for source in sources:
        client, remote = getattr(source, 'client', None), getattr(source, 'remote', None)
        if client is not None and remote is not None:
            record = next((item for item in getattr(client, 'package_records', ())
                           if remote in item.get('remotes', ())), None)
            return record is None or not record.get('saved', False)
        connection = getattr(source, 'connection', None)
        if connection is not None:
            # Desktop LocalCrypt currently unlocks its package into a .session
            # context even when a separate saved cloud config also exists.
            # That unrelated config must never relax this retained grant.
            return PurePosixPath(str(connection.context)).suffix == '.session'
    return True


class VideoContent:
    """Own one retained grant, revision and bounded decoder stream.

    ProviderContent chooses native decoded ranges for mobile LocalCrypt, whose
    ordinary open() is a ciphertext transfer stream rather than video content.
    """
    extensions = VIDEO_EXTENSIONS

    def __init__(self, provider, path):
        if PurePosixPath(str(path)).suffix.lower() not in self.extensions:
            raise ValueError('Choose an MP4 or MKV video.')
        self.source = ProviderContent(provider, path)
        self.provider, self.path = self.source.provider, self.source.path
        self.remote = document_remote(self.provider)
        self.gate = next((source.privacy_gate for source in document_sources(self.provider)
                          if getattr(source, 'privacy_gate', None) is not None), None)
        self.closed = False
        try:
            self.check()
            with self.source.open(self.path) as stream:
                if not stream.seekable():
                    raise ValueError('Video playback requires seekable content.')
                stream.seek(0, 2)
                self.size = stream.tell()
            if not self.size:
                raise ValueError('This video is empty.')
        except BaseException:
            self.close()
            raise

    @property
    def restricted(self):
        return session_only(self.provider)

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

    def open(self):
        self.check()
        return self.source.open(self.path)

    def close(self):
        if not self.closed:
            self.closed = True
            self.source.close()


class SubtitleContent(VideoContent):
    extensions = frozenset({'.srt', '.vtt', '.ass', '.ssa'})
