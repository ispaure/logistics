"""Shared reading layout and page commands; adapters own storage and privacy."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class ReadingFrame:
    def __init__(self, content, controls, *, margin=8):
        self.content, self.controls, self.margin = content, list(controls), margin
        self.widget = toga.Box(children=[*self.controls[:1], content, *self.controls[1:]],
                               style=Pack(direction=COLUMN, margin=margin, flex=1))
        self.widget._reading_frame = True
        self.immersive = False

    def set_immersive(self, immersive, *, comic):
        self.immersive = immersive
        for control in self.controls:
            if control in self.widget.children:
                self.widget.remove(control)
        if not immersive:
            self.widget.insert(0, self.controls[0])
            for control in self.controls[1:]:
                self.widget.add(control)
        self.widget.style.margin = 0 if immersive and comic else self.margin
        self.widget._comic_fullscreen = immersive and comic


def page_buttons(previous, next_page):
    return (toga.Button('Previous', on_press=previous, style=Pack(height=44, flex=1)),
            toga.Button('Next', on_press=next_page, style=Pack(height=44, flex=1)))


def schedule_swipe(owner, direction, *, position, count, right_to_left, busy, move):
    if busy or not owner.active_host or owner.session.id not in owner.workspace.sessions:
        return
    index = position + (-direction if right_to_left else direction)
    if not 0 <= index < count:
        return
    task = getattr(owner, '_comic_swipe_task', None)
    if task is None or task.done():
        owner._comic_swipe_task = owner.loop.create_task(move(index))
