"""Document-owned Markdown media; encrypted videos use revocable range streams."""
import posixpath
from pathlib import PurePosixPath
from threading import RLock
from urllib.parse import unquote, urlsplit

from commonUtils.formats.markdown.image_sources import folder_image_source


class MarkdownMedia:
    def __init__(self, provider, document, *, root=None, entry=None):
        self.provider, self.document, self.root = provider, provider.relative(document), root
        from types import SimpleNamespace
        self.image_provider = SimpleNamespace(relative=provider.relative, open=provider.open, entry=entry) if entry else provider
        self.images = folder_image_source(self.image_provider, document, root=root)
        self.videos, self.closed, self.lock = {}, False, RLock()

    def render_source(self):
        """Each render gets a fresh raster budget; video leases stay document-owned."""
        from features.video.formats import VIDEO_EXTENSIONS
        images = folder_image_source(self.image_provider, self.document, root=self.root)
        def source(target):
            with self.lock:
                if self.closed:
                    return None
            if PurePosixPath(unquote(urlsplit(target).path)).suffix.lower() in VIDEO_EXTENSIONS:
                return self(target)
            return images(target)
        source.videos = self.videos
        return source

    def __call__(self, target):
        from features.video.formats import VIDEO_EXTENSIONS
        parts = urlsplit(target)
        name = unquote(parts.path)
        if PurePosixPath(name).suffix.lower() not in VIDEO_EXTENSIONS:
            return self.images(target)
        if parts.scheme or parts.netloc or parts.query or not name or name.startswith(('/', '\\')) or '\\' in name:
            return None
        candidates = [posixpath.normpath(posixpath.join(posixpath.dirname(self.document), name))]
        if self.root is not None and not name.startswith(('./', '../')):
            candidates.append(posixpath.normpath(posixpath.join(self.root, name)))
            if '/' not in name:
                candidates.extend(posixpath.join(self.root, folder, name) for folder in
                                  ('Attachments', 'attachments', 'Assets', 'assets', 'Videos', 'videos'))
        with self.lock:
            if self.closed:
                return None
            for candidate in dict.fromkeys(candidates):
                if candidate == '..' or candidate.startswith('../'):
                    continue
                if self.root and not candidate.startswith(self.root + '/'):
                    continue
                if any(part.startswith('.') for part in PurePosixPath(candidate).parts):
                    continue
                try:
                    candidate = self.provider.relative(candidate)
                    if candidate in self.videos:
                        self.videos[candidate][0].check_access()
                        return 'video/mp4', self.videos[candidate][1].url
                    if len(self.videos) >= 8:
                        return None
                    from features.video.playback import VideoContent
                    from features.video.transport import VideoTransport
                    content = VideoContent(self.provider, candidate)
                    try:
                        transport = VideoTransport(content)
                    except BaseException:
                        content.close()
                        raise
                    self.videos[candidate] = content, transport
                    return 'video/mp4', transport.url
                except (OSError, ValueError):
                    continue
        return None

    def close(self):
        with self.lock:
            self.closed = True
            videos, self.videos = self.videos, {}
        for content, transport in videos.values():
            try:
                transport.close()
            finally:
                content.close()


def reader_media_source(provider, reader, path):
    source = getattr(reader, '_markdown_media', None)
    if source is None or source.document != provider.relative(path):
        if source is not None:
            source.close()
        reader._markdown_media = source = MarkdownMedia(provider, path)
    return source.render_source()
