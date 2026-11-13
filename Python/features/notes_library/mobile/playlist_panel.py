"""Notes Library playlist list, detail and in-library note selection."""

import asyncio
from pathlib import PurePosixPath
from uuid import uuid4

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, NONE, PACK, ROW

from .library_drag import NativeRowDrag
from ..notes import document_kind
from services.documents.authoring.document_dialogs import DocumentTypeDialog


class PlaylistDrag(NativeRowDrag):
    def __init__(self, panel):
        self.panel = panel
        self.source = self.highlighted = None
        self.bindings = {}
        self.token = uuid4().hex

    def start(self, identity):
        if (not self.panel.can_edit() or self.panel.owner.panel_tab != 'Playlist'
                or self.panel.entry_index(identity) is None):
            return False
        self.source = identity
        return True

    def destination(self, identity):
        if (self.source is not None and identity != self.source
                and self.panel.owner.panel_tab == 'Playlist' and self.panel.can_edit()):
            return self.panel.entry_index(identity)
        return None

    def drop(self, identity):
        target = self.destination(identity)
        source = self.source
        self.end()
        if target is None:
            return False
        self.panel.owner.host.loop.create_task(self.panel.move(source, target))
        return True

    def highlight(self, widget):
        if self.highlighted is not widget:
            paint = self.panel.owner.host.highlight_entry
            if self.highlighted is not None:
                paint(self.highlighted, False)
            self.highlighted = widget
            if widget is not None:
                paint(widget, True)

    def end(self):
        self.source = None
        self.highlight(None)

    def clear(self):
        self.end()
        for widget in list(self.bindings):
            self.unbind(widget)


