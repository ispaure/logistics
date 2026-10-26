"""Bounded in-memory Markdown resources, independent of presentation."""
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from urllib.request import url2pathname


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
    resources = {}
    budget = 32 * 1024 * 1024
    # Resource I/O stays in the opening worker; Qt rendering uses only RAM.
    from commonUtils.persistence.text import decode_bytes
    from commonUtils.formats.markdown.images import image_targets
    for reference in image_targets(decode_bytes(data).text):
        check_cancelled(cancelled)
        parts = urlsplit(reference)
        if parts.scheme or parts.netloc or parts.query:
            continue
        target = Path(url2pathname(urlsplit(urljoin(path.parent.as_uri() + '/', parts.path)).path))
        try:
            provider.relative(target)
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
    return data, resources
