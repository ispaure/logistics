"""Notes tree projection over the host's viewport-recycled native list."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, NONE, PACK


class NativeTreeRows:
    recycled = True

    def __init__(self, owner, list_factory):
        self.owner = owner
        self.epoch = 0
        self.closed = False
        self.tasks = set()
        actions = any(owner.library.supports(action) for action in ('rename', 'delete'))
        self.native_list = list_factory(on_select=self.select,
            primary_action='Actions for' if actions else None, on_primary_action=self.context,
            style=Pack(flex=1))
        self.native_list.tree_actions = self
        self.status = toga.Label('', style=Pack(display=NONE))
        self.widget = toga.Box(children=[self.native_list, self.status],
                               style=Pack(direction=COLUMN, flex=1))

    @property
    def style(self):
        return self.widget.style

    @property
    def vertical_position(self):
        get_position = getattr(self.native_list._impl, 'get_vertical_position', None)
        return get_position() if get_position is not None else 0

    @vertical_position.setter
    def vertical_position(self, position):
        set_position = getattr(self.native_list._impl, 'set_vertical_position', None)
        if set_position is not None:
            set_position(position)

    @property
    def children(self):
        return list(self.native_list.data)

    @property
    def drag_token(self):
        drag = getattr(self.owner, 'file_drag', None)
        return drag.token if drag is not None and self.owner.library.supports('rename') else None

    def active(self):
        if (self.closed or not self.owner.valid() or getattr(self.owner, 'rows', None) is not self
                or getattr(self.owner, 'panel_tab', None) not in ('Files', 'Search')):
            return False
        sidebar = getattr(self.owner, 'sidebar', None)
        if sidebar is None or not (sidebar.expanded or sidebar.side == 'files'):
            return False
        native = getattr(self.native_list._impl, 'native', None)
        if self.native_list.factory.DetailedList.__module__.startswith('toga_iOS.'):
            if native is None or native.window is None:
                return False
            while native is not None:
                if native.isHidden() or float(native.alpha) <= 0:
                    return False
                parent = native.superview
                native = parent() if callable(parent) else parent
            return True
        return native is None or (native.isAttachedToWindow() and native.isShown())

    def current(self, row):
        return (self.active() and row.epoch == self.epoch and 0 <= row.index < len(self.native_list.data)
                and self.native_list.data[row.index] is row)

    def add(self, *records):
        """Publish one complete lightweight source; native cells bind on demand."""
        self.end_drag()
        self.epoch += 1
        self.native_list.updating = True
        try:
            self.native_list.data = [dict(record, epoch=self.epoch, index=index)
                                     for index, record in enumerate(records)]
            self.select_path()
        finally:
            self.native_list.updating = False

    def message(self, value):
        if self.status.text != value:
            self.status.text = value
        display = PACK if value else NONE
        if self.status.style.display != display:
            self.status.style.display = display

    def select_path(self):
        index = next((i for i, row in enumerate(self.native_list.data)
                      if row.path == self.owner.selected_path), None)
        self.native_list.select_index(index)

    def spawn(self, coroutine):
        task = self.owner.host.loop.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def select(self, widget, **kwargs):
        # Capture synchronously, before another tap or a source replacement.
        if self.native_list.updating or not self.active():
            return
        row = self.native_list.selection
        if row is not None and self.current(row):
            self.spawn(self.activate(row))

    async def activate(self, row):
        if not self.current(row):
            return
        if row.page is not None:
            await self.owner.open_selected_note(row.page, row_path=row.path)
        elif row.folder and row.searching:
            await self.owner.reveal_folder(row.path)
        elif row.folder:
            await self.owner.toggle_folder(row.path)
        else:
            await self.owner.open_selected_note(row.path)

    def toggle(self, row):
        if self.current(row) and row.folder and row.tree_expanded is not None:
            self.spawn(self.expand(row))

    async def expand(self, row):
        if self.current(row):
            await self.owner.toggle_folder(row.path)

    def context(self, widget, row, **kwargs):
        if self.current(row):
            self.spawn(self.actions(row))

    async def actions(self, row):
        if self.current(row):
            await self.owner.file_actions(row.path)

    def start_drag(self, row):
        return bool(self.current(row) and self.drag_token and self.owner.file_drag.start(row.path))

    def can_drop(self, row):
        return bool(self.current(row) and row.folder and self.drag_token
                    and self.owner.file_drag.destination(row.path) is not None)

    def drop(self, row):
        return bool(self.can_drop(row) and self.owner.file_drag.drop(row.path))

    def end_drag(self):
        drag = getattr(self.owner, 'file_drag', None)
        if drag is not None:
            drag.end()

    def clear(self):
        self.epoch += 1
        self.native_list.clear()
        self.message('')

    def dispose(self):
        self.closed = True
        for task in tuple(self.tasks):
            task.cancel()
        self.end_drag()
        self.clear()
        self.native_list.tree_actions = None
