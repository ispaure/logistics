"""Mobile PDF surface, explicit navigation history and compact controls."""
import asyncio

import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.ui.native.image_canvas import ImageCanvas

from .continuous import PDFScroll, page_ratios, render_page


class PDFCanvas(ImageCanvas):
    """Image-only artwork for the reader chrome and external display."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, page_axis='vertical', description='PDF page', **kwargs)


class PDFReaderCanvas(toga.Box):
    _external_document_page = True

    def __init__(self, owner, reader):
        from services.documents.mobile_views import document_webview
        from services.documents.storage import DocumentPolicy
        from types import SimpleNamespace
        from commonUtils.ui.native.private_webview import private_webview_supported
        self.owner, self.reader = owner, reader
        self.artwork = PDFCanvas()
        self.canvases = [self.artwork]
        self.on_page = owner.swipe_crypt_page
        self.on_toggle = owner.toggle_private_reading_mode
        self.return_page = self.return_timer = None
        self.return_box = toga.Box(style=Pack(direction=COLUMN))
        resource = SimpleNamespace(policy=DocumentPolicy(False, False)) if private_webview_supported() else None
        web = document_webview(resource, style=Pack(flex=1))
        self.scroll = PDFScroll(web, reader.pdf, reader.pdf_navigation.ratios, loop=owner.loop,
                                active=self.active, on_position=self.scrolled,
                                on_action=self.action, on_image=self.update_image)
        super().__init__(children=[web], style=Pack(direction=COLUMN, flex=1))

    @property
    def image(self):
        return self.artwork.image

    @image.setter
    def image(self, value):
        if value is None:
            self.scroll.suspend()
        else:
            self.artwork.image = value

    @property
    def magnifier_enabled(self):
        return bool(self.scroll.magnifier and self.scroll.magnifier[0])

    @magnifier_enabled.setter
    def magnifier_enabled(self, value):
        self.scroll.magnifier = [bool(value), self.artwork.magnifier_zoom]

    @property
    def zoom_scale(self):
        return (self.scroll.location or {}).get('zoom', 1)

    def set_zoom(self, value):
        self.scroll.set_zoom(value)

    def fit_page(self, widget=None, **kwargs):
        self.set_zoom(1)

    def reading_viewport(self):
        return self.scroll.location

    def active(self):
        owner = self.owner
        return (owner is not None and owner.crypt_reader is self.reader
                and owner.manager.active is owner and owner.app.visible_reader() == owner.session.id
                and owner.manager.available(owner.session.id)
                and not owner.app.screen_privacy.inactive
                and not owner.app.screen_privacy.resume_locked)

    def update_image(self, png):
        if png:
            from features.images.mobile.decoding import decode_page
            from features.images.validation import image_dimensions
            from toga.platform import get_factory
            size = image_dimensions(png)
            self.artwork.image = decode_page(png, size, size, get_factory().Image.__module__)
        else:
            self.artwork.image = None
        if self.active():
            from mobile.external_display import sync
            from mobile.ios_content_background import sync as sync_background
            sync(self.owner.app)
            sync_background(self.owner.app)

    def scrolled(self, index, location):
        if self.owner.cloud_busy:
            return
        self.scroll.magnifier = [self.magnifier_enabled, self.artwork.magnifier_zoom]
        navigation = self.reader.pdf_navigation
        if index != navigation.index:
            self.clear_return()
            navigation.index = index
            sync_pdf_selection(self.owner, index)
        progress = getattr(self.owner, '_provider_progress', None)
        if progress is not None:
            progress.capture_pdf(index, location)

    def page(self, direction):
        if self.on_page is not None:
            self.on_page(direction)

    def toggle_controls(self):
        if self.on_toggle is not None:
            self.on_toggle()

    def action(self, event):
        if 'target' in event:
            self.owner.loop.create_task(self.jump_link(event['target'], event['from']))
        elif 'magnification' in event:
            self.artwork.request_magnifier_zoom(event['magnification'])
        elif event.get('tap') and self.zoom_scale <= 1.05:
            self.toggle_controls()

    def clear_return(self):
        if self.return_timer is not None:
            self.return_timer.cancel()
            self.return_timer = None
        self.return_page = None
        self.return_box.clear()

    async def jump_link(self, index, previous):
        if not await self.link_ready():
            return
        owner = self.owner
        await owner.move_private_page(index)
        if self.active() and self.reader.pdf_navigation.index == index and index != previous:
            self.return_page = previous, index
            self.return_box.add(toga.Button('Undo page jump', on_press=self.undo_link, style=Pack(height=44)))
            self.return_timer = owner.loop.call_later(3, self.clear_return)

    async def link_ready(self):
        owner = self.owner
        if not self.active() or owner.cloud_busy:
            return False
        revision = self.scroll.revision
        progress = getattr(owner, '_provider_progress', None)
        if progress is not None and progress.worker is not None:
            await asyncio.wait({progress.task})
        return (self.active() and not owner.cloud_busy and revision == self.scroll.revision
                and owner.provider_document().can_start())

    async def undo_link(self, widget=None, **kwargs):
        target = self.return_page
        if target is not None and await self.link_ready() and self.return_page == target:
            self.clear_return()
            await self.owner.move_private_page(target[0])

    def dispose(self):
        self.clear_return()
        self.scroll.dispose()
        self.artwork.dispose()
        self.on_page = self.on_toggle = self.owner = self.reader = None


class PDFTools:
    """Compact page jump and text search, leaving the reading area clear."""
    def __init__(self, controls):
        from toga.style import Pack
        from toga.style.pack import COLUMN
        self.panel = toga.Box(children=controls, style=Pack(direction=COLUMN, margin_top=8))
        self.button = toga.Button('Pages & search', on_press=self.toggle, style=Pack(height=44))
        self.widget = toga.Box(children=[self.button], style=Pack(direction=COLUMN))

    def toggle(self, widget=None, **kwargs):
        if self.panel in self.widget.children:
            self.close()
        else:
            self.widget.add(self.panel)
            self.button.text = 'Hide pages & search'
        self.refresh_control()

    def close(self):
        if self.panel in self.widget.children:
            self.widget.remove(self.panel)
        self.button.text = 'Pages & search'
        self.refresh_control()

    def refresh_control(self):
        callback = getattr(self, 'on_state_change', None)
        if callback is not None:
            callback()


class PDFNavigation:
    """Track explicit destinations separately from viewport observations."""
    def __init__(self, document, *, cancelled=lambda: False):
        from services.documents.page_visits import PageVisits
        self.document = document
        self.ratios = page_ratios(document, cancelled=cancelled)
        self.index = 0
        self.visits = PageVisits()

    def load(self, index):
        return render_page(self.document, index, links=True)

    def next(self):
        return self.index + 1 if self.index + 1 < self.document.count else None

    def previous(self):
        return self.index - 1 if self.index else None


def sync_pdf_progress(view):
    navigation = view.crypt_reader.pdf_navigation
    index, count = navigation.index, navigation.document.count
    footer = view.page_footer
    footer.index = index
    if not getattr(footer.slider, 'tracking', False):
        footer.slider.value = index
    footer.set_progress_text(f'{index + 1}/{count}', f'Page {index + 1} of {count}')
    view.previous_page.enabled = index > 0
    view.next_page.enabled = navigation.next() is not None


def sync_pdf_selection(view, index):
    from mobile.provider_ui import private_label
    view._provider_displayed_index = index
    view.crypt_page.value = view.crypt_reader.labels[index]
    view.crypt_title.text = private_label(f'Page {index + 1} / {len(view.crypt_reader.labels)}')
    if hasattr(view, 'pdf_number') and not getattr(view.pdf_number, '_pdf_entering_page', False):
        view.pdf_number.value = str(index + 1)
    sync_pdf_progress(view)
    view.refresh_private_bookmarks()
