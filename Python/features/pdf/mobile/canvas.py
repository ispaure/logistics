"""PDF page gestures and compact navigation controls."""
import toga
from commonUtils.ui.native.image_canvas import ImageCanvas


class PDFCanvas(ImageCanvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, page_axis='vertical',
            description='PDF page. Tap to toggle fullscreen; swipe up for next page, down for previous page. Hold in fullscreen to magnify.',
            **kwargs)


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
    """Bounded page-pair loading; keep the selected page as the spread anchor."""
    def __init__(self, document):
        self.document = document
        self.indices = (0,)
        self.viewport = (1, 1)
        self.sizes = {}
        self._spread_starts = {}
        self._stops = {}
        self._layout = None

    def commit(self, indices, viewport):
        """Remember published boundaries so Back retraces the visible spreads."""
        self._use_layout(viewport)
        self.indices, self.viewport = indices, viewport
        # A direct jump can repartition a previously visited pair. Retire
        # overlapping history so Back cannot reuse an obsolete pair boundary.
        for end, start in list(self._spread_starts.items()):
            if start <= indices[-1] and end > indices[0]:
                del self._spread_starts[end]
        self._spread_starts[indices[-1] + 1] = indices[0]

    def _use_layout(self, viewport):
        if self._layout != viewport:
            self._spread_starts.clear()
            self._stops.clear()
            self._layout = viewport

    def load(self, index, viewport):
        from features.images.validation import image_dimensions
        self._use_layout(viewport)
        first = self.document.page(index)
        self.sizes[index] = image_dimensions(first)
        indices, data = (index,), [first]
        width, height = viewport
        if index + 1 < self._stops.get(index, self.document.count):
            second = self.document.page(index + 1)
            self.sizes[index + 1] = image_dimensions(second)
            ratios = [w / h for w, h in (self.sizes[index], self.sizes[index + 1])]
            if width >= sum(ratios) * max(1, height):
                indices, data = (index, index + 1), [first, second]
        return indices, data

    def next(self):
        target = self.indices[-1] + 1
        return target if target < self.document.count else None

    def previous(self):
        self._use_layout(self.viewport)
        index = self.indices[0]
        if index == 0:
            return None
        if index in self._spread_starts:
            return self._spread_starts[index]
        if index >= 2:
            indices, _ = self.load(index - 2, self.viewport)
            if len(indices) == 2:
                return index - 2
        # After a direct jump, the preceding page may otherwise pair with the
        # current page. Keep this boundary on subsequent layout refreshes too.
        self._stops[index - 1] = index
        return index - 1


def pdf_viewport(owner):
    width, height = owner.private_comic_viewport()
    # Before its first native layout the canvas has no measured height. Do not
    # mistake that transient one-point allocation for a very wide reading pane.
    return width, height if height > 1 else max(1, owner.main_window.size.height)


def watch_pdf_layout(owner):
    """Use the same resize/zoom-aware invalidation loop as comic spreads."""
    reader = owner.crypt_reader
    task = getattr(owner, '_provider_layout_task', None)
    if task is not None and not task.done():
        return
    from features.comics.mobile.presentation import watch_layout
    owner._provider_layout_task = owner.loop.create_task(watch_layout(
        alive=lambda: owner.crypt_reader is reader and owner.active_host,
        available=lambda: not owner.cloud_busy and owner.manager.active is owner,
        viewport=lambda: pdf_viewport(owner),
        view=lambda: owner.crypt_image,
        reload=owner.read_crypt_page,
        changed=owner.format_services.layout_changed(),
        initial=reader.pdf_navigation.viewport))


def sync_pdf_progress(view):
    navigation = view.crypt_reader.pdf_navigation
    first, last = navigation.indices[0] + 1, navigation.indices[-1] + 1
    count = view.crypt_reader.pdf.count
    pages = str(first) if first == last else f'{first}–{last}'
    view.page_footer.set_progress_text(f'{pages}/{count}', f'Pages {pages} of {count}')
    view.next_page.enabled = navigation.next() is not None
