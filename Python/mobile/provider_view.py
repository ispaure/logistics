"""Construct provider controls after the opening workflow has prepared document content."""
from pathlib import Path
import logging
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from .provider_ui import private_label, _MarkdownState


class ProviderView:
    """Unpublished controls until route admission transfers them to the session.

    Reader sources stay with the opening workflow, not this control draft.
    Presentation builders add format-specific fields before adoption.
    """
    _adopted = False
    _discarded = False

    def adopt(self, owner):
        if self._discarded or self._adopted:
            raise RuntimeError('Provider view ownership was already transferred or discarded.')
        owner._provider_markdown = getattr(self, '_provider_markdown', None)
        for name, value in vars(self).items():
            if owner._provider_markdown is not None and isinstance(getattr(type(owner), name, None), _MarkdownState):
                continue
            setattr(owner, name, value)
        self._adopted = True

    def discard(self):
        """Retire only unpublished controls; never close an acquired/prepared reader."""
        if self._adopted or self._discarded:
            return
        self._discarded = True
        for name in ('_provider_markdown', 'provider_epub_view', 'pdf_search',
                     'pdf_contents', 'provider_spread', 'crypt_text', 'crypt_image',
                     'crypt_actions_menu'):
            control = getattr(self, name, None)
            if control is not None:
                try:
                    control.dispose()
                except Exception:
                    # Retire the remaining controls without masking the opening failure.
                    logging.getLogger(__name__).exception('Could not retire unpublished %s', name)


class ProviderDocumentView:
    def __init__(self, owner):
        self.owner = owner

    def build(self, reader, copies, kind, content, *, progress=None):
        view = ProviderView()
        try:
            return self._build(view, reader, copies, kind, content, progress=progress)
        except BaseException:
            view.discard()
            raise

    def _build(self, view, reader, copies, kind, content, *, progress=None):
        owner = self.owner
        view.crypt_reader = reader
        view._crypt_reader_store = copies
        view.crypt_title = toga.Label(private_label(Path(reader.name).name), style=Pack(font_size=18))
        view.crypt_page = toga.Selection(items=reader.labels, style=Pack(height=44))
        view.crypt_page.value = reader.labels[0]
        view.crypt_read_page = toga.Button('Read selected page', on_press=owner.read_crypt_page, style=Pack(height=44))
        view.crypt_bookmarks = set()
        view.epub_session_bookmarks = set()
        if progress is not None:
            view._provider_progress = progress
            progress.restore(view)
        view.crypt_bookmark_button = toga.Button('Bookmark', on_press=owner.toggle_private_bookmark,
                                                enabled=not reader.editable, style=Pack(height=44))
        view.crypt_bookmark_selector = toga.Selection(items=['Bookmarks…'],
            on_change=owner.select_private_bookmark, enabled=not reader.editable, style=Pack(height=44))
        from commonUtils.ui.native.code_input import CodeInput
        from .font_scaling import bind, font_size
        view.crypt_text = CodeInput(loop=owner.loop, filename=reader.name, readonly=not reader.editable,
            highlighting=owner.preferences.values.get('android_eink') != 'true',
            on_change=owner.private_source_changed,
            style=Pack(flex=1, font_size=font_size(owner, reader.kind)))
        bind(owner, view.crypt_text, reader.kind)
        if getattr(reader, 'read_only', False):
            view.crypt_text.readonly = True
        from commonUtils.ui.native.image_canvas import ImageCanvas
        if reader.kind == '.pdf':
            from features.pdf.mobile.canvas import PDFCanvas
            view.crypt_image = PDFCanvas(on_page=owner.swipe_crypt_page,
                on_toggle=owner.toggle_private_reading_mode, style=Pack(flex=1))
        else:
            view.crypt_image = ImageCanvas(on_page=owner.swipe_crypt_page,
                page_swipes_at_edges=reader.kind in {'.cbz', '.zip'},
                on_toggle=owner.toggle_private_reading_mode, style=Pack(flex=1))
        from .magnifier import bind
        bind(owner, view.crypt_image)
        view.crypt_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
        owner._show_crypt_content(kind, content, view=view)
        view.crypt_save = toga.Button('Save', on_press=owner.save_crypt, enabled=reader.editable and not getattr(reader, 'read_only', False), style=Pack(height=44))
        view.crypt_read_page.enabled = not reader.editable
        read_only = getattr(reader, 'read_only', False)
        mutation_controls = [] if read_only else ([view.crypt_save,
            toga.Button('Save As…', on_press=owner.show_crypt_save_as, style=Pack(height=44))]
            if reader.editable else [toga.Button('Edit metadata…', on_press=owner.edit_crypt_metadata, style=Pack(height=44))])
        view.crypt_view = toga.Box(children=[view.crypt_title, view.crypt_page, view.crypt_read_page, view.crypt_content,
            *mutation_controls,
            toga.Button('Open…', on_press=owner.show_editor_open, style=Pack(height=44)),
            toga.Label(private_label('Remote preview · Read-only' if read_only else
                ('Edits stay in memory until saved to the selected local file.' if reader.editable else 'Reading position stays in this session'))),
            toga.Button('Cancel request', on_press=owner.cancel_cloud, style=Pack(height=44)),
            *([] if read_only or not reader.editable else [toga.Button('Discard changes and close', on_press=owner.discard_crypt, style=Pack(height=44))]),
            toga.Button('Close private reader', on_press=owner.close_crypt, style=Pack(height=44))],
            style=Pack(direction=COLUMN, flex=1, margin=12))
        owner.compact_private_view(view)
        return view
