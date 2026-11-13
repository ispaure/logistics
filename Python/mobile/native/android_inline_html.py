"""Keep large inline Android pages below Chromium's data-URL limit."""
from urllib.parse import quote

DATA_URL_LIMIT = 2 * 1024 * 1024
DATA_URL_PREFIX = 'data:text/html,'


def load_inline_html(impl, root_url, content, *, fallback):
    # Toga checks unescaped characters, then percent-encodes the HTML. A page
    # below its cutoff can therefore exceed Chromium's final URL limit and
    # silently leave the view blank. Load those pages directly from memory.
    if len(DATA_URL_PREFIX) + len(quote(content)) >= DATA_URL_LIMIT:
        impl.loaded_future = None
        impl.native.loadDataWithBaseURL(root_url, content, 'text/html', 'utf-8', None)
    else:
        fallback(impl, root_url, content)