class PlaylistPanel:
    def __init__(self, owner):
        self.owner = owner
        self.catalog = self.speech = None
        self.unsubscribe = lambda: None
        self.records = ()
        self.playlist_id = self.selected = self.picking = None
        self.naming = self.busy = self.closed = self.suspended = False
        self.loading = None
        self.reload_pending = False
        self.choice = None
        self.buttons = {}
        self.drag = PlaylistDrag(self)
        self.header = toga.Label('', style=Pack(font_weight='bold', display=NONE))
        self.notice = toga.Label('', style=Pack(font_size=12, display=NONE))
        self.spoken = toga.Label('', style=Pack(font_size=12, display=NONE))
        self.rows = toga.Box(style=Pack(direction=COLUMN))
        self.commands = toga.Box(style=Pack(direction=COLUMN))
        self.content = toga.Box(children=[self.commands, self.rows], style=Pack(direction=COLUMN))
        self.scroll = toga.ScrollContainer(content=self.content, horizontal=False, style=Pack(flex=1))
        self.play_button = self.button('Read aloud…', self.play, flex=1)
        self.selected_play_button = self.button('Play selected', self.play_selected, flex=1)
        self.play_actions = toga.Box(children=[self.play_button, self.selected_play_button],
                                     style=Pack(direction=ROW, gap=4, display=NONE))
        self.widget = toga.Box(children=[self.header, self.notice, self.spoken, self.scroll, self.play_actions],
                               style=Pack(direction=COLUMN, flex=1, margin=4))
        self.up_button = self.button('Move up', self.move_up, flex=1)
        self.down_button = self.button('Move down', self.move_down, flex=1)
        self.repair_button = self.button('Repair reference…', self.repair, flex=1)
        self.remove_button = self.button('Remove entry', self.remove, flex=1)
        self.move_actions = toga.Box(children=[self.up_button, self.down_button], style=Pack(direction=ROW, gap=4))
        self.entry_actions = toga.Box(children=[self.repair_button, self.remove_button], style=Pack(direction=ROW, gap=4))
        self.pick_notice = toga.Label('Choose a Markdown note in Files or Search.', style=Pack(font_size=12, flex=1))
        self.pick_prompt = toga.Box(children=[self.pick_notice, self.button('Cancel', self.finish_pick)],
                                    style=Pack(direction=ROW))

    def button(self, label, handler, *, flex=0):
        return toga.Button(label, on_press=handler, style=Pack(height=44, flex=flex))

    @staticmethod
    def message(label, value):
        if label.text != value:
            label.text = value
        display = PACK if value else NONE
        if label.style.display != display:
            label.style.display = display

    @property
    def playlist(self):
        return next((record for record in self.records if record.id == self.playlist_id), None)

    def usable(self):
        return not (self.closed or self.suspended) and self.owner.valid()

    def can_edit(self):
        return self.usable() and not (self.busy or self.naming) and self.playlist is not None

    def connect_library(self):
        if self.catalog is None:
            self.catalog = self.owner.host.playlists(self.owner.library)
            self.unsubscribe = self.catalog.subscribe(self.catalog_changed)
            self.speech = self.owner.host.playlist_speech(self.owner, self.catalog, self.refresh_state)

    def activate(self):
        if not self.usable():
            self.clear_display()
            return
        self.connect_library()
        self.reload()

    def catalog_changed(self):
        loop = self.owner.host.loop
        if not loop.is_closed():
            loop.call_soon_threadsafe(self.reload)

    def reload(self):
        if self.closed:
            return
        if not self.usable():
            self.clear_display()
            return
        self.reload_pending = True
        if self.loading is None or self.loading.done():
            self.loading = self.owner.host.loop.create_task(self.load_pending())
        return self.loading

    async def load_pending(self):
        loaded = False
        while self.reload_pending and self.usable():
            self.reload_pending = False
            loaded = await self.load()
        return loaded

    async def load(self):
        try:
            records = await asyncio.to_thread(self.catalog.list)
        except (OSError, ValueError):
            if self.usable():
                self.clear_display()
                self.message(self.notice, 'Playlists could not be opened. Unlock the library or try again.')
            return False
        if not self.usable():
            self.clear_display()
            return False
        self.records = records
        if self.playlist is None:
            self.playlist_id = self.selected = None
        if not self.naming:
            self.render()
        return True

    def clear_display(self):
        self.drag.clear()
        self.records = ()
        self.playlist_id = self.selected = self.picking = None
        self.naming = False
        self.hide_pick_prompt()
        for label in (self.header, self.notice, self.spoken):
            self.message(label, '')
        self.play_actions.style.display = NONE
        for row in self.rows.children:
            row.text = ''
            self.owner.host.presentation.accessible_name(row, '')
        for control in self.commands.children:
            if isinstance(control, toga.TextInput):
                control.value = ''
        self.buttons.clear()
        self.rows.clear()
        self.commands.clear()
        if self.choice is not None:
            self.choice.cancel()
            self.owner.sidebar.cancel_action()

    def suspend_display(self):
        if self.closed or self.suspended:
            return
        self.suspended = True
        if self.loading is not None:
            self.loading.cancel()
            self.loading = None
        self.clear_display()

    def resume_display(self):
        if self.closed or not self.suspended:
            return
        self.suspended = False
        if self.owner.panel_tab == 'Playlist':
            self.activate()

    def close(self):
        self.closed = True
        self.unsubscribe()
        self.unsubscribe = lambda: None
        if self.loading is not None:
            self.loading.cancel()
        if self.speech is not None:
            self.speech.close()
        self.speech = self.catalog = None
        self.clear_display()

    def render(self):
        if not self.usable():
            self.clear_display()
            return
        self.drag.clear()
        self.buttons.clear()
        self.rows.clear()
        self.commands.clear()
        playlist = self.playlist
        self.message(self.header, playlist.name if playlist else '')
        self.play_actions.style.display = PACK if playlist else NONE
        if playlist is None:
            self.message(self.spoken, '')
            self.message(self.notice, '' if self.records else 'Create a playlist to arrange notes for read-aloud.')
            for record in self.records:
                def open_playlist(widget, identity=record.id, **kwargs):
                    self.open(identity)
                self.rows.add(self.button(record.name + (' · This session' if record.session_only else ''), open_playlist))
            self.commands.add(self.button('New playlist…', self.name))
            return
        if self.entry_index(self.selected) is None:
            self.selected = playlist.active_id
        for entry in playlist.entries:
            def select(widget, identity=entry.id, **kwargs):
                if self.can_edit():
                    self.selected = identity
                    self.refresh_state()
            button = self.button(entry.path, select)
            self.owner.host.middle_filename(button)
            self.buttons[entry.id] = button
            self.rows.add(button)
            self.drag.bind(button, entry.id, target=True)
        self.commands.add(
            self.button_row(('All playlists', self.back), ('Rename…', self.name)),
            self.button('Add Markdown…', self.begin_pick),
            self.move_actions, self.entry_actions,
        )
        self.refresh_state()

    def button_row(self, *specs):
        return toga.Box(children=[self.button(label, handler, flex=1) for label, handler in specs],
                        style=Pack(direction=ROW, gap=4))

    def refresh_state(self):
        if not self.usable():
            self.clear_display()
            return
        playlist, speech = self.playlist, self.speech
        if playlist is None or speech is None:
            return
        current = speech.playlist_id == playlist.id
        active = (speech.active_id if current else None) or playlist.active_id
        state = speech.state if current else 'stopped'
        status = {'speaking': 'Playing', 'paused': 'Paused', 'stopped': 'Ready',
                  'unavailable': 'Read-aloud unavailable'}.get(state, state.capitalize())
        for entry in playlist.entries:
            button = self.buttons.get(entry.id)
            if button is None:
                continue
            parts = [entry.path]
            if entry.id == active:
                parts.append(status)
            if entry.id in speech.unavailable:
                parts.append('Missing or inaccessible')
            title = ' · '.join(parts)
            title_changed = button.text != title
            if title_changed:
                button.text = title
            selected = entry.id == self.selected
            if getattr(button, '_playlist_selected', None) != selected:
                button._playlist_selected = selected
                self.owner.host.tab_style(button, selected)
            if title_changed or getattr(button, '_playlist_accessible_selected', None) != selected:
                button._playlist_accessible_selected = selected
                self.owner.host.presentation.accessible_name(button, title + (' selected' if selected else ''))
        detail = status if playlist.entries else 'Add Markdown notes to start listening.'
        if playlist.session_only:
            detail += ' This playlist lasts for the current session.'
        self.message(self.notice, detail)
        line = getattr(speech, 'spoken_line', '') if current else ''
        self.message(self.spoken, line)
        index = self.entry_index(self.selected)
        self.up_button.enabled = index is not None and index > 0
        self.down_button.enabled = index is not None and index < len(playlist.entries) - 1
        self.repair_button.enabled = self.remove_button.enabled = index is not None
        self.play_button.enabled = bool(playlist.entries)
        self.selected_play_button.enabled = index is not None

    def entry_index(self, identity):
        if self.playlist is not None:
            return next((index for index, entry in enumerate(self.playlist.entries) if entry.id == identity), None)
        return None

    def open(self, identity):
        if not self.usable():
            return
        self.playlist_id, self.selected = identity, None
        self.render()
        self.scroll.vertical_position = 0

    def back(self, widget=None, **kwargs):
        self.open(None)

    async def change(self, method, *args):
        if not self.usable() or self.busy:
            return None
        self.busy = True
        try:
            record = await asyncio.to_thread(getattr(self.catalog, method), *args)
            return record if self.usable() else None
        except (OSError, ValueError):
            if self.usable():
                self.message(self.notice, 'Could not update the playlist. Check the selection and library access.')
            return None
        finally:
            self.busy = False

    def name(self, widget=None, *, path=None, **kwargs):
        if not self.usable() or self.busy:
            return
        playlist = self.playlist
        self.naming = True
        field = toga.TextInput(value=playlist.name if playlist else '', placeholder='Playlist name', style=Pack(height=44))
        self.owner.host.presentation.accessible_name(field, 'Playlist name')

        async def save(widget, **kwargs):
            record = await (self.change('rename', playlist.id, field.value) if playlist
                            else self.change('create', field.value))
            if record is not None:
                self.naming = False
                if path is not None:
                    await self.change('add', record.id, path)
                if self.usable() and await self.reload():
                    self.open(record.id)

        def cancel(widget, **kwargs):
            self.naming = False
            self.render()

        self.commands.clear()
        self.commands.add(field, self.button_row(('Save name', save), ('Cancel', cancel)))
        field.focus()

    def begin_pick(self, widget=None, *, replace=False, **kwargs):
        if not self.can_edit():
            return
        if replace and self.selected is None:
            return
        self.picking = self.playlist.id, self.selected if replace else None
        self.pick_notice.text = 'Choose a Markdown note in Files or Search.'
        self.owner.select_panel_tab('Files')

    def sync_pick_prompt(self, name):
        if name == 'Playlist':
            self.picking = None
        else:
            self.drag.end()
        if self.picking is None or name not in ('Files', 'Search'):
            self.hide_pick_prompt()
            return
        target = self.owner.files_content if name == 'Files' else self.owner.search_content
        parent = self.pick_prompt.parent
        if parent is not target:
            if parent is not None:
                parent.remove(self.pick_prompt)
            target.insert(0, self.pick_prompt)

    def hide_pick_prompt(self):
        if self.pick_prompt.parent is not None:
            self.pick_prompt.parent.remove(self.pick_prompt)

    def finish_pick(self, widget=None, **kwargs):
        self.picking = None
        self.hide_pick_prompt()
        if self.usable():
            self.owner.select_panel_tab('Playlist')

    async def choose_note(self, path):
        """Consume Files/Search activation only during an explicit picker request."""
        if self.picking is None or not self.usable():
            return False
        if self.owner.panel_tab not in ('Files', 'Search'):
            return False
        if document_kind(path) != 'markdown':
            self.pick_notice.text = 'Choose a Markdown note ending in .md or .markdown.'
            return True
        identity, entry = self.picking
        record = await (self.change('replace', identity, entry, path) if entry
                        else self.change('add', identity, path))
        if self.picking != (identity, entry):
            return True
        if record is not None:
            self.finish_pick()
        elif self.usable():
            self.pick_notice.text = 'Could not add this note. Choose another note or cancel.'
        return True

    async def add_note(self, path):
        if not self.usable() or self.choice is not None:
            return
        if self.picking is not None:
            await self.choose_note(path)
            return
        self.connect_library()
        if not await self.reload() or not self.usable():
            return
        if not self.records:
            self.owner.select_panel_tab('Playlist')
            self.name(path=path)
            return
        dialog = DocumentTypeDialog(choices=[(record.name, record.id) for record in self.records])
        dialog.title, dialog.message = 'Add to playlist', PurePosixPath(path).name
        choice = self.choice = self.owner.host.loop.create_task(
            self.owner.sidebar.choose_action(dialog, self.owner.view.window))
        try:
            identity = await choice
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            return
        finally:
            self.choice = None
        if self.usable() and any(record.id == identity for record in self.records):
            record = await self.change('add', identity, path)
            if record is not None:
                self.open(record.id)
                self.owner.select_panel_tab('Playlist')

    def repair(self, widget=None, **kwargs):
        self.begin_pick(replace=True)

    async def remove(self, widget=None, **kwargs):
        if self.can_edit() and self.selected is not None:
            await self.change('remove', self.playlist.id, self.selected)

    async def move(self, entry, index):
        if self.can_edit():
            await self.change('move', self.playlist.id, entry, index)

    async def move_selected(self, distance):
        index = self.entry_index(self.selected)
        if index is not None and 0 <= index + distance < len(self.playlist.entries):
            await self.move(self.selected, index + distance)

    async def move_up(self, widget=None, **kwargs):
        await self.move_selected(-1)

    async def move_down(self, widget=None, **kwargs):
        await self.move_selected(1)

    def play(self, widget=None, **kwargs):
        if self.can_edit() and self.playlist.entries:
            self.speech.play(self.playlist.id, anchor=self.play_button)

    def play_selected(self, widget=None, **kwargs):
        if self.can_edit() and self.selected is not None:
            self.speech.play(self.playlist.id, self.selected, anchor=self.play_button)
