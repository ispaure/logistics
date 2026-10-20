"""Mobile Markdown renderer with Logistics appearance roles."""
from commonUtils.ui.native.markdown_preview import markdown_body, markdown_preview as _markdown_preview
from .palette import css_variables

__all__ = ['markdown_body', 'markdown_preview']


def markdown_preview(text, font_size=16, *, local_links=False, image_source=None):
    # The Android host replaces this fallback with the actual native font.
    stylesheet = (css_variables() + 'html body{font-family:-apple-system,BlinkMacSystemFont,sans-serif}'
                  'html,body{background:var(--surface);color:var(--text)}'
                  'p,li{text-align:var(--logistics-text-align,start)}')
    content = _markdown_preview(text, font_size, local_links=local_links, stylesheet=stylesheet, image_source=image_source)
    content = content.replace('content="width=device-width, initial-scale=1"',
        'content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"', 1)
    return content.replace('</head>', '<meta name="logistics-native-font" content="true"></head>', 1)


def folder_image_source(provider, document):
    """Resolve sibling raster images through the document's rooted provider."""
    import posixpath
    from urllib.parse import unquote, urlsplit
    from features.images.validation import image_dimensions, MAX_IMAGE
    used = 0
    cache = {}
    parent = posixpath.dirname(provider.relative(document))

    def load(target):
        nonlocal used
        if used >= 16 * 1024 * 1024:
            return None
        parsed = urlsplit(unquote(target))
        if (parsed.scheme or parsed.netloc or parsed.query or not parsed.path
                or parsed.path.startswith(('/', '\\')) or '\\' in parsed.path
                or any(ord(c) < 32 for c in parsed.path)):
            return None
        path = posixpath.normpath(posixpath.join(parent, parsed.path))
        if path == '..' or path.startswith('../'):
            return None
        path = provider.relative(path)
        if not path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            return None
        # Recheck cached entries too: another scene can revoke credentials.
        before = provider.entry(path)
        if (before['directory'] or before.get('size', 0) > MAX_IMAGE + 64
                or used + max(0, before.get('size', 0) - 64) > 16 * 1024 * 1024):
            return None
        if path in cache:
            revision, image = cache[path]
            if revision != before:
                raise ValueError('Image changed while rendering Markdown.')
            if used + len(image[1]) > 16 * 1024 * 1024:
                return None
            used += len(image[1])
            return image
        with provider.open(path) as stream:
            data = stream.read(MAX_IMAGE + 1)
        if provider.entry(path) != before:
            raise ValueError('Image changed while rendering Markdown.')
        image_dimensions(data)
        if used + len(data) > 16 * 1024 * 1024:
            return None
        used += len(data)
        mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/webp' if data[:4] == b'RIFF' else 'image/jpeg'
        image = mime, data
        cache[path] = before, image
        return image
    return load


def reader_image_source(copies, reader):
    provider = getattr(copies, 'provider', None)
    key = getattr(reader, 'key', None)
    if provider is not None and key is not None:
        return folder_image_source(provider, key)
    return None
