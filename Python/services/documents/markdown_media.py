"""Document-owned Markdown media; encrypted videos use revocable range streams."""
import posixpath
from pathlib import PurePosixPath
from threading import RLock
from urllib.parse import unquote, urlsplit

from commonUtils.formats.markdown.image_sources import folder_image_source


class MarkdownMedia:
    def __init__(self, provider, document, *, root=None, entry=None, resolve=None,
                 max_image_bytes=16 * 1024 * 1024):
        self.provider, self.document, self.root = provider, provider.relative(document), root
        from types import SimpleNamespace
        self.image_provider = SimpleNamespace(relative=provider.relative, open=provider.open, entry=entry) if entry else provider
        self.max_image_bytes = max_image_bytes
        self.images = folder_image_source(self.image_provider, document, root=root, resolve=resolve,
                                         max_total_bytes=max_image_bytes)
        self.videos, self.closed, self.lock = {}, False, RLock()
        self.resolve = resolve

    def render_source(self, *, resolve=None):
        """Each render gets a fresh raster budget; video leases stay document-owned."""
        from features.video.formats import VIDEO_EXTENSIONS
        images = folder_image_source(self.image_provider, self.document, root=self.root, resolve=resolve or self.resolve,
                                     max_total_bytes=self.max_image_bytes)
        def source(target):
            with self.lock:
                if self.closed:
                    return None
            if PurePosixPath(unquote(urlsplit(target).path)).suffix.lower() in VIDEO_EXTENSIONS:
                return self(target, resolve=resolve)
            return images(target)
        source.videos = self.videos
        return source

    def __call__(self, target, *, resolve=None):
        from features.video.formats import VIDEO_EXTENSIONS
        parts = urlsplit(target)
        name = unquote(parts.path)
        if PurePosixPath(name).suffix.lower() not in VIDEO_EXTENSIONS:
            return self.images(target)
        if parts.scheme or parts.netloc or parts.query or not name or name.startswith(('/', '\\')) or '\\' in name:
            return None
        from commonUtils.formats.markdown import link_path_names
        candidates = []
        for name in link_path_names(parts.path):
            candidates.append(posixpath.normpath(posixpath.join(posixpath.dirname(self.document), name)))
            if self.root is not None and not name.startswith(('./', '../')):
                candidates.append(posixpath.normpath(posixpath.join(self.root, name)))
                if '/' not in name:
                    candidates.extend(posixpath.join(self.root, folder, name) for folder in
                                      ('Attachments', 'attachments', 'Assets', 'assets', 'Videos', 'videos'))
        def paths():
            resolver = resolve or self.resolve
            if resolver is not None:
                try:
                    yield resolver(target)
                except (OSError, ValueError):
                    # Resolution can fail before reaching a previously cached
                    # candidate (for example after deletion). Retire invalid
                    # streams even when there is no longer a resolved path.
                    for path, (content, transport) in list(self.videos.items()):
                        try:
                            content.check()
                        except (OSError, ValueError):
                            del self.videos[path]
                            try:
                                transport.close()
                            finally:
                                content.close()
                    raise
            else:
                yield from dict.fromkeys(candidates)

        with self.lock:
            if self.closed:
                return None
            for candidate in paths():
                if candidate == '..' or candidate.startswith('../'):
                    continue
                if self.root and not candidate.startswith(self.root + '/'):
                    continue
                if any(part.startswith('.') for part in PurePosixPath(candidate).parts):
                    continue
                try:
                    candidate = self.provider.relative(candidate)
                    if candidate in self.videos:
                        content, transport = self.videos[candidate]
                        try:
                            content.check()
                        except (OSError, ValueError):
                            del self.videos[candidate]
                            try:
                                transport.close()
                            finally:
                                content.close()
                        else:
                            return 'video/mp4', transport.url
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
            self.resolve = None
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
