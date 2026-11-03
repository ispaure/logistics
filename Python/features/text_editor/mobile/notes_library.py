"""Feature-owned provider Notes Library browser with explicit host services."""
from commonUtils.search.policy import SEARCH_DEBOUNCE_SECONDS

from collections import Counter
import asyncio
import posixpath
from ..dataview import view_plan
from ..dataview_script import worker_policy
import re
from html import unescape
from pathlib import PurePosixPath
from threading import Event
from textwrap import fill
from urllib.parse import parse_qs, quote, unquote, urlsplit
from uuid import uuid4
from dataclasses import dataclass
from typing import Callable
from time import perf_counter
import toga
from commonUtils.ui.native.inline_html import set_inline_html
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER, NONE, PACK
from features.text_editor.notes import NotesLibrary, MAX_NOTE, MARKDOWN, DOCUMENTS, document_kind
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.search.names import natural_name_key, search_terms
from commonUtils.search.providers import search_resources, SearchResult
from commonUtils.ui.native.adaptive import allocated_width


@dataclass(frozen=True)
class NotesHost:
    presentation: object
    storage: Callable
    loop: object
    workspace: object
    apple: bool
    client: Callable
    active: Callable
    privacy_gate: Callable
    privacy_gates: Callable
    content_width: Callable
    folder_visible: Callable
    show_documents: Callable
    close_session: Callable
    show_view: Callable
    destination: Callable
    render: Callable
    speech: Callable
    commands: Callable
    list_button: Callable
    middle_filename: Callable
    entry_icon: Callable
    highlight_entry: Callable
    preview: Callable
    drawers: Callable
    tab_style: Callable
    document_editor: Callable = None
    confirm: Callable = None
    choose_type: Callable = None
    toolbar_insets: Callable = lambda toolbar: (8, 8)
    open_timing: Callable = None


from .library_panels import LibraryPanels, LibraryOpening


