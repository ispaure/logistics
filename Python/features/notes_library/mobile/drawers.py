"""Compact Notes Library drawers, with persistent Files on wide allocations."""
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable
import toga
from toga.style import Pack
from toga.style.pack import ROW
from . import drawer_gestures, drawer_motion


@dataclass(frozen=True)
class DrawerHost:
    """Native window and presentation capabilities supplied by the mobile host."""
    loop: object
    window: Callable
    division: Callable
    overlay: Callable
    surface: Callable
    sync_bottom: Callable
    opening_blocked: Callable
    eink: Callable


class NotesDrawers:
    expanded = False

    def __init__(self, files, article, links, *, host):
        self.host, self.sidebar, self.detail, self.links = host, files, article, links
        self.view = toga.Box(children=[article], style=Pack(direction=ROW, flex=1))
        self.policy = SimpleNamespace(sidebar_width=320, gap=0)
        self.overlay = None
        self.action_choice = None
        self.action_overlay = None
        self.side = None
        self.wide = False
        self.wide_files_open = True
        self.files_bottom_extension = 0
        self.gestures = []
        self.opening_gestures = []
        self.retiring = []
        self.open_links = self.show_links
        self.on_close = lambda: None
        self.on_change = lambda: None
        for panel in (files, links):
            panel.hide = self.show_detail
            panel.overlay = None
            panel.overlay_height = 480

    @property
    def sidebar_open(self):
        return self.side is not None

    def reflow(self, width):
        drawer_gestures.install_opening_swipes(self)
        fold = self.host.division(self.view)
        vertical_fold = fold is not None and fold.vertical
        self.wide = vertical_fold or width >= 840  # 320 for Files, at least 520 for the document.
        # The host passes the document width minus its 24-unit inset. Leave
        # at least 44 units opposite the drawer for outside dismissal.
        drawer_width = min(320, max(1, width - 32))
        # UIKit reports the crease and its interaction margins in this row's
        # coordinates, including any offset from a system bar or safe area.
        files_width, gap = (fold.x, fold.width) if vertical_fold else (drawer_width, 0)
        previous_gap = self.policy.gap

        def apply():
            self.policy.sidebar_width = files_width
            self.policy.gap = gap
            if self.side != 'files':
                self.sidebar.style.width = files_width
            self.links.style.width = drawer_width
            self.view.style.gap = gap
            self.layout_files()

        if ((vertical_fold or previous_gap)
                and (self.expanded or (self.wide and self.wide_files_open))
                and (files_width, gap) != (self.policy.sidebar_width, previous_gap)):
            drawer_motion.resize_panes(self.view, apply)
        else:
            apply()
        if self.overlay is not None:
            self.overlay.reposition()
        if self.action_overlay is not None:
            self.action_overlay.reposition()

    def layout_files(self):
        expanded = self.wide and self.wide_files_open
        if expanded == self.expanded:
            return
        if self.side == 'files':
            self.show_detail()
            self.finish_dismissals()
        self.expanded = expanded
        self.extend_files_bottom(self.files_bottom_extension)
        if expanded:
            self.sidebar.style.width = self.policy.sidebar_width
            self.sidebar.style.flex = 0
            self.view.insert(0, self.sidebar)
        else:
            self.view.remove(self.sidebar)
            self.sidebar.style.flex = 1

    def set_files_scrolls(self, *scrolls):
        self.sidebar._bottom_scrolls = scrolls

    def extend_files_bottom(self, extension):
        self.files_bottom_extension = extension
        margin = -extension if self.expanded else 0
        if self.sidebar.style.margin_bottom == margin:
            return False
        return self.host.sync_bottom(self.sidebar, inset=-margin)

    def toggle(self, widget=None, **kwargs):
        if self.expanded:
            self.wide_files_open = False
            self.layout_files()
            self.on_change()
        elif self.side == 'files':
            self.show_detail()
        else:
            self.show_sidebar()

    def show_sidebar(self):
        self.show('files')

    def show_links(self):
        self.show('links')

    def show(self, side):
        if self.host.opening_blocked():
            return
        if side == 'files' and self.wide:
            self.show_detail()
            self.wide_files_open = True
            self.layout_files()
            self.on_change()
            return
        if self.side == side:
            return
        self.show_detail()
        self.finish_dismissals()
        self.side = side
        self.on_change()
        panel = self.sidebar if side == 'files' else self.links
        if side == 'files':
            del panel.style.width
        self.overlay = self.host.overlay(
            panel, self.view, leading=side == 'files', full_height=True,
            label='Files' if side == 'files' else 'Links', dim=True, edge_panel=True,
            android_radius=8, width_limit=352 if side == 'files' else 320,
            opposite_gutter=28 if side == 'files' else None)
        self.overlay.chapter_owner = self.view
        panel.overlay = self.overlay
        drawer_gestures.install_dismiss_swipe(self, panel)
        drawer_motion.slide_in(self.overlay, -1 if side == 'files' else 1, eink=self.host.eink())

    async def choose_action(self, dialog, window):
        drawer = self.overlay
        backend = type(self.sidebar._impl).__module__
        if drawer is None or not backend.startswith(('toga_iOS.', 'toga_android.')):
            return await window.dialog(dialog)
        if self.action_choice is not None:
            return 'cancel'

        result = self.action_choice = self.host.loop.create_future()
        def finish(value):
            if not result.done():
                result.set_result(value)

        surface = self.host.surface
        content = toga.Box(style=Pack(direction='column', margin=12))
        content.add(toga.Label(dialog.title, style=Pack(font_weight='bold', margin_bottom=4)),
                    toga.Label(dialog.message, style=Pack(margin_bottom=8)))
        for label, value, role in dialog.choices:
            def select(widget, value=value, **kwargs):
                finish(value)
            content.add(surface(toga.Button(label, on_press=select, style=Pack(height=44)),
                                    radius=8, background='transparent',
                                    foreground='destructive' if role == 2 else 'text', outlined=False))
        panel = toga.ScrollContainer(content=content, horizontal=False)
        panel.overlay_height = 76 + 44 * len(dialog.choices)
        panel.hide = lambda: finish('cancel')
        surface(panel, radius=12, background='surface', outlined=False)
        if drawer.outside_tap is not None:
            drawer.outside_tap.enabled = False
        choice = None
        try:
            choice = self.action_overlay = self.host.overlay(
                panel, self.view, dim=True, centered=True, label='File actions', android_radius=12)
            return await result
        finally:
            if choice is not None:
                choice.close()
            if drawer.outside_tap is not None:
                drawer.outside_tap.enabled = True
            self.action_choice = self.action_overlay = None

    def cancel_action(self):
        if self.action_choice is not None and not self.action_choice.done():
            self.action_choice.set_result('cancel')

    def swipe(self, direction):
        if self.action_choice is not None:
            return False
        if (self.side == 'files' and direction < 0) or (self.side == 'links' and direction > 0):
            self.show_detail()
            return True
        return False

    def open_swipe(self, direction):
        if self.side is not None or not drawer_gestures.opening_swipes_allowed(self):
            return False
        if direction > 0:
            if self.expanded:
                return False
            self.show_sidebar()
        else:
            self.open_links()
        return True

    def finish_dismissals(self):
        for overlay, handle in self.retiring:
            handle.cancel()
            overlay.close()
        self.retiring.clear()

    def dispose(self):
        drawer_gestures.clear_opening_swipes(self)
        self.show_detail()
        self.finish_dismissals()

    def refresh_gestures(self):
        # Both native backends observe the overlay container, so replacing
        # rows does not require replacing the active recognizer/touch stream.
        if self.overlay is not None and not self.gestures:
            drawer_gestures.install_dismiss_swipe(self, self.sidebar if self.side == 'files' else self.links)

    def show_detail(self):
        self.cancel_action()
        if self.side is not None:
            self.on_close()
        self.side = None
        self.on_change()
        drawer_gestures.clear_dismiss_swipes(self)
        overlay, self.overlay = self.overlay, None
        if overlay is not None:
            overlay.panel.overlay = None
            duration = drawer_motion.slide_out(overlay, -1 if overlay.leading else 1, eink=self.host.eink())
            if duration:
                def finish():
                    overlay.close()
                    self.retiring.remove((overlay, handle))
                handle = self.host.loop.call_later(duration, finish)
                self.retiring.append((overlay, handle))
            else:
                overlay.close()
