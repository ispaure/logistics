"""One compact, accessible sync shortcut on main destinations only."""
import toga
from toga.style import Pack
from toga.style.pack import ROW, CENTER
from commonUtils.ui.native.icons import IconRenderer, IconSpec
from .control_icons import tint_android


class SyncButton(toga.Button):
    def __init__(self, app):
        super().__init__(on_press=app.show_transfers, style=Pack(width=48, height=48))
        self.renderer = IconRenderer({}, tint_android=tint_android)
        self.snapshot = None
        from .appearance import surface
        surface(self, background='transparent', foreground='text', outlined=False)

    def update(self, busy, percentage, complete, phase):
        progress = None if percentage is None else max(0, min(100, round(percentage)))
        state = busy, progress, complete, phase if busy and progress is None else 0
        if state == self.snapshot:
            return
        initial = self.snapshot is None
        self.snapshot = state
        start = -90 if progress is not None or not busy else phase * 30 - 90
        sweep = max(3, 360 * progress / 100) if busy and progress is not None else 100 if busy else 360
        lines = (((8, 8), (15, 8), (13, 6)), ((15, 8), (13, 10)),
                 ((16, 16), (9, 16), (11, 14)), ((9, 16), (11, 18)))
        label = (f'Syncing: {progress}% of known work. Open transfers' if progress is not None else
                 'Syncing. Open transfers') if busy else 'Sync finished. Open transfers' if complete else 'Sync stopped. Open transfers'
        self.renderer.icons['sync-progress'] = IconSpec('', '↻', lines,
            arcs=((2, 2, 22, 22, start, sweep),), stroke_width=1.6, apple_vector=True)
        self.renderer.apply(self, 'sync-progress', label, preserve_layout=not initial)


def status_host(app, destination):
    """Use retained root content, never document/toolbars or split detail panes."""
    if destination == 'home':
        return getattr(app, '_home_status_row', None), True
    if destination == 'documents':
        return getattr(getattr(app, 'documents_sections', None), 'content', None), False
    if destination == 'files':
        view = getattr(app, 'folder_picker_view', None)
        return getattr(getattr(view, '_workspace_frame', None), 'main', view), False
    if destination == 'chat':
        return getattr(app, 'chat_header', None), True
    return getattr(getattr(app, 'settings_navigation', None), '_menu', None), False


def refresh(app, destination=None):
    pending = getattr(app, '_sync_status_tick', None)
    if pending is not None:
        pending.cancel()
        app._sync_status_tick = None
    if not getattr(app, 'active_host', False) or not hasattr(app, 'routes'):
        return
    busy = bool(getattr(app, 'transfer_busy', False))
    visible = busy or getattr(app, 'transfer_notification', False)
    destination = destination or app.native_host.state.destination
    controls = app.__dict__.setdefault('_sync_status_controls', {})
    # Remove every hidden control as well, so no timers or stale status survive
    # navigation into a document or replacement of a lazy root.
    for key, (host, row, button, inline) in list(controls.items()):
        current, _ = status_host(app, key)
        if not visible or key != destination or app.routes.screens[key] or current is not host:
            mounted = button if inline else row
            if mounted.parent is not None:
                mounted.parent.remove(mounted)
            if current is not host:
                del controls[key]
    if not visible or app.routes.screens[destination]:
        return
    host, inline = status_host(app, destination)
    if host is None:
        return
    if destination not in controls:
        button = SyncButton(app)
        row = toga.Box(children=[toga.Box(style=Pack(flex=1)), button],
                       style=Pack(direction=ROW, align_items=CENTER)) if not inline else None
        controls[destination] = host, row, button, inline
    _, row, button, _ = controls[destination]
    mounted = button if inline else row
    if mounted.parent is None:
        host.add(button) if inline else host.insert(0, row)
    percentage = getattr(app, 'transfer_percentage', None)
    phase = int(app.loop.time() * 5) % 12
    button.update(busy, percentage, getattr(app, 'transfer_complete', False), phase)
    if busy and percentage is None and app.preferences.values.get('android_eink') != 'true':
        # Only the visible main tab animates; known progress redraws on updates.
        app._sync_status_tick = app.loop.call_later(.2, refresh, app)