class VaultBrowser(LibraryPanels):
    def __init__(self, host, provider, root, destination):
        self.host, self.provider, self.destination = host, provider, destination
        self.release_provider = lambda: None
        self.library = NotesLibrary(provider, root)
        self.root = self.library.root
        self.history, self.history_index = [], -1
        self.positions = {}
        self.session = None
        self.embedded = None
        self.editing = False
        self.access = host.storage(provider)
        self.cancelled = Event()
        self.folders, self.expanded, self.loading = {}, {self.root}, set()
        self.folder_pages = {}
        self.path = None
        self.selected_path = None
        self.epoch = 0
        self._open_timing = None
        self.shown = 50
        self.base = "https://markdown.invalid/vault/" + uuid4().hex + "/"
        self.rows = toga.Box(style=Pack(direction=COLUMN))
        self.notice = toga.Label("", style=Pack(font_size=12))
        self.tree = toga.Box(
            children=[
                toga.Label("Files", style=Pack(font_size=20, font_weight='bold', margin_bottom=4)),
                toga.Label(self.access.label
                           + (' · Editable' if self.library.writable else ' · Read-only'),
                           style=Pack(font_size=12, margin_bottom=12)),
                toga.ScrollContainer(
                    content=self.rows, horizontal=False, style=Pack(flex=1)
                ),
            ],
            style=Pack(direction=COLUMN, flex=1, margin=12),
        )
        self.title = toga.Label(
            "Choose a Markdown note", style=Pack(font_size=18, flex=1)
        )
        self.edit = self.host.presentation.icon_button(
            "edit", "Edit Markdown", on_press=self.open_editor, enabled=False
        )
        self.pending_fragment = ""
        self.web = self.access.webview(max_bytes=MAX_NOTE,
            on_navigation_starting=self.follow_link, on_webview_load=self.page_loaded,
            style=Pack(flex=1))
        host.presentation.bind_font(self.web, "markdown", web=True)
        self.article = toga.Box(
            children=[self.web], style=Pack(direction=COLUMN, flex=1)
        )
        from commonUtils.ui.native.markdown_search import MarkdownPageSearch
        self.page_search = MarkdownPageSearch(self.web, self.article, valid=self.valid)
        self.speech = host.speech(
            self.web,
            self.article,
            document_title=lambda: self.access.title(self.path),
            privacy_gate=self.access.speech_gate,
            valid=self.valid,
        )
        self.speech.button.enabled = False
        self.link_rows = toga.Box(style=Pack(direction=COLUMN))
        self.links = toga.Box(children=[
            toga.Label('Links', style=Pack(font_size=20, font_weight='bold')),
            toga.ScrollContainer(content=self.link_rows, horizontal=False, style=Pack(flex=1)),
        ], style=Pack(direction=COLUMN, flex=1, margin=12))
        self.links_generation = 0
        self.links_refresh_task = None
        self.sidebar = host.drawers(self.tree, self.article, self.links)
        self.sidebar.on_close = self.cancel_links
        self.links_button = self.host.presentation.icon_button(
            'notes_links', 'Backlinks and outgoing links', on_press=self.show_links
        )
        self.links_button._toolbar_priority = True
        self.links_button._toolbar_horizontal = True
        self.menu = host.presentation.icon_button(
            "notes_files", "Browse Notes Library", on_press=self.sidebar.toggle
        )
        self.menu._toolbar_horizontal = True
        self.back_button = self.host.presentation.icon_button(
            "back",
            "Previous note",
            on_press=self.previous_note,
            enabled=False,
        )
        self.forward_button = self.host.presentation.icon_button(
            "forward",
            "Next note",
            on_press=self.next_note,
            enabled=False,
        )
        self.up_button = self.host.presentation.icon_button(
            "up", "Browse parent folder", on_press=self.browse_parent, enabled=False
        )
        self.search_task = None
        self.search_paused = False
        self.search_generation = 0
        self.search_rows = []
        self.search_status = ""
        self.search = toga.TextInput(
            placeholder="Search Notes Library",
            on_change=self.search_changed,
            style=Pack(height=48),
        )
        self.search_mode = toga.Selection(items=["Documents", "Names only"], style=Pack(height=48))
        self.search_mode.on_change = self.search_changed
        self.tree.insert(2, self.search)
        self.tree.insert(3, self.search_mode)
        self.toolbar = toga.Box(
            children=[
                self.menu,
                self.back_button,
                self.forward_button,
                self.up_button,
                toga.Box(style=Pack(flex=1)),
                self.edit,
                self.speech.button,
            ],
            style=Pack(direction=ROW),
        )
        if not self.library.writable:
            self.toolbar.remove(self.edit)
        self.view = toga.Box(
            children=[self.toolbar, self.notice, self.sidebar.view],
            style=Pack(direction=COLUMN, flex=1),
        )
        self.view._keyboard_actions_required = True
        self.reader_actions_button = self.host.presentation.icon_button(
            "more", "Note actions"
        )
        self.toolbar.remove(self.up_button)
        self.toolbar.remove(self.speech.button)
        self.toolbar.add(self.reader_actions_button, self.links_button)
        self.close_button = self.host.presentation.icon_button(
            "close", "Close Notes Library", on_press=self.close
        )
        self.toolbar.insert(0, self.close_button)
        self.view._reader_close_button = self.close_button
        for button in (self.back_button, self.forward_button):
            button._toolbar_group = 'page-history'
            button._toolbar_priority = True
        self.view._workspace_menu_button = self.menu
        self.view._native_reader_toolbar = self.toolbar
        self.view._native_reader_title = (
            lambda: PurePosixPath(self.path).name if self.path else "Notes Library"
        )
        from services.documents.storage import display_path
        self.view._document_path = lambda: display_path(self.provider, self.path or self.root) if self.valid() else None
        self.view._native_reader_buttons = lambda: [
            self.back_button,
            self.forward_button,
            *(
                [self.edit if self.library.writable else self.speech.button]
                if self.path and document_kind(self.path) == 'markdown'
                else []
            ),
            self.reader_actions_button,
            self.links_button,
        ]
        self.secondary = toga.Box(children=[], style=Pack(direction=ROW, margin_left=8, margin_right=8))
        for button in (self.back_button, self.forward_button, self.edit, self.reader_actions_button):
            if button.parent is not None:
                button.parent.remove(button)
            self.secondary.add(button)
        self.view.insert(1, self.secondary)
        self.view._native_reader_buttons = lambda: [self.links_button]
        self.sidebar.on_change = self.refresh_chrome
        self.welcome = toga.Box(style=Pack(direction=COLUMN, flex=1, margin=20))
        self.open_card = toga.Button('Open Document', on_press=lambda widget: self.sidebar.show_sidebar(), style=Pack(height=72))
        self.new_card = toga.Button('New Document', on_press=self.new_note, style=Pack(height=72, margin_top=12))
        host.presentation.surface(self.open_card, radius=16)
        host.presentation.surface(self.new_card, radius=16)
        self.welcome.add(toga.Label('Notes Library', style=Pack(font_size=24, font_weight='bold')), self.open_card)
        if self.library.supports('create'):
            self.welcome.add(self.new_card)
        self.article.remove(self.web)
        self.article.add(self.welcome)
        self.refresh_reader_actions()
        self.refresh_chrome()
        self.init_panels()
        self.reflow(host.content_width(destination))

    def refresh_chrome(self):
        if not hasattr(self, 'secondary'):
            return
        left, right = self.host.toolbar_insets(self.secondary)
        if (self.secondary.style.margin_left, self.secondary.style.margin_right) != (left, right):
            self.secondary.style.margin_left, self.secondary.style.margin_right = left, right
        show = self.path is not None and not self.sidebar.sidebar_open
        if show and self.secondary.parent is None:
            self.view.insert(1, self.secondary)
        elif not show and self.secondary.parent is not None:
            self.secondary.parent.remove(self.secondary)
        editable = not self.path or PurePosixPath(self.path).suffix.lower() in MARKDOWN
        if editable and self.edit.parent is None:
            self.secondary.insert(2, self.edit)
        elif not editable and self.edit.parent is self.secondary:
            self.secondary.remove(self.edit)
        if getattr(self, '_edit_chrome', None) != self.editing:
            self._edit_chrome = self.editing
            self.host.presentation.apply_icon(self.edit, 'view' if self.editing else 'edit',
                                              'View document' if self.editing else 'Edit document')

    async def prepare_leave(self):
        editor = self.embedded
        if editor is None:
            return True
        if editor.busy:
            self.notice.text = 'Wait for the document operation to finish.'
            return False
        try:
            await editor.flush()
            if not self.valid() or self.embedded is not editor:
                return False
            if editor.dirty:
                if self.host.confirm is None:
                    return False
                choice = await self.host.confirm()
                if not self.valid() or self.embedded is not editor:
                    return False
                if choice == 'save':
                    return await editor.save()
                return choice == 'discard'
            return True
        except (OSError, ValueError) as error:
            self.notice.text = str(error)
            return False

    def retire_editor(self):
        if self.embedded is not None:
            formatted = getattr(self.embedded, 'formatted', None)
            if formatted is not None and self.path is not None:
                self.positions[self.path] = formatted.scroll_top
            self.embedded.dispose()
            self.embedded = None
        self.editing = False
        if self.session is not None:
            self.session.dirty = False

    def valid(self):
        return not self.cancelled.is_set() and self.access.valid()

    def contained(self, path):
        return self.library.contained(path)

    def reflow(self, width):
        available = max(0, allocated_width(self.view, width) - 24)
        self.sidebar.reflow(available)
        # Compact browsing still needs its menu while the article is hidden.
        # Wide layouts keep document commands over their own article pane.
        parent = self.article if self.sidebar.expanded else self.view
        if not self.host.apple and self.toolbar.parent is not parent:
            if self.toolbar.parent is not None:
                self.toolbar.parent.remove(self.toolbar)
            parent.insert(0, self.toolbar)
        self.rows.style.width = (
            max(0, self.sidebar.policy.sidebar_width - 24)
        )
        self.menu.enabled = True
        self.refresh_chrome()

    def refresh_reader_actions(self):
        if hasattr(self, "reader_actions"):
            self.reader_actions.dispose()
        actions = []
        if self.library.supports('create'):
            actions.append(("New document…", self.new_note))
            actions.append(("New folder…", lambda: self.manage_entry(folder=True)))
        if self.selected_path is not None and self.library.supports('rename'):
            actions.append(("Rename / move selected…", lambda: self.manage_entry(move=True)))
        if self.embedded is not None:
            if self.library.writable:
                actions.append(('Save', self.embedded.save))
            if getattr(self.embedded, 'kind', None) == 'markdown':
                actions.extend([('Formatted editing', self.embedded.choose_mode),
                    ('Source editing', lambda: self.embedded.choose_mode(False)),
                    ('Find / replace…', self.embedded.show_find),
                    ('Properties…', self.embedded.show_properties),
                    ('Edit YAML…', self.embedded.edit_yaml)])
            elif getattr(self.embedded, 'kind', None) == 'text':
                actions.append(('Find / replace…', self.embedded.show_find))
        if self.path is not None and PurePosixPath(self.path).suffix.lower() in MARKDOWN:
            from .library_tools import show_contents
            async def contents(widget=None, **kwargs):
                return await show_contents(self)
            actions.append(('Contents…', contents))
        if self.path is not None and not self.editing and PurePosixPath(self.path).suffix.lower() in MARKDOWN:
            actions.append(("Find in this page…", self.show_page_search))
            actions.append(("Read aloud…", self.speech.show))
        if self.up_button.enabled:
            actions.append(("Browse parent folder", self.browse_parent))
        actions.append(("All documents", self.host.show_documents))
        self.reader_actions = self.host.commands(
            self.reader_actions_button, actions, self.browse_parent
        )

    async def load_folder(self, path, *, rows=None):
        if not self.valid() or path in self.loading:
            return False
        self.loading.add(path)
        self.notice.text = "Loading notes…"
        try:
            path = self.contained(path)
            def listing():
                entries = self.library.folders(path, cancelled=lambda: not self.valid()) if rows is None else rows
                pages = self.library.folder_pages(
                    [row for row in entries if not row['name'].startswith('.')
                     and self.host.folder_visible(row['path'], directory=row['directory'])],
                    cancelled=lambda: not self.valid())
                return entries, pages
            rows, pages = await asyncio.to_thread(listing)
            if not self.valid():
                return False
            self.folder_pages.update(pages)
            self.folders[path] = sorted(
                (
                    row
                    for row in rows
                    if not row["name"].startswith(".")
                    and self.host.folder_visible(
                        row["path"], directory=row["directory"]
                    )
                    and (
                        row["directory"]
                        or PurePosixPath(row["name"]).suffix.lower() in DOCUMENTS
                    )
                ),
                key=lambda row: (not row["directory"], row["name"].casefold()),
            )
            self.notice.text = ""
            self.render_tree()
            return True
        except OperationCancelled:
            return False
        except (OSError, ValueError) as error:
            if self.valid():
                self.notice.text = fill(
                    "Could not browse notes: " + str(error)[:120], width=28
                )
            return False
        finally:
            self.loading.discard(path)

    async def toggle_folder(self, path):
        if not self.valid():
            return
        self.selected_path = path
        if path in self.expanded:
            self.expanded.remove(path)
        else:
            self.expanded.add(path)
            if path not in self.folders:
                await self.load_folder(path)
        self.render_tree()
        self.refresh_reader_actions()

    def search_changed(self, widget=None, **kwargs):
        tree_task = getattr(self, 'tree_task', None)
        if tree_task is not None and not tree_task.done():
            tree_task.cancel()
        self.search_generation += 1
        if self.search_task is not None:
            self.search_task.cancel()
            self.search_task = None
        if not self.valid():
            return
        terms = search_terms(self.search.value or '')
        self.search_paused = False
        if terms:
            if getattr(self, 'panel_tab', 'Files') != 'Files':
                self.search_paused = True
                return
            # Keep the current native results untouched until typing settles.
            self.search_task = self.host.loop.create_task(self.run_search(
                self.search.value, self.search_generation, self.search_mode.value == 'Search within Documents'))
        else:
            self.search_rows = []
            self.search_status = ''
            self.shown = 50
            self.render_tree()

    async def run_search(self, query, generation, include_text):
        def cancelled():
            return generation != self.search_generation or not self.valid()

        def list_children(folder, *, cancelled):
            try:
                entries = self.library.folders(folder, cancelled=cancelled)
            except ValueError as error:
                if cancelled():
                    raise OperationCancelled() from error
                # An oversized or unsupported folder is a partial listing.
                raise OSError(str(error)) from error
            return [row for row in entries
                    if self.host.folder_visible(row["path"], directory=row["directory"])]

        def read_text(path, *, cancelled):
            return self.library.read_text(path, cancelled=cancelled)

        last_progress_size = -1
        def publish(result, finished=False):
            nonlocal last_progress_size
            if cancelled():
                return
            if not finished and len(result.rows) == last_progress_size:
                return
            last_progress_size = len(result.rows)
            self.search_rows = result.rows
            if finished:
                self.search_status = "" if result.complete else "Some items could not be searched."
            self.render_tree()

        def project(result):
            rows = [dict(row, name=posixpath.basename(row['path'])) for row in result.rows]
            rows.sort(key=lambda row: (row.get('content_match', False), natural_name_key(row['name']),
                                      natural_name_key(row['path'])))
            return SearchResult(rows, result.scanned, result.complete, result.errors)

        await asyncio.sleep(SEARCH_DEBOUNCE_SECONDS)
        if cancelled():
            return
        self.shown = 50
        self.search_status = 'Searching…'
        # A scan with no early matches still needs visible feedback. Updating
        # one status row avoids rebuilding the retained native result list.
        if not hasattr(self, '_rows_message'):
            self._rows_message = toga.Label(self.search_status)
        else:
            self._rows_message.text = self.search_status
        if self._rows_message.parent is not self.rows:
            self.rows.add(self._rows_message)
        # Reuse existing results while the worker finds the new query's matches.
        from time import monotonic
        last_publish = 0
        pending_progress = None
        progress_queued = False
        def deliver_progress():
            nonlocal pending_progress, progress_queued
            latest, pending_progress = pending_progress, None
            progress_queued = False
            if latest is not None:
                publish(latest)
        def progress(result):
            nonlocal last_publish, pending_progress, progress_queued
            now = monotonic()
            if not cancelled() and now - last_publish >= .3:
                last_publish = now
                pending_progress = project(result)
                if not progress_queued:
                    progress_queued = True
                    self.host.loop.call_soon_threadsafe(deliver_progress)
        try:
            def scan():
                return project(search_resources(self.provider, self.root, query, cancelled=cancelled,
                    list_children=list_children, read_text=read_text if include_text else None,
                    progress=progress))
            result = await asyncio.to_thread(scan)
        except OperationCancelled:
            return
        except (OSError, ValueError) as error:
            if not cancelled():
                self.search_rows = []
                self.search_status = "Could not search notes: " + str(error)[:120]
                self.render_tree()
        else:
            pending_progress = None
            publish(result, finished=True)

    async def reveal_folder(self, path, *, select=True):
        self.search.value = ""
        folder = self.root
        for part in PurePosixPath(path).relative_to(self.root or ".").parts:
            self.expanded.add(folder)
            if folder not in self.folders and not await self.load_folder(folder):
                return
            folder = posixpath.join(folder, part)
        self.expanded.add(path)
        if select:
            self.selected_path = path
        if path not in self.folders:
            await self.load_folder(path)
        self.render_tree()
        self.refresh_reader_actions()

    def render_tree(self):
        if not self.valid():
            return
        task = getattr(self, 'tree_task', None)
        if task is not None and not task.done():
            task.cancel()
        if getattr(self, 'panel_tab', 'Files') != 'Files':
            return
        from commonUtils.ui.native.text_size import native_backend
        updates = self.tree_updates()
        if native_backend(self.rows).startswith('toga_dummy.'):
            for _ in updates:
                pass
            return
        async def render():
            try:
                for _ in updates:
                    if not self.valid():
                        break
                    # Native control creation/layout must release the main loop.
                    await asyncio.sleep(.001)
            finally:
                updates.close()
        self.tree_task = self.host.loop.create_task(render())

    def tree_updates(self):
        if not self.valid():
            return
        old_rows = dict(getattr(self, '_row_cache', {}))
        self._row_cache = dict(old_rows)
        new_rows, desired = {}, []
        flattened = []

        searching = bool(search_terms(self.search.value or ""))

        def add(folder, depth=0):
            for entry in self.folders.get(folder, ()):
                if not self.host.folder_visible(
                    entry["path"], directory=entry["directory"]
                ):
                    continue
                flattened.append((entry, depth))
                if entry["directory"] and entry["path"] in self.expanded:
                    add(entry["path"], depth + 1)

        if searching:
            flattened = [(entry, 0) for entry in self.search_rows
                         if self.host.folder_visible(entry["path"], directory=entry["directory"])]
        else:
            add(self.root)
        counts = Counter(PurePosixPath(entry['path']).name.casefold() for entry, _ in flattened) if searching else {}
        for entry, depth in flattened[: self.shown]:
            path, directory = entry["path"], entry["directory"]
            page = self.folder_pages.get(path) if directory else None

            async def choose(widget=None, path=path, directory=directory, page=page, **kwargs):
                if searching and directory:
                    await self.reveal_folder(path)
                elif page is not None:
                    await self.open_note(page)
                elif directory:
                    await self.toggle_folder(path)
                else:
                    await self.open_note(path)

            label = PurePosixPath(path).name if searching else entry['name']
            if counts.get(label.casefold(), 0) > 1:
                parent = posixpath.dirname(posixpath.relpath(path, self.root or "."))
                label += " · " + (parent or "Library root")
            key = (searching, path, directory, page, depth, label, path in self.expanded)
            row = old_rows.get(key)
            if row is None:
                button = self.host.list_button(
                    toga.Button(label, on_press=choose, style=Pack(height=48, flex=1))
                )
                self.host.middle_filename(button)
                button.vault_path = path
                self.bind_file_hold(button, path)
                row = toga.Box(
                    children=[
                        toga.Box(style=Pack(width=depth * 20)),
                        self.host.entry_icon(directory, landing_page=page is not None),
                        button,
                    ],
                    style=Pack(direction=ROW, align_items=CENTER),
                )
                if directory and not searching:
                    async def expand(widget=None, path=path, **kwargs):
                        await self.toggle_folder(path)
                    disclosure = self.host.presentation.icon_button(
                        'down' if path in self.expanded else 'forward',
                        ('Collapse ' if path in self.expanded else 'Expand ') + entry['name'],
                        on_press=expand,
                    )
                    disclosure.style.width = 48
                    disclosure.style.height = 48
                    row.insert(2, disclosure)
            new_rows[key] = row
            self._row_cache[key] = row
            button = next(child for child in row.children if hasattr(child, 'vault_path'))
            selected = path == self.selected_path
            if getattr(row, '_notes_selected', None) != selected:
                self.host.highlight_entry(row, selected)
                self.host.highlight_entry(button, selected)
                row._notes_selected = selected
            desired.append(row)
            yield
        if len(flattened) > self.shown:
            if not hasattr(self, '_more_rows'):
                def more(widget=None, **kwargs):
                    self.shown += 50
                    self.render_tree()
                self._more_rows = toga.Button('Show more notes', on_press=more, style=Pack(height=48))
            desired.append(self._more_rows)
        message = (self.search_status if searching and self.search_status else
            'No matching notes or folders.' if searching and not flattened else
            'No documents in this folder.' if not flattened else '')
        if message:
            if not hasattr(self, '_rows_message'):
                self._rows_message = toga.Label(message)
            elif self._rows_message.text != message:
                self._rows_message.text = message
            desired.append(self._rows_message)
        changed = list(self.rows.children) != desired
        if changed:
            for row in list(self.rows.children):
                if row not in desired:
                    self.rows.remove(row)
                    yield
            for index, row in enumerate(desired):
                if row.parent is not self.rows:
                    self.rows.insert(index, row)
                    yield
                elif self.rows.children[index] is not row:
                    self.rows.remove(row)
                    self.rows.insert(index, row)
                    yield
        for key, row in list(self._row_cache.items()):
            if key not in new_rows:
                # A cancelled cleanup must not expose an unbound cached row.
                self._row_cache.pop(key, None)
                for button in row.children:
                    if hasattr(button, 'vault_path'):
                        self.release_file_hold(button)
                yield
        self._row_cache = new_rows
        if changed:
            self.sidebar.refresh_gestures()

    def mark_open_timing(self, stage, epoch):
        timing = self._open_timing
        if timing is not None and timing['epoch'] == epoch:
            timing['stages_ms'][stage] = round((perf_counter() - timing['started']) * 1000, 2)
            self.host.open_timing({key: value for key, value in timing.items() if key != 'started'})

    async def open_note(self, path, *, remember=True, fragment="", resolve_link=False):
        return_side = getattr(self.sidebar, 'side', None)
        opened = await self._open_note(path, remember=remember, fragment=fragment, resolve_link=resolve_link)
        if opened and return_side is not None:
            self._document_return_side = return_side
        return opened

    async def _open_note(self, path, *, remember=True, fragment="", resolve_link=False):
        started = perf_counter()
        if not self.valid():
            return False
        if not await self.prepare_leave():
            return False
        if not resolve_link and document_kind(path) == 'text':
            return await self.open_text(path, remember=remember)
        if not resolve_link and PurePosixPath(path).suffix.lower() == '.rmdoc':
            return await self.open_canvas(path, remember=remember)
        if not hasattr(self, 'page_loading'):
            self.page_loading = LibraryOpening(self)
        self.sidebar.show_detail()
        self.links_generation += 1
        self.epoch += 1
        epoch = self.epoch
        if self.host.open_timing is not None:
            self._open_timing = dict(epoch=epoch, started=started, link=resolve_link,
                cached_folders_at_start=len(self.library._link_folders), stages_ms={})
            self.mark_open_timing('started', epoch)
        current = self.path
        cancelled = lambda: not self.valid() or epoch != self.epoch
        try:
            try:
                await asyncio.wait_for(self.remember_position(), timeout=.25)
            except asyncio.TimeoutError:
                pass
            if cancelled():
                return False
            self.page_loading.start(path, finding=resolve_link)
            self.speech.close()
            if not resolve_link:
                path = self.contained(path)
            if not resolve_link and PurePosixPath(path).suffix.lower() not in MARKDOWN:
                raise ValueError("Choose a Markdown note.")
            if resolve_link:
                self.mark_open_timing('finding', epoch)
                path, fragment = await asyncio.to_thread(self.library.link, current, path, cancelled=cancelled)
                if cancelled():
                    return False
                self.page_loading.opening(path)
                self.mark_open_timing('found', epoch)
                if document_kind(path) in ('text', 'notebook'):
                    self.page_loading.finish()
                    opener = self.open_text if document_kind(path) == 'text' else self.open_canvas
                    return await opener(path, remember=remember)

            def read():
                data = self.library.read(path, cancelled=cancelled)
                plan = view_plan(data.decode("utf-8-sig"))
                html = self.host.preview(plan.render() if plan.scripts else plan.source, image_source=self.library.image_source(path))
                self.access.validate_preview(html, MAX_NOTE)
                return html, plan

            html, plan = await asyncio.to_thread(read)
            if not self.valid() or epoch != self.epoch:
                return False
            self.mark_open_timing('prepared', epoch)
            self.cancel_data_views()
            if remember and path != self.path:
                del self.history[self.history_index + 1 :]
                self.history.append(path)
                self.history_index = len(self.history) - 1
            self.retire_editor()
            self.article.clear()
            self.article.add(self.web)
            self.path = self.selected_path = path
            self.update_tree_selection()
            self.title.text = fill(PurePosixPath(path).name, width=28)
            self.base = "https://markdown.invalid/vault/" + uuid4().hex + "/"
            if self._open_timing is not None:
                self._open_timing['published_epoch'] = epoch
            self.data_view_plan = plan if plan.scripts else None
            self.data_views_loading = bool(plan.scripts)
            html = self.data_view_html(html, active=bool(plan.scripts))
            self.pending_fragment = fragment
            self.page_search.loading()
            set_inline_html(self.web, self.base, html)
            self.edit.enabled = self.library.writable
            self.speech.button.enabled = True
            self.notice.text = ""
            self.back_button.enabled = self.history_index > 0
            self.forward_button.enabled = self.history_index < len(self.history) - 1
            self.up_button.enabled = True
            self.refresh_reader_actions()
            self.sidebar.show_detail()
            self.refresh_chrome()
            self.host.render()
            self.mark_open_timing('published', epoch)
            return True
        except OperationCancelled:
            return False
        except (OSError, UnicodeError, ValueError) as error:
            if self.valid() and epoch == self.epoch:
                self.notice.text = fill(str(error)[:180], width=28)
            return False
        finally:
            if epoch == self.epoch:
                self.page_loading.finish()

    def follow_link(self, widget, url, **kwargs):
        if not self.valid() or self.path is None:
            return False
        if url == self.base + '?drawer=files':
            self.sidebar.show_sidebar()
            return False
        if url == self.base + '?drawer=links':
            self.host.loop.create_task(self.show_links())
            return False
        parsed = urlsplit(url)
        if not parsed.scheme and not parsed.netloc:
            target = url
        elif url.split("?", 1)[0] == self.base:
            target = parse_qs(parsed.query).get("target", [""])[0]
        else:
            return False
        link = urlsplit(target)
        if not link.path and link.fragment:
            if getattr(self, 'data_views_loading', False):
                self.pending_fragment = link.fragment
            self.scroll_fragment(link.fragment)
            return False
        if (
            link.scheme
            or link.netloc
            or link.query
            or not link.path
            or link.path.startswith(("/", "\\"))
        ):
            return False
        try:
            self.contained(
                posixpath.normpath(
                    posixpath.join(posixpath.dirname(self.path), unquote(link.path))
                )
            )
        except ValueError:
            return False
        self.host.loop.create_task(self.open_note(target, resolve_link=True))
        return False

    def scroll_fragment(self, fragment):
        import json

        self.web.evaluate_javascript(
            "(function(){const h=document.getElementById("
            + json.dumps(unquote(fragment))
            + ");if(h)h.scrollIntoView();})()"
        )

    def page_loaded(self, widget=None, url=None, **kwargs):
        if (self._open_timing is not None and self._open_timing.get('published_epoch') == self.epoch
                and 'dom_ready' not in self._open_timing['stages_ms']):
            self.mark_open_timing('dom_ready', self.epoch)
        plan = getattr(self, 'data_view_plan', None)
        if plan is not None:
            self.data_view_plan = None
            self.data_view_task = self.host.loop.create_task(self.render_data_views(plan, self.base, self.path))
        from .notes_swipe import document_swipes
        self.web.evaluate_javascript(document_swipes(self.base))
        self.page_search.loaded(reveal=not bool(self.pending_fragment))
        if self.pending_fragment and not getattr(self, 'data_views_loading', False):
            fragment, self.pending_fragment = self.pending_fragment, ""
            self.scroll_fragment(fragment)
        elif not self.pending_fragment and self.path in self.positions:
            self.web.evaluate_javascript('window.scrollTo(0,' + str(self.positions[self.path]) + ')')

    def data_view_html(self, html, *, active=False):
        html = re.sub(r'href="([^"]*)"', lambda match: 'href="' + self.base + '?target='
                      + quote(unescape(match[1]), safe='') + '"', html)
        if active:
            html = html.replace('<body>', '<body data-logistics-data-view="' + self.base + '">', 1)
            return worker_policy(html)
        return html

    def cancel_data_views(self):
        self.data_view_plan = None
        self.data_views_loading = False
        task = getattr(self, 'data_view_task', None)
        running = task is not None and not task.done()
        if running:
            task.cancel()
        self.data_view_task = None
        # Navigation/retirement replaces the document as well; terminate promptly
        # while an opening worker or an editor transition is still pending.
        if running:
            from ..dataview_script import STOP
            self.web.evaluate_javascript(STOP)

    async def render_data_views(self, plan, base, path):
        from .dataview import execute_views
        # Opening attempts may fail while this document remains visible. Its
        # publication token changes only after a replacement is ready.
        def valid():
            return self.valid() and self.base == base and self.path == path and not self.editing
        try:
            text = await asyncio.wait_for(execute_views(self.web, self.library, path, plan,
                valid=valid, marker=base), timeout=35)
            if text is None or not valid():
                return
            def render():
                html = self.host.preview(text, image_source=self.library.image_source(path))
                self.access.validate_preview(html, MAX_NOTE)
                return html
            html = await asyncio.to_thread(render)
            if valid():
                await self.remember_position()
                if valid():
                    self.page_search.loading()
                    self.data_views_loading = False
                    set_inline_html(self.web, self.base, self.data_view_html(html))
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, asyncio.TimeoutError) as error:
            if valid():
                self.data_views_loading = False
                self.notice.text = 'Data view error: ' + (str(error)[:160] or 'execution exceeded 35 seconds.')

    async def remember_position(self):
        from commonUtils.ui.native.text_size import native_backend
        if self.path is None or self.editing or not native_backend(self.web).startswith(('toga_iOS.', 'toga_android.')):
            return
        path = self.path
        try:
            position = await asyncio.wait_for(self.web.evaluate_javascript('window.scrollY'), timeout=.25)
            if self.valid() and self.path == path and isinstance(position, (int, float)):
                self.positions[path] = max(0, int(position))
        except Exception:
            # A retired page has no position to retain. Reading still owns the
            # original note and no source content crosses this presentation path.
            return

    def back_action(self):
        """Close compact browsing before retracing note links."""
        if not self.sidebar.expanded and self.sidebar.sidebar_open:
            return self.sidebar.show_detail
        opening = getattr(self, 'page_loading', None)
        if opening is not None and opening.active:
            return opening.cancel
        if getattr(self, '_document_return_side', None) is not None:
            return self.return_to_browsing
        if self.history_index > 0:
            return self.previous_note
        return None

    def return_to_browsing(self):
        side, self._document_return_side = self._document_return_side, None
        self.sidebar.show(side)
        self.host.render()

    async def previous_note(self, widget=None, **kwargs):
        await self.navigate_history(-1)

    async def next_note(self, widget=None, **kwargs):
        await self.navigate_history(1)

    async def navigate_history(self, offset):
        index = self.history_index + offset
        if 0 <= index < len(self.history) and await self.open_note(
            self.history[index], remember=False
        ):
            self.history_index = index
            self.back_button.enabled = index > 0
            self.forward_button.enabled = index < len(self.history) - 1
            self.refresh_reader_actions()
            self.host.render()

    def close(self, widget=None, **kwargs):
        if self.session is not None:
            return self.host.close_session(self.session.id)

    async def browse_parent(self, widget=None, **kwargs):
        if self.path is not None:
            await self.reveal_folder(posixpath.dirname(self.path), select=False)
            self.sidebar.show_sidebar()

    def present(self, *, destination=None):
        if self.valid() and self.session is not None:
            self.destination = destination or self.host.destination()
            self.host.workspace.activate(self.session.id)
            return self.host.show_view(
                self.view,
                destination=self.destination,
                route="notes-library:" + self.session.id,
                title=self.session.title,
            )

    def cancel_links(self):
        self.links_generation += 1
        task, self.links_refresh_task = self.links_refresh_task, None
        if task is not None:
            task.cancel()

    def refresh_library_indexes(self):
        if not self.valid():
            return
        if self.search.value:
            self.search_changed()
        self.cancel_links()
        if self.sidebar.side == 'links':
            self.links_refresh_task = self.host.loop.create_task(self.show_links(refresh=True))

    async def show_links(self, widget=None, *, refresh=False, **kwargs):
        if not self.valid():
            return
        if refresh and self.sidebar.side != 'links':
            return
        if self.sidebar.side == 'links' and not refresh:
            self.sidebar.show_detail()
            self.links_generation += 1
            return
        self.sidebar.show_links()
        self.link_rows.clear()
        if self.path is None:
            self.link_rows.add(toga.Label('Open a note to see its connections.'))
            return
        if PurePosixPath(self.path).suffix.lower() not in MARKDOWN:
            self.link_rows.add(toga.Label('Connections are available for Markdown documents.'))
            return
        self.links_generation += 1
        generation, path = self.links_generation, self.path
        cancelled = lambda: not self.valid() or generation != self.links_generation
        self.link_rows.add(toga.Label('Finding local connections…'))
        spinner = toga.ActivityIndicator()
        self.link_rows.add(spinner)
        spinner.start()
        try:
            from features.text_editor.notes_links import connections
            result = await asyncio.to_thread(connections, self.library, path,
                cancelled=cancelled, visible=self.host.folder_visible)
            if cancelled():
                return
            self.link_rows.clear()
            self.link_rows.add(toga.Label(PurePosixPath(path).name),
                toga.Label(f"{result['words']:,} words · {result['characters']:,} characters",
                           style=Pack(font_size=12, margin_bottom=12)))
            for key, title in (('incoming', 'Backlinks'), ('outgoing', 'Outgoing links')):
                self.link_rows.add(toga.Label(f'{title} ({len(result[key])})',
                    style=Pack(font_weight='bold', margin_top=12)))
                if not result[key]:
                    self.link_rows.add(toga.Label('No ' + title.lower() + '.'))
                for target in result[key]:
                    async def choose(widget=None, target=target, **kwargs):
                        await self.open_note(target)
                    label = str(PurePosixPath(target).relative_to(self.root or '.'))
                    self.link_rows.add(self.host.list_button(toga.Button(label,
                        on_press=choose, style=Pack(height=48))))
            if result['unresolved']:
                self.link_rows.add(toga.Label('Unresolved links', style=Pack(font_weight='bold', margin_top=12)))
                for target in result['unresolved']:
                    self.link_rows.add(toga.Label(target))
        except OperationCancelled:
            pass
        except (OSError, ValueError, UnicodeError) as error:
            if not cancelled():
                self.link_rows.clear()
                self.link_rows.add(toga.Label(fill(str(error)[:180], width=30)))
        finally:
            spinner.stop()
            self.sidebar.refresh_gestures()

    async def open_canvas(self, path, *, remember=True):
        if self.host.document_editor is None:
            return False
        return await self.open_embedded(path, self.host.document_editor, remember=remember)

    async def open_embedded(self, path, opener, *, remember=True):
        """One navigation/lifetime path for source editors and notebook canvases."""
        path = self.contained(path)
        self.epoch += 1
        epoch = self.epoch
        if not hasattr(self, 'page_loading'):
            self.page_loading = LibraryOpening(self)
        self.page_loading.start(path)
        try:
            editor = await opener(self, path)
        except (OSError, ValueError, OperationCancelled) as error:
            if self.valid() and epoch == self.epoch:
                self.notice.text = str(error)
            return False
        finally:
            if epoch == self.epoch:
                self.page_loading.finish()
        if not self.valid() or epoch != self.epoch:
            editor.dispose()
            return False
        self.cancel_data_views()
        self.retire_editor()
        self.embedded = editor
        self.editing = True
        self.path = self.selected_path = path
        self.update_tree_selection()
        self.title.text = fill(PurePosixPath(path).name, width=28)
        self.speech.close()
        self.up_button.enabled = True
        if remember and (self.history_index < 0 or self.history[self.history_index] != path):
            del self.history[self.history_index + 1:]
            self.history.append(path)
            self.history_index = len(self.history) - 1
        self.article.clear()
        self.article.add(editor.view)
        self.edit.enabled = False
        self.back_button.enabled = self.history_index > 0
        self.forward_button.enabled = self.history_index < len(self.history) - 1
        self.notice.text = ''
        self.refresh_reader_actions()
        self.refresh_chrome()
        self.render_tree()
        self.sidebar.show_detail()
        self.host.render()
        return True

    async def open_editor(self, widget=None, **kwargs):
        if not self.valid() or self.path is None or not self.library.writable:
            return False
        if self.editing:
            return await self.open_note(self.path, remember=False)
        self.sidebar.show_detail()
        from .library_document import LibraryMarkdown
        path = self.path
        self.epoch += 1
        epoch = self.epoch
        await self.remember_position()
        if not self.valid() or epoch != self.epoch or self.path != path:
            return False
        try:
            editor = await LibraryMarkdown.open(self, path)
        except (OSError, ValueError, UnicodeError, OperationCancelled) as error:
            if self.valid() and epoch == self.epoch:
                self.notice.text = str(error)
            return False
        if not self.valid() or epoch != self.epoch or self.path != path:
            editor.dispose()
            return False
        self.cancel_data_views()
        self.embedded, self.editing = editor, True
        self.article.clear()
        self.article.add(editor.view)
        self.refresh_reader_actions()
        self.refresh_chrome()
        self.host.render()
        return True

    async def open_text(self, path, *, remember=True):
        from .library_text import LibraryText
        return await self.open_embedded(path, LibraryText.open, remember=remember)

    def new_note(self, widget=None, **kwargs):
        async def choose():
            if not self.valid() or not self.library.supports('create'):
                return False
            extension = await self.host.choose_type() if self.host.choose_type else 'md'
            if self.valid() and extension in ('md', 'rmdoc'):
                self.name_document(extension)
        return self.host.loop.create_task(choose())

    def name_document(self, extension, filename=''):
        name = toga.TextInput(value=filename, placeholder='Untitled.' + extension, style=Pack(height=48))
        status = toga.Label('')
        async def next_step(widget=None, **kwargs):
            try:
                from features.text_editor.names import document_name
                filename = document_name(name.value or 'Untitled.' + extension)
                suffixes = MARKDOWN if extension == 'md' else {'.' + extension}
                if PurePosixPath(filename).suffix.lower() not in suffixes:
                    filename += '.' + extension
                await self.choose_location(filename, extension, self.selected_parent())
            except (OSError, ValueError) as error:
                status.text = str(error)
        form = toga.Box(children=[toga.Label('Name your document', style=Pack(font_size=20)),
            toga.Label('Remarkable Document' if extension == 'rmdoc' else 'Markdown'), name, status,
            toga.Button('Choose location', on_press=next_step, style=Pack(height=48)),
            toga.Button('Cancel', on_press=lambda widget: self.present(), style=Pack(height=48))],
            style=Pack(direction=COLUMN, margin=16))
        return self.host.show_view(form, destination=self.destination, route='notes-new', title='New document')

    async def choose_location(self, name, extension, parent):
        if not self.valid():
            return
        parent = self.contained(parent)
        rows = await asyncio.to_thread(self.library.folders, parent, cancelled=lambda: not self.valid())
        if not self.valid():
            return
        status = toga.Label('')
        create = toga.Button('Create here', style=Pack(height=48))
        async def submit(widget=None, **kwargs):
            if not self.valid() or not create.enabled:
                return
            create.enabled = False
            try:
                path = await asyncio.to_thread(self.library.create, name, parent, extension=extension,
                                              cancelled=lambda: not self.valid())
                if not self.valid():
                    return
                await self.load_folder(parent)
                if self.search.value:
                    self.search_changed()
                self.present()
                if await self.open_note(path) and extension == 'md':
                    await self.open_editor()
            except (OSError, ValueError) as error:
                if self.valid():
                    status.text = str(error)
            finally:
                create.enabled = True
        create.on_press = submit
        folders = toga.Box(style=Pack(direction=COLUMN))
        if parent != self.root:
            async def up(widget=None, **kwargs):
                await self.choose_location(name, extension, posixpath.dirname(parent))
            folders.add(toga.Button('Parent folder', on_press=up, style=Pack(height=48)))
        for row in rows:
            if row['directory']:
                async def enter(widget=None, path=row['path'], **kwargs):
                    await self.choose_location(name, extension, path)
                folders.add(toga.Button(row['name'], on_press=enter, style=Pack(height=48)))
        form = toga.Box(children=[toga.Label('Save inside Notes Library', style=Pack(font_size=20)),
            toga.Label(parent or 'Library root'), toga.Label(name),
            toga.ScrollContainer(content=folders, horizontal=False, style=Pack(flex=1)), status, create,
            toga.Button('Back to name', on_press=lambda widget: self.name_document(extension, name), style=Pack(height=48)),
            toga.Button('Cancel', on_press=lambda widget: self.present(), style=Pack(height=48))],
            style=Pack(direction=COLUMN, flex=1, margin=16))
        self.host.show_view(form, destination=self.destination, route='notes-new', title='Choose location')

    def selected_parent(self):
        selected = self.selected_path
        if selected in self.folders or selected in self.expanded:
            return selected
        rows = (row for entries in self.folders.values() for row in entries)
        if any(row['path'] == selected and row['directory'] for row in rows) or any(
                row['path'] == selected and row['directory'] for row in self.search_rows):
            return selected
        return posixpath.dirname(selected) if selected else self.root

    def manage_entry(self, *, folder=False, move=False):
        if not self.valid() or not self.library.supports('rename' if move else 'create'):
            return False
        source = self.selected_path if move else None
        if move and source is None:
            return False
        title = 'Rename or move' if move else 'New folder'
        initial = PurePosixPath(source).relative_to(self.root or '.').as_posix() if move else ''
        name = toga.TextInput(value=initial, style=Pack(height=48))
        status = toga.Label('Links are not rewritten.' if move else '')
        submit_button = toga.Button('Move' if move else 'Create folder', style=Pack(height=48))
        cancel = toga.Button('Cancel', on_press=lambda widget: self.present(), style=Pack(height=48))
        parent = self.selected_parent()
        async def submit(widget=None, **kwargs):
            if not self.valid() or self.file_command_busy:
                return
            self.file_command_busy = True
            submit_button.enabled = cancel.enabled = False
            try:
                moving_open = bool(move and self.path and (self.path == source or self.path.startswith(source + '/')))
                if moving_open and not await self.prepare_leave():
                    return
                if move:
                    destination = posixpath.join(self.root, name.value)
                    await asyncio.to_thread(self.library.move, source, destination, cancelled=lambda: not self.valid())
                    if not self.valid():
                        return
                    if moving_open:
                        self.retire_editor()
                    def remap(path):
                        return destination + path[len(source):] if path is not None and (
                            path == source or path.startswith(source + '/')) else path
                    self.history = [remap(path) for path in self.history]
                    self.positions = {remap(path): value for path, value in self.positions.items()}
                    self.path, self.selected_path = remap(self.path), destination
                    self.expanded = {remap(path) for path in self.expanded}
                    paths = {remap(path) for path in self.folders}
                    paths.add(posixpath.dirname(destination))
                else:
                    await asyncio.to_thread(self.library.create_folder, name.value, parent,
                                            cancelled=lambda: not self.valid())
                    paths = set(self.folders) | {parent}
                if not self.valid():
                    return
                self.epoch += 1
                self.folders.clear()
                for path in sorted(paths | {self.root}):
                    await self.load_folder(path)
                if self.search.value:
                    self.search_changed()
                self.present()
                if moving_open:
                    await self.open_note(self.path, remember=False)
                self.refresh_reader_actions()
            except OperationCancelled:
                return
            except (OSError, ValueError) as error:
                if self.valid():
                    status.text = fill(str(error)[:180], width=28)
            finally:
                self.file_command_busy = False
                submit_button.enabled = cancel.enabled = True
        submit_button.on_press = submit
        form = toga.Box(children=[toga.Label(title, style=Pack(font_size=20)),
            toga.Label('Path inside Notes Library (existing folders)' if move else 'Folder name'),
            name, status, submit_button, cancel], style=Pack(direction=COLUMN, margin=16))
        return self.host.show_view(toga.ScrollContainer(content=form, horizontal=False, style=Pack(flex=1)),
                                  destination=self.destination, route='notes-manage', title=title)

    def show_page_search(self, widget=None, **kwargs):
        if self.valid() and self.path is not None:
            self.sidebar.show_detail()
            self.page_search.show()

    def dispose(self):
        self.cancel_data_views()
        task = getattr(self, 'tree_task', None)
        if task is not None:
            task.cancel()
        for row in getattr(self, '_row_cache', {}).values():
            for button in row.children:
                if hasattr(button, 'vault_path'):
                    self.release_file_hold(button)
        self._row_cache = {}
        self.dispose_panels()
        self.retire_editor()
        self.sidebar.show_detail()
        self.cancel_links()
        self.link_rows.clear()
        if hasattr(self, 'page_loading'):
            self.page_loading.finish()
        self.page_search.dispose()
        self.reader_actions.dispose()
        self.speech.close()
        self.speech.button.enabled = False
        self.cancelled.set()
        self._open_timing = None
        self.library.close()
        if self.search_task is not None:
            self.search_task.cancel()
        self.search_rows.clear()
        if self.search is not None:
            self.search.value = ""
        self.epoch += 1
        self.folders.clear()
        self.folder_pages.clear()
        self.expanded.clear()
        self.rows.clear()
        self.path = self.selected_path = None
        self.root = ""
        self.title.text = "Notes Library closed"
        self.edit.enabled = False
        self.notice.text = "Reopen Notes Library from the location actions."
        self.history.clear()
        self.positions.clear()
        if self.session is not None and self.session.id in self.host.workspace.sessions:
            self.host.workspace.close(self.session.id, guard=lambda session: True)
        self.session = None
        from services.documents.mobile_views import retire_webview

        if hasattr(self.web, "clear_private_content"):
            self.web.clear_private_content()
        else:
            retire_webview(self.web)
        self.release_provider()
        self.release_provider = lambda: None
