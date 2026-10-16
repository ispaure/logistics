"""Shared reading layout and page commands; adapters own storage and privacy."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .control_icons import icon_button, apply_icon
from .appearance import accessible_name


class ReadingFrame:
    def __init__(self, content, controls, *, margin=16):
        self.content, self.controls, self.margin = content, list(controls), margin
        self.widget = toga.Box(children=[*self.controls[:1], content, *self.controls[1:]],
                               style=Pack(direction=COLUMN, margin=margin, flex=1))
        self.widget._reading_frame = True
        self.widget._reading_frame_owner = self
        self.immersive = False

    def set_immersive(self, immersive, *, comic):
        self.immersive = immersive
        for child in self.content.children:
            if hasattr(child, 'magnifier_enabled'):
                child.magnifier_enabled = bool(immersive and comic)
        for control in self.controls:
            if control in self.widget.children:
                self.widget.remove(control)
        if not immersive:
            self.widget.insert(0, self.controls[0])
            for control in self.controls[1:]:
                self.widget.add(control)
        self.widget.style.margin = 0 if immersive and comic else self.margin
        self.widget._comic_fullscreen = immersive and comic
        self.widget._reader_fullscreen = immersive


def page_buttons(previous, next_page):
    return (icon_button('back', 'Previous page', on_press=previous),
            icon_button('forward', 'Next page', on_press=next_page))


class PageFooter:
    """Comic scrubbing commits on release; logical page commands stay unchanged."""
    def __init__(self, previous, following, move):
        self.previous, self.following, self.move = previous, following, move
        self.count, self.rtl = 0, False
        self.slider = toga.Slider(min=0, max=1, value=0, on_release=self.release,
                                  style=Pack(flex=1, height=48))
        accessible_name(self.slider, 'Comic page')
        self.spacer = toga.Box(style=Pack(flex=1))
        self.widget = toga.Box(style=Pack(direction=ROW))
        self.sync(comic=False, count=0, index=0)

    def sync(self, *, comic, count, index, right_to_left=False):
        self.count, self.index, self.rtl = count, index, comic and right_to_left
        apply_icon(self.previous, 'forward' if self.rtl else 'back', 'Previous page')
        apply_icon(self.following, 'back' if self.rtl else 'forward', 'Next page')
        children = [self.following if self.rtl else self.previous,
                    self.slider if comic else self.spacer,
                    self.previous if self.rtl else self.following]
        if list(self.widget.children) != children:
            for child in list(self.widget.children):
                self.widget.remove(child)
            self.widget.add(*children)
        self.slider.max = max(1, count - 1)
        self.slider.value = count - 1 - index if self.rtl else index
        self.slider.enabled = comic and count > 1

    async def release(self, widget, **kwargs):
        if not self.slider.enabled:
            return
        index = round(widget.value)
        try:
            await self.move(self.count - 1 - index if self.rtl else index)
        finally:
            self.slider.value = self.count - 1 - self.index if self.rtl else self.index


def schedule_swipe(owner, direction, *, position, count, right_to_left, busy, move):
    if busy or not owner.active_host or owner.session.id not in owner.workspace.sessions:
        return
    index = position + (-direction if right_to_left else direction)
    if not 0 <= index < count:
        return
    task = getattr(owner, '_comic_swipe_task', None)
    if task is None or task.done():
        owner._comic_swipe_task = owner.loop.create_task(move(index))
