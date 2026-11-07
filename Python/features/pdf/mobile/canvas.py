"""PDF page gestures and compact navigation controls."""
import asyncio

import toga
from commonUtils.ui.native.image_canvas import ImageCanvas


class PDFCanvas(ImageCanvas):
    def __init__(self, *args, **kwargs):
        self.link_owner = self.link_reader = self.return_page = self.return_timer = None
        super().__init__(*args, page_axis='vertical',
            description='PDF page. Tap to toggle fullscreen; swipe up for next page, down for previous page. Hold in fullscreen to magnify.',
            **kwargs)

    def reading_viewport(self):
        """Store fit-relative zoom and an in-spread normalized focal point."""
        if self.image is None:
            return None
        zoom = round(self.zoom_scale, 3)
        if zoom <= 1.05:
            return None
        value = dict(zoom=zoom)
        if hasattr(self._impl, 'picture'):
            scroll = self._impl.native
            point, bounds, size = scroll.contentOffset, scroll.bounds.size, scroll.contentSize
            if size.width > 0 and size.height > 0:
                value['center'] = [
                    round(max(0, min(1, (offset + extent / 2) / length)), 5)
                    for offset, extent, length in ((point.x, bounds.width, size.width),
                                                   (point.y, bounds.height, size.height))]
        return value

    def restore_viewport(self, value):
        if self.image is None or not isinstance(value, dict):
            return
        zoom = value.get('zoom')
        if type(zoom) not in (float, int) or not 1.05 < zoom <= 6:
            return
        self.set_zoom(zoom)
        center = value.get('center')
        if (not hasattr(self._impl, 'picture') or not isinstance(center, list)
                or len(center) != 2 or any(type(v) not in (float, int) or not 0 <= v <= 1 for v in center)):
            return
        from rubicon.objc import CGPoint
        scroll = self._impl.native
        bounds, size = scroll.bounds.size, scroll.contentSize
        def offset(fraction, extent, length):
            return max(0, min(length - extent, fraction * length - extent / 2)) if length >= extent else (length - extent) / 2
        scroll.setContentOffset(CGPoint(offset(center[0], bounds.width, size.width),
                                        offset(center[1], bounds.height, size.height)), animated=False)

    def bind_links(self, owner, reader):
        self.link_owner, self.link_reader = owner, reader
        self.on_tap = self.follow_link
        self.return_page = None
        self.return_timer = None

    def link_alive(self):
        owner = self.link_owner
        return (owner is not None and owner.active_host and owner.crypt_reader is self.link_reader
                and owner.manager.active is owner
                and owner.session.id in owner.workspace.sessions
                and owner.app.native_host.state.destination == owner.presentation_destination)

    def clear_return(self):
        if self.return_timer is not None:
            self.return_timer.cancel()
            self.return_timer = None
        self.return_page = None
        if hasattr(self, 'return_box'):
            self.return_box.clear()

    def follow_link(self, x, y):
        if not self.link_alive() or self.link_owner.cloud_busy:
            return False
        navigation = self.link_reader.pdf_navigation
        from features.comics.mobile.composite import spread_geometry
        size, rects = spread_geometry([navigation.sizes[i] for i in navigation.indices], navigation.viewport)
        for index, (left, top, width, height) in zip(navigation.indices, rects):
            px, py = (x*size[0]-left)/width, (y*size[1]-top)/height
            for link in navigation.links.get(index, []):
                l, t, r, b = link['rect']
                if l <= px <= r and t <= py <= b:
                    self.link_owner.loop.create_task(self.jump_link(link['index']))
                    return True
        return False

    async def link_navigation_ready(self, owner, reader, page):
        # Saving reader progress also owns the document briefly, without
        # setting cloud_busy. Let that save finish before changing selection.
        progress = getattr(owner, '_provider_progress', None)
        if progress is not None and progress.worker is not None:
            await asyncio.wait({progress.task})
        return (self.link_alive() and self.link_owner is owner and self.link_reader is reader
                and not owner.cloud_busy and owner.provider_document().can_start()
                and reader.pdf_navigation.indices[0] == page)

    async def jump_link(self, index):
        if not self.link_alive() or self.link_owner.cloud_busy:
            return
        owner, reader = self.link_owner, self.link_reader
        previous = reader.pdf_navigation.indices[0]
        if not await self.link_navigation_ready(owner, reader, previous):
            return
        self.clear_return()
        await self.link_owner.move_private_page(index)
        if self.link_alive() and self.link_reader.pdf_navigation.indices[0] == index and index != previous:
            from toga.style import Pack
            self.return_page = (previous, index)
            button = toga.Button('Undo page jump', on_press=self.undo_link, style=Pack(height=44))
            self.return_box.add(button)
            self.return_timer = self.link_owner.loop.call_later(3, self.clear_return)

    async def undo_link(self, widget=None, **kwargs):
        if not self.link_alive() or self.link_owner.cloud_busy or self.return_page is None:
            return
        owner, reader = self.link_owner, self.link_reader
        previous, target = self.return_page
        if (await self.link_navigation_ready(owner, reader, target)
                and self.return_page == (previous, target)):
            self.clear_return()
            await owner.move_private_page(previous)

    def dispose(self):
        self.clear_return()
        self.link_owner = self.link_reader = None
        super().dispose()



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
        self.links = {}
        self._candidate = None
        from services.documents.page_visits import PageVisits
        self.visits = PageVisits()

    def commit(self, indices, viewport):
        """Publish link geometry and remember the displayed spread boundary."""
        candidate = self._candidate
        if candidate is None or candidate[:2] != (indices, viewport):
            raise ValueError('No loaded PDF spread matches the published pages.')
        _, _, self.sizes, self.links = candidate
        self._candidate = None
        self._use_layout(viewport)
        self.indices, self.viewport = indices, viewport
        self.visits.visit(indices[0])
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
        self._candidate = None
        self._use_layout(viewport)
        indices, data, sizes = self._load_spread(index, viewport)
        from features.pdf.links import safe_page_links
        links = {page: safe_page_links(self.document.data, page) for page in indices}
        self._candidate = indices, viewport, sizes, links
        return indices, data

    def _load_spread(self, index, viewport):
        from features.images.validation import image_dimensions
        first = self.document.page(index)
        sizes = {index: image_dimensions(first)}
        indices, data = (index,), [first]
        width, height = viewport
        if index + 1 < self._stops.get(index, self.document.count):
            second = self.document.page(index + 1)
            second_size = image_dimensions(second)
            ratios = [w / h for w, h in (sizes[index], second_size)]
            if width >= sum(ratios) * max(1, height):
                indices, data = (index, index + 1), [first, second]
                sizes[index + 1] = second_size
        return indices, data, sizes

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
            indices, _, _ = self._load_spread(index - 2, self.viewport)
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
