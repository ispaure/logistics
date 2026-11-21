"""Local File Browser controls and viewport-owned thumbnails."""
from functools import partial
from threading import Event

import toga
from toga.style import Pack
from toga.style.pack import ROW

from .browser_ui import FileBrowser, browser_command
from .control_icons import apply_icon, icon_button


class LocalFileBrowser(FileBrowser):
    def __init__(self, **kwargs):
        self.thumbnails = None
        self._previews_visible = False
        self._preview_update = None
        self._preview_jobs = {}
        self._preview_completed = set()
        self._tile_previews = {}
        self._mode_anchor = None
        super().__init__(**kwargs)
        self.view_switch = browser_command(icon_button('file_tiles', 'Show tiles', on_press=self.switch_view))

    def configure_previews(self, source):
        previous = self.thumbnails
        if previous is not None and (previous.provider is not source.provider
                                     or previous.password != source.password):
            self.icons.clear()
            self.work.decoded.clear()
        self._reset_previews()
        self.thumbnails = source

    def set_previews_visible(self, visible):
        if self._previews_visible != visible:
            self._previews_visible = visible
            if visible:
                self._schedule_previews()
            else:
                self._reset_previews()

    def pause_search_work(self):
        self.set_previews_visible(False)
        if self.thumbnails is not None and self.thumbnails.private:
            self._clear_private_previews()
        super().pause_search_work()

    def _clear_private_previews(self):
        self.icons.clear()
        self.work.decoded.clear()
        for row in self._list_thumbnail_rows.values():
            row.thumbnail = False
            row.icon = self.presentation.file_icon(row.folder)
        self._list_thumbnail_rows.clear()
        for preview, box, placeholder in self._tile_previews.values():
            preview.image = None
            if preview.parent is box:
                box.remove(preview)
                box.add(placeholder)

    def _reset_previews(self):
        if self._preview_update is not None:
            self._preview_update.cancel()
            self._preview_update = None
        for cancelled in self._preview_jobs.values():
            cancelled.set()
        self._preview_completed.clear()

    def stop(self):
        self.set_previews_visible(False)
        self._reset_previews()
        self.thumbnails = self.details = None
        self._mode_anchor = None
        super().stop()

    def render(self):
        self._reset_previews()
        super().render()
        self._schedule_previews()

    def switch_view(self, widget=None, **kwargs):
        (self.show_tiles if self.mode == 'List' else self.show_list)()

    def show_list(self, widget=None, **kwargs):
        self._show_mode('List')

    def show_tiles(self, widget=None, **kwargs):
        self._show_mode('Tiles')

    def _show_mode(self, mode):
        if self.closed or self.mode == mode:
            return
        self.dismiss_item_menu()
        if self.mode == 'List':
            visible = self._visible_rows()
            index = visible[0] if visible else 0
            entries = self._list_entries
        else:
            index = int(self.vertical_position / self.TILE_ROW_HEIGHT) * 2
            entries = self._tile_entries
            if self._mode_anchor is not None and index + 1 < len(entries):
                if entries[index + 1].identity == self._mode_anchor:
                    index += 1
        anchor = entries[index].identity if 0 <= index < len(entries) else None
        self._mode_anchor = anchor if mode == 'Tiles' else None
        self.mode = mode
        self.render()
        icon, label = ('contents', 'Show rows') if mode == 'Tiles' else ('file_tiles', 'Show tiles')
        apply_icon(self.view_switch, icon, label)
        if hasattr(self.view_switch, '_ios_action_item'):
            self._loop.call_soon(self._app.adaptive.render)
        if mode == 'Tiles':
            index = next((i for i, entry in enumerate(self._tile_entries) if entry.identity == anchor), 0)
            position = (index // 2) * self.TILE_ROW_HEIGHT
            self._update_tile_window(position)
        else:
            index = self._list_indices.get(anchor, 0)
            impl = self.native_list._impl
            if type(impl).__module__.endswith('_android'):
                native = impl.native
                native.setSelectionFromTop(index, 0)
                self._schedule_previews()
                return
            position = index * self.native_list.appearance.row_height
        self.vertical_position = position

    def _visible_rows(self):
        impl = self.native_list._impl
        if type(impl).__module__.endswith('_android'):
            first, last = impl.native.getFirstVisiblePosition(), impl.native.getLastVisiblePosition()
            return range(max(0, first), min(len(self._list_entries), last + 1))
        if type(impl).__module__.endswith('_ios'):
            paths = impl.native.indexPathsForVisibleRows
            return sorted(int(path.row) for path in paths) if paths is not None else ()
        return ()

    def _publish_list_rows(self):
        self.native_list.observe_rows = bool(self.thumbnails and self.thumbnails.enabled)
        super()._publish_list_rows()

    def _row_visible(self, row):
        # Native adapters call during binding. Read the finished viewport on the next turn.
        self._schedule_previews()

    def _tile_card(self, entry):
        card = super()._tile_card(entry)
        image_box, button = card.children
        if self.thumbnails is not None and self.thumbnails.supports(entry):
            preview = toga.ImageView(style=Pack(width=96, height=96))
            self._tile_previews[entry.identity] = preview, image_box, image_box.children[0]
        if self.on_item_actions is not None:
            card.remove(button)
            button.style.flex = 1
            command = icon_button('overflow', 'Actions for ' + button.text,
                                  on_press=partial(self._tile_actions, entry))
            card.add(toga.Box(children=[button, command], style=Pack(direction=ROW)))
        return card

    async def _tile_actions(self, entry, widget=None, **kwargs):
        if self.closed or self.navigation_busy or not self._entry_current(entry):
            return
        entry = await self.validate_cached_entry(entry)
        if entry is None or not self._entry_current(entry):
            return
        await self.select(entry)
        if self.selected == entry.identity and self._entry_current(entry):
            self.on_item_actions(entry.payload)

    def _retire_tile(self, identity):
        target = self._tile_previews.pop(identity, None)
        if target is not None:
            preview = target[0]
            token = id(preview)
            cancelled = self._preview_jobs.get(token)
            if cancelled is not None:
                cancelled.set()
            self._preview_completed.discard(token)
            preview.image = None
        super()._retire_tile(identity)

    def _update_tile_window(self, position):
        super()._update_tile_window(position)
        self._schedule_previews()

    def _schedule_previews(self, delay=0):
        if (self._preview_update is None and not self.closed and self._previews_visible
                and self.thumbnails is not None and self.thumbnails.enabled):
            self._preview_update = self._loop.call_later(delay, self._update_previews)

    def _preview_targets(self):
        if self.mode == 'List':
            return {id(row): (row.entry, row) for index in self._visible_rows()
                    if 0 <= index < len(self.native_list.data)
                    and self.thumbnails.supports((row := self.native_list.data[index]).entry)}
        return {id(preview): (self._tile_cards[identity][0], (preview, box))
                for identity, (preview, box, _) in self._tile_previews.items()}

    def _update_previews(self):
        self._preview_update = None
        source = self.thumbnails
        if self.closed or not self._previews_visible or source is None:
            return
        if not source.can_publish():
            self._reset_previews()
            if source.private:
                self._clear_private_previews()
            return
        targets = self._preview_targets()
        self._preview_completed.intersection_update(targets)
        for token, cancelled in self._preview_jobs.items():
            if token not in targets:
                cancelled.set()
        for token, (entry, target) in targets.items():
            if token in self._preview_completed or token in self._preview_jobs:
                continue
            if self.mode == 'List' and target.thumbnail:
                continue
            key = entry.identity, entry.revision
            if key in self.icons:
                self.icons.move_to_end(key)
                self._publish_preview(target, toga.Image(src=self.icons[key]))
                self._preview_completed.add(token)
            elif len(self._preview_jobs) < 2:
                cancelled = self._preview_jobs[token] = Event()
                self._spawn(self._load_preview(source, entry, target, token, cancelled))
        # Native rows notify entry but don't expose an exit callback. Retire
        # out-of-view work even when a scroll exits into unsupported rows.
        if self._preview_jobs:
            self._schedule_previews(.06)

    async def _load_preview(self, source, entry, target, token, cancelled):
        def publish(data):
            if (not self._previews_visible or source is not self.thumbnails or not source.can_publish()
                    or token not in self._preview_targets()):
                # The shared cache writes before calling publish. Discard a
                # result that left its viewport or lost access during decoding.
                self.icons.pop((entry.identity, entry.revision), None)
                return
            self._publish_preview(target, toga.Image(src=data))
        try:
            await self.work.thumbnail(entry, source.load, publish, epoch=self.epoch, cancelled=cancelled)
        finally:
            self._preview_jobs.pop(token, None)
            if not cancelled.is_set():
                self._preview_completed.add(token)
            self._schedule_previews()

    def _publish_preview(self, target, image):
        if self.mode == 'List':
            self._set_row_thumbnail(target, image)
        else:
            view, box = target
            view.image = image
            if view.parent is not box:
                box.clear()
                box.add(view)
