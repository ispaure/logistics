"""Bounded in-memory Markdown resources, independent of presentation."""
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from urllib.request import url2pathname


class MarkdownResources(dict):
    def __init__(self):
        super().__init__()
        self.videos, self.media = {}, None

    def close(self):
        if self.media is not None:
            self.media.close()
            self.media = None
        self.videos.clear()
        self.clear()


def prepare_markdown(provider, path, *, data=None, cancelled=lambda: False, image_source=None):
    from commonUtils.runtime.operations import check_cancelled
    from contextlib import nullcontext
    def read(path, limit):
        check_cancelled(cancelled)
        scope = getattr(provider, 'operation', None)
        with scope(cancelled) if scope else nullcontext():
            with provider.open(path) as stream:
                value = stream.read(limit + 1)
        if len(value) > limit:
            raise ValueError('Markdown resource exceeds the memory limit.')
        return value
    if data is None:
        data = read(path, 8 * 1024 * 1024)
    resources = MarkdownResources()
    budget = 32 * 1024 * 1024
    # Resource I/O stays in the opening worker; Qt rendering uses only RAM.
    from commonUtils.persistence.text import decode_bytes
    from commonUtils.formats.markdown.images import image_targets
    try:
        for reference in image_targets(decode_bytes(data).text)[:128]:
            check_cancelled(cancelled)
            parts = urlsplit(reference)
            if parts.scheme or parts.netloc or parts.query:
                continue
            target = Path(url2pathname(urlsplit(urljoin(path.parent.as_uri() + '/', parts.path)).path))
            try:
                provider.relative(target)
                from features.video.formats import VIDEO_EXTENSIONS
                if target.suffix.lower() in VIDEO_EXTENSIONS:
                    source = image_source
                    if source is None:
                        if resources.media is None:
                            from .markdown_media import MarkdownMedia
                            resources.media = MarkdownMedia(provider, path)
                        source = resources.media
                    video = source(reference)
                    if video is not None and isinstance(video[1], str):
                        resources.videos[target.resolve()] = video[1]
                    continue
                if image_source is not None:
                    image = image_source(reference)
                    if image is None:
                        continue
                    _, value = image
                    if len(value) > budget:
                        continue
                else:
                    value = read(target, min(budget, getattr(provider, 'max_resource', 8 * 1024 * 1024)))
                budget -= len(value)
                resources[target.resolve()] = value
            except (ValueError, OSError):
                continue
            if budget <= 0:
                break
        check_cancelled(cancelled)
    except BaseException:
        resources.close()
        raise
    return data, resources
