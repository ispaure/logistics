"""One compact, accessible sync shortcut on Workspaces."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import toga
from toga.style import Pack
from commonUtils.ui.native.icons import IconRenderer, IconSpec
from .control_icons import ICONS, tint_android


class SyncButton(toga.Button):
    def __init__(self, app):
        super().__init__(on_press=app.show_transfers, style=Pack(width=48, height=48, margin_left=8, font_size=16))
        self.renderer = IconRenderer({'transfers': IconSpec(*ICONS['transfers'])}, tint_android=tint_android)
        self.snapshot = None
        from .appearance import surface
        surface(self, background='transparent', foreground='text', outlined=False, eink_outlined=False)

    def update(self, busy, percentage, complete, *, notified=False):
        progress = None if percentage is None else max(0, min(100, round(percentage)))
        state = busy, progress, complete, notified
        if state == self.snapshot:
            return
        initial = self.snapshot is None
        self.snapshot = state
        if not (busy or notified):
            self.renderer.apply(self, 'transfers', 'Transfers', preserve_layout=not initial)
            self.refresh_native_item()
            return
        sweep = max(3, 360 * progress / 100) if busy and progress is not None else 100 if busy else 360
        lines = (((8, 8), (15, 8), (13, 6)), ((15, 8), (13, 10)),
                 ((16, 16), (9, 16), (11, 14)), ((9, 16), (11, 18)))
        label = (f'Syncing: {progress}% of known work. Open transfers' if progress is not None else
                 'Syncing. Open transfers') if busy else 'Sync finished. Open transfers' if complete else 'Sync stopped. Open transfers'
        self.renderer.icons['sync-progress'] = IconSpec('', '↻', lines,
            arcs=((2, 2, 22, 22, -90, sweep),), stroke_width=1.6, apple_vector=True)
        self.renderer.apply(self, 'sync-progress', label, preserve_layout=not initial)
        self.refresh_native_item()

    def refresh_native_item(self):
        if hasattr(self, '_ios_action_item'):
            from .ios_toolbar import bar_item
            bar_item(self)


def refresh(app, destination=None):
    if not getattr(app, 'active_host', False) or not hasattr(app, 'routes'):
        return
    destination = destination or app.native_host.state.destination
    if destination != 'files' or app.routes.screens['files']:
        return
    button = getattr(app, 'folder_transfers_button', None)
    if button is None or (button.parent is None and not hasattr(button, '_ios_action_item')):
        return
    busy = bool(getattr(app, 'transfer_busy', False))
    percentage = getattr(app, 'transfer_percentage', None)
    button.update(busy, percentage, getattr(app, 'transfer_complete', False),
                  notified=bool(getattr(app, 'transfer_notification', False)))
