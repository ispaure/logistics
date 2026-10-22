"""Mobile Markdown renderer with Logistics appearance roles."""
from commonUtils.ui.native.markdown_preview import markdown_body, markdown_preview as _markdown_preview
from .palette import css_variables
from commonUtils.ui.native.markdown_images import folder_image_source

__all__ = ['markdown_body', 'markdown_preview']


def markdown_preview(text, font_size=16, *, local_links=False, image_source=None):
    # The Android host replaces this fallback with the actual native font.
    stylesheet = (css_variables() + 'html body{font-family:-apple-system,BlinkMacSystemFont,sans-serif}'
                  'html,html body{background:var(--window);color:var(--text)}'
                  'p,li{text-align:var(--logistics-text-align,start)}')
    content = _markdown_preview(text, font_size, local_links=local_links, stylesheet=stylesheet, image_source=image_source)
    content = content.replace('content="width=device-width, initial-scale=1"',
        'content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"', 1)
    return content.replace('</head>', '<meta name="logistics-native-font" content="true"></head>', 1)


def reader_image_source(copies, reader):
    provider = getattr(copies, 'provider', None)
    key = getattr(reader, 'key', None)
    if provider is not None and key is not None:
        return folder_image_source(provider, key)
    return None
