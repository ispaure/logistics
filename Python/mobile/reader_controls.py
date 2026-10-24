"""Shared reading layout and page commands; adapters own storage and privacy."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .control_icons import icon_button, apply_icon
from .appearance import accessible_name


# One comic menu contract; storage adapters only supply supported callbacks.
COMIC_COMMANDS = (
    ('pages', 'Comic pages…'), ('appearance', 'Appearance…'),
    ('reading_mode', 'Reading mode'), ('fit', 'Fit comic page'),
    ('metadata', 'Edit metadata…'), ('info', 'Info…'),
    ('close', 'Close comic'),
)


def comic_actions(**callbacks):
    return [(label, callbacks[key]) for key, label in COMIC_COMMANDS if callbacks.get(key) is not None]


def provider_comic_path(copies, reader):
    """Describe the opened location without loading configs or retaining names."""
    from pathlib import Path
    key = reader.key
    if getattr(copies, 'remote_storage', False):
        return f'{copies.remote}:{key}'
    provider = getattr(copies, 'provider', None)
    if provider is not None and getattr(provider, 'private', False):
        return f"LocalCrypt: {getattr(provider, 'remote', '')}/{key}"
    path = getattr(getattr(reader, 'source', None), 'path', None)
    if path is not None and Path(path).is_absolute():
        return str(path)
    if hasattr(copies, '_data'):
        return str(copies._data(key))
    return str(Path(copies.root) / key)


def comic_pages(selector, back):
    return toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
        toga.Label('Comic pages', style=Pack(font_size=20, margin_bottom=8)), selector,
        toga.Button('Return to reading', on_press=back, style=Pack(height=48))],
        style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))


class ComicHeader:
    """File navigation above the page; page navigation remains in the footer."""
    def __init__(self, more, *, previous=None, following=None):
        self.busy = False
        self.supported = previous is not None, following is not None
        def handler(callback):
            async def switch(widget=None, **kwargs):
                if callback is None or self.busy:
                    return
                self.busy = True
                self.sync(*self.available)
                try:
                    import inspect
                    result = callback()
                    if inspect.isawaitable(result):
                        await result
                finally:
                    self.busy = False
                    self.sync(*self.available)
            return switch
        self.previous = icon_button('previous_comic', 'Previous comic', on_press=handler(previous))
        self.following = icon_button('next_comic', 'Next comic', on_press=handler(following))
        self.sync(previous is not None, following is not None)
        self.widget = toga.Box(children=[toga.Box(style=Pack(flex=1)),
            self.previous, self.following, more], style=Pack(direction=ROW))

    def sync(self, previous, following):
        self.available = previous and self.supported[0], following and self.supported[1]
        self.previous.enabled = self.available[0] and not self.busy
        self.following.enabled = self.available[1] and not self.busy


class ReadingFrame:
    def __init__(self, content, controls, *, margin=16, restore=None, top_controls=1):
        self.content, self.controls, self.margin = content, list(controls), margin
        self.top_controls = top_controls
        self.restore = restore
        self.widget = toga.Box(children=[*self.controls[:top_controls], content, *self.controls[top_controls:]],
                               style=Pack(direction=COLUMN, margin=margin, flex=1))
        self.widget._reading_frame = True
        self.widget._reading_frame_owner = self
        self.immersive = False

    def set_immersive(self, immersive, *, comic, image=False):
        self.immersive = immersive
        for container, control in getattr(self, 'side_controls', ()):
            if immersive and control in container.children:
                container.remove(control)
            elif not immersive and control not in container.children:
                container.add(control)
        full_page = comic or image
        def magnifier(widget):
            if hasattr(widget, 'magnifier_enabled'):
                widget.magnifier_enabled = bool(immersive and full_page)
            for child in widget.children:
                magnifier(child)
        magnifier(self.content)
        for control in self.controls:
            if control in self.widget.children:
                self.widget.remove(control)
        if not immersive:
            for index, control in enumerate(self.controls[:self.top_controls]):
                self.widget.insert(index, control)
            for control in self.controls[self.top_controls:]:
                self.widget.add(control)
        if self.restore is not None:
            if self.restore in self.widget.children:
                self.widget.remove(self.restore)
            if immersive and not full_page:
                self.widget.add(self.restore)
        self.widget.style.margin = 0 if immersive and full_page else self.margin
        self.widget._comic_fullscreen = immersive and full_page
        self.widget._reader_fullscreen = immersive


def page_buttons(previous, next_page):
    return (icon_button('back', 'Previous page', on_press=previous),
            icon_button('forward', 'Next page', on_press=next_page))


class PageFooter:
    """Shared page/chapter scrubbing; publish movement only on release."""
    def __init__(self, previous, following, move, *, compact=False, status=None, unit='page', vertical=False):
        self.previous, self.following, self.move = previous, following, move
        self.compact = compact
        self.vertical = vertical
        self.status = status
        self.unit = unit
        self.count, self.rtl = 0, False
        self.book_boundaries = None
        self.book_seek = None
        self.book_fraction = 0
        if vertical:
            from .reader_progress import VerticalPageSlider
            self.slider = VerticalPageSlider(on_release=self.release, style=Pack(flex=1, width=44))
        else:
            self.slider = toga.Slider(min=0, max=1, value=0, on_release=self.release,
                                      style=Pack(flex=1, height=48))
        accessible_name(self.slider, 'Chapter position' if unit == 'chapter' else 'Page position')
        self.spacer = toga.Label('', style=Pack(width=92, text_align='center', font_size=10))
        self.badge = toga.Box(children=[self.spacer], style=Pack(direction=COLUMN, width=104, height=28,
            align_items='center', justify_content='center', margin_left=6, margin_right=2))
        from .appearance import surface
        surface(self.spacer, background='transparent', foreground='text')
        surface(self.badge, radius=14, background='alternate')
        self.widget = toga.Box(style=Pack(direction=COLUMN if vertical else ROW, width=56 if vertical else toga.style.pack.NONE, align_items='center', margin_left=4, margin_right=4))
        from .reader_progress import style_slider
        style_slider(self.slider)
        self.sync(comic=False, count=0, index=0)

    def sync(self, *, comic, count, index, right_to_left=False):
        self.count, self.index, self.rtl = count, index, comic and right_to_left
        from .appearance import surface
        for button, icon, label in ((self.previous, 'forward' if self.rtl else 'back', 'Previous page'),
                                    (self.following, 'back' if self.rtl else 'forward', 'Next page')):
            apply_icon(button, icon, label, size=18)
            surface(button, radius=24, background='transparent', foreground='text')
        if self.vertical:
            apply_icon(self.previous, 'up', 'Previous page', size=18)
            apply_icon(self.following, 'down', 'Next page', size=18)
        children = [self.following if self.rtl else self.previous,
                    self.slider, self.badge,
                    self.previous if self.rtl else self.following]
        if self.compact:
            children = ([] if hasattr(self.previous, '_native_reader_item') else
                        [self.previous, self.following])
        if list(self.widget.children) != children:
            for child in list(self.widget.children):
                self.widget.remove(child)
            self.widget.add(*children)
        self.slider.max = max(1, count - 1)
        self.slider.value = count - 1 - index if self.rtl else index
        self.slider.enabled = count > 1
        progress = f'{index + 1}/{count}' if count else '—'
        if comic and self.status is not None and self.status.text.startswith('Page '):
            progress = self.status.text[5:].split(' · Right-to-left')[0]
        self.set_progress_text(progress, f'{self.unit.title()} {progress}')

    def set_progress_text(self, text, label):
        self.spacer.text = text.replace('/', '\n/') if self.vertical else text
        self.badge.style.width = 48 if self.vertical else max(52, min(120, 20 + 7 * len(text)))
        self.spacer.style.width = self.badge.style.width - 12
        accessible_name(self.spacer, label)

    def set_book(self, book, seek):
        from features.books.locations import book_boundaries
        self.book_boundaries = book_boundaries(book)
        self.book_seek = seek
        accessible_name(self.slider, 'Whole book position')

    def chapter_progress(self, index, count, offset, length):
        fraction = min(1, max(0, offset / length)) if length else 0
        boundaries = self.book_boundaries
        start, end = (boundaries[index:index + 2] if boundaries is not None
                      else (index / count, (index + 1) / count))
        self.book_fraction = start + (end - start) * fraction
        self.slider.max = 1
        self.slider.value = self.book_fraction
        self.slider.enabled = count > 0
        percent = round(100 * self.book_fraction)
        self.set_progress_text(f'{percent}% · {index + 1}/{count}',
                               f'Chapter {index + 1} of {count}, {percent}% through book')

    async def release(self, widget, **kwargs):
        if not self.slider.enabled:
            return
        try:
            if self.book_seek is not None:
                from features.books.locations import book_location
                await self.book_seek(*book_location(self.book_boundaries, widget.value))
            else:
                index = round(widget.value)
                await self.move(self.count - 1 - index if self.rtl else index)
        finally:
            self.slider.value = (self.book_fraction if self.book_seek is not None else
                                 self.count - 1 - self.index if self.rtl else self.index)


def schedule_swipe(owner, direction, *, right_to_left, busy, move, position=None, count=None):
    """Queue one live-session gesture, using spread steps or absolute pages."""
    if busy or not owner.active_host or owner.session.id not in owner.workspace.sessions:
        return
    target = -direction if right_to_left else direction
    if position is not None:
        target += position
        if not 0 <= target < count:
            return
    task = getattr(owner, '_comic_swipe_task', None)
    if task is None or task.done():
        owner._comic_swipe_task = owner.loop.create_task(move(target))
