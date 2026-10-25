"""Bounded in-memory Markdown resources, independent of presentation."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit, urljoin
from urllib.request import url2pathname


def prepare_markdown(provider, path, *, data=None, cancelled=lambda: False):
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
    for match in re.finditer(r'!\[[^\]\n]*\]\(<?([^\s)>]+)>?(?:\s+[^)]*)?\)', decode_bytes(data).text):
        check_cancelled(cancelled)
        parts = urlsplit(unquote(match.group(1)))
        if parts.scheme or parts.netloc:
            continue
        target = Path(url2pathname(urlsplit(urljoin(path.parent.as_uri() + '/', parts.path)).path))
        try:
            provider.relative(target)
            value = read(target, min(budget, getattr(provider, 'max_resource', 8 * 1024 * 1024)))
            budget -= len(value)
            resources[target] = value
        except (ValueError, OSError):
            continue
        if budget <= 0:
            break
    return data, resources
