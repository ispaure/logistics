"""Mobile Markdown renderer with Logistics appearance roles."""
from commonUtils.ui.native.markdown_preview import markdown_body, markdown_preview as _markdown_preview
from .palette import css_variables
from commonUtils.ui.native.markdown_images import folder_image_source
from features.text_editor.mobile.markdown_style import READING_CSS

__all__ = ['markdown_body', 'markdown_preview']


def markdown_preview(text, font_size=16, *, local_links=False, image_source=None):
    # The Android host replaces this fallback with the actual native font.
    stylesheet = (css_variables() + 'html body{font-family:-apple-system,BlinkMacSystemFont,sans-serif}'
                  'html,html body{background:var(--window);color:var(--text)}'
                  'p,li{text-align:var(--logistics-text-align,start)}' + READING_CSS)
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


def prepare_managed_preview(owner, *, on_edit, valid):
    """Build retained preview controls on the existing text-editor owner.

    The owner already holds its WebView and owns disposal. The host supplies Edit
    and search-validity callbacks; checkpoint, workspace and route policy stay
    outside construction. Repeated preview visits keep controls/search identity.
    """
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN, ROW
    if owner.preview_box is not None:
        return
    from .control_icons import icon_button
    owner.preview_edit = icon_button('edit', 'Edit Markdown', on_press=on_edit)
    owner.preview_actions_button = icon_button('more', 'Document actions')
    owner.preview_toolbar = toga.Box(children=[owner.preview_edit,
        toga.Box(style=Pack(flex=1)), owner.preview_actions_button], style=Pack(direction=ROW))
    owner.preview_box = toga.Box(children=[
        owner.preview_toolbar,
        owner.preview], style=Pack(direction=COLUMN, flex=1))
    from commonUtils.ui.native.markdown_search import MarkdownPageSearch
    owner.preview_search = MarkdownPageSearch(owner.preview, owner.preview_box, insertion_index=1,
        valid=valid)
    owner.preview.on_webview_load = lambda widget=None, *args, **kwargs: owner.preview_search.loaded(widget, **kwargs)
    owner.preview_box._workspace_toolbar = owner.preview_toolbar
    owner.preview_box._native_reader_toolbar = owner.preview_toolbar
    owner.preview_box._native_reader_buttons = lambda: [owner.preview_edit, owner.preview_actions_button]
    owner.preview_box._native_reader_title = lambda: owner.document.name
