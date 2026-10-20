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
        full_page = comic or image
        for child in self.content.children:
            if hasattr(child, 'magnifier_enabled'):
                child.magnifier_enabled = bool(immersive and full_page)
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
    """Comic scrubbing commits on release; logical page commands stay unchanged."""
    def __init__(self, previous, following, move, *, compact=False):
        self.previous, self.following, self.move = previous, following, move
        self.compact = compact
        self.count, self.rtl = 0, False
        self.slider = toga.Slider(min=0, max=1, value=0, on_release=self.release,
                                  style=Pack(flex=1, height=48))
        accessible_name(self.slider, 'Comic page')
        self.spacer = toga.Label('', style=Pack(flex=1, text_align='center', font_size=12, margin_top=14))
        self.widget = toga.Box(style=Pack(direction=ROW))
        self.sync(comic=False, count=0, index=0)

    def sync(self, *, comic, count, index, right_to_left=False):
        self.count, self.index, self.rtl = count, index, comic and right_to_left
        apply_icon(self.previous, 'forward' if self.rtl else 'back', 'Previous page')
        apply_icon(self.following, 'back' if self.rtl else 'forward', 'Next page')
        children = [self.following if self.rtl else self.previous,
                    self.slider if comic else self.spacer,
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
        self.slider.enabled = comic and count > 1
        self.spacer.text = f'{index + 1} / {count}' if count else ''

    def chapter_progress(self, index, count, offset, length):
        percent = round(100 * min(max(0, offset), length) / length) if length else 0
        self.spacer.text = f'Chapter {index + 1}/{count} · {percent}%'

    async def release(self, widget, **kwargs):
        if not self.slider.enabled:
            return
        index = round(widget.value)
        try:
            await self.move(self.count - 1 - index if self.rtl else index)
        finally:
            self.slider.value = self.count - 1 - self.index if self.rtl else self.index


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
