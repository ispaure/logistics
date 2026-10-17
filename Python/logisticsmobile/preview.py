"""Mobile Markdown renderer with Logistics appearance roles."""
from commonUtils.ui.native.markdown_preview import markdown_body, markdown_preview as _markdown_preview
from .palette import css_variables

__all__ = ['markdown_body', 'markdown_preview']


def markdown_preview(text, font_size=16, *, local_links=False):
    return _markdown_preview(text, font_size, local_links=local_links, stylesheet=css_variables())
