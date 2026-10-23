"""Feature-owned provider Notes Library browser with explicit host services."""

import asyncio
import posixpath
import re
from html import unescape
from pathlib import PurePosixPath
from threading import Event
from textwrap import fill
from urllib.parse import parse_qs, quote, unquote, urlsplit
from uuid import uuid4
from dataclasses import dataclass
from typing import Callable
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from features.text_editor.notes import NotesLibrary, MAX_NOTE, MARKDOWN
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.ui.native.adaptive import AdaptiveSidebar, allocated_width


@dataclass(frozen=True)
class NotesHost:
    presentation: object
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
    show_view: Callable
    destination: Callable
    render: Callable
    open_editor: Callable
    speech: Callable
    commands: Callable
    list_button: Callable
    middle_filename: Callable
    entry_icon: Callable
    highlight_entry: Callable
    preview: Callable


class VaultBrowser:
    def __init__(self, host, provider, root, destination):
        self.host, self.provider, self.destination = host, provider, destination
        self.library = NotesLibrary(provider, root)
        self.root = self.library.root
        self.history, self.history_index = [], -1
        self.session = None
        self.client = host.client()
        self.generation = getattr(self.client, "generation", None)
        self.cancelled = Event()
        self.folders, self.expanded, self.loading = {}, {self.root}, set()
        self.path = None
        self.selected_path = None
        self.epoch = 0
        self.shown = 500
        self.base = "https://markdown.invalid/vault/" + uuid4().hex + "/"
        self.rows = toga.Box(style=Pack(direction=COLUMN))
        self.notice = toga.Label("", style=Pack(font_size=12))
        self.tree = toga.Box(
            children=[
                toga.Label("Markdown notes", style=Pack(font_size=18)),
                toga.ScrollContainer(
                    content=self.rows, horizontal=False, style=Pack(flex=1)
                ),
            ],
            style=Pack(direction=COLUMN, flex=1),
        )
        self.title = toga.Label(
            "Choose a Markdown note", style=Pack(font_size=18, flex=1)
        )
        self.edit = self.host.presentation.icon_button(
            "edit", "Edit Markdown", on_press=self.open_editor, enabled=False
        )
        from commonUtils.ui.native.private_webview import (
            PrivateWebView,
            private_webview_supported,
        )

        web_type = (
            PrivateWebView
            if provider.private and private_webview_supported()
            else toga.WebView
        )
        self.pending_fragment = ""
        private_options = {"max_html_bytes": MAX_NOTE} if web_type is PrivateWebView else {}
        self.web = web_type(
            on_navigation_starting=self.follow_link,
            **private_options,
            on_webview_load=self.page_loaded,
            style=Pack(flex=1),
        )
        host.presentation.bind_font(self.web, "markdown", web=True)
        self.article = toga.Box(
            children=[self.web], style=Pack(direction=COLUMN, flex=1)
        )
        from commonUtils.ui.native.markdown_search import MarkdownPageSearch
        self.page_search = MarkdownPageSearch(self.web, self.article, valid=self.valid)
        self.speech = host.speech(
            self.web,
            self.article,
            document_title=lambda: "" if self.provider.private else self.path,
            privacy_gate=lambda: host.privacy_gate() if self.provider.private else None,
            valid=lambda: not self.cancelled.is_set()
            and host.active()
            and (
                not self.provider.private
                or (
                    self.client is host.client()
                    and self.generation == getattr(self.client, "generation", None)
                )
            ),
        )
        self.speech.button.enabled = False
        self.sidebar = AdaptiveSidebar(
            self.tree, self.article, label="Vault folders and Markdown notes"
        )
        self.menu = host.presentation.menu_button(
            self.sidebar.toggle, label="Browse Notes Library"
        )
        self.back_button = self.host.presentation.icon_button(
            "back",
            "Previous note",
            on_press=lambda w: self.navigate_history(-1),
            enabled=False,
        )
        self.forward_button = self.host.presentation.icon_button(
            "forward",
            "Next note",
            on_press=lambda w: self.navigate_history(1),
            enabled=False,
        )
        self.up_button = self.host.presentation.icon_button(
            "up", "Browse parent folder", on_press=self.browse_parent, enabled=False
        )
        self.search = None
        if not self.library.remote:
            self.search = toga.TextInput(
                placeholder="Filter loaded file names",
                on_change=lambda w: self.render_tree(),
                style=Pack(height=48),
            )
            self.tree.insert(1, self.search)
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
        self.view = toga.Box(
            children=[self.toolbar, self.notice, self.sidebar.view],
            style=Pack(direction=COLUMN, flex=1),
        )
        self.reader_actions_button = self.host.presentation.icon_button(
            "more", "Note actions"
        )
        self.view._workspace_menu_button = self.menu
        self.view._native_reader_toolbar = self.toolbar
        self.view._native_reader_title = (
            lambda: PurePosixPath(self.path).name if self.path else "Notes Library"
        )
        self.view._native_reader_buttons = lambda: [
            *(
                [self.edit if not self.library.remote else self.speech.button]
                if self.path
                else []
            ),
            self.reader_actions_button,
        ]
        self.refresh_reader_actions()
        self.reflow(host.content_width(destination))
        self.sidebar.show_sidebar()

    def valid(self):
        if self.cancelled.is_set() or not self.host.active():
            return False
        if self.provider.private:
            return (
                self.client is self.host.client()
                and self.generation == getattr(self.client, "generation", None)
                and not any(gate.locked for gate in self.host.privacy_gates())
            )
        return True

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
            self.sidebar.policy.sidebar_width if self.sidebar.expanded else available
        )
        self.menu.enabled = self.host.apple or not self.sidebar.expanded

    def refresh_reader_actions(self):
        if hasattr(self, "reader_actions"):
            self.reader_actions.dispose()
        actions = []
        if self.path is not None:
            actions.append(("Find in this page…", self.show_page_search))
            actions.append(("Read aloud…", self.speech.show))
        if self.back_button.enabled:
            actions.append(("Previous note", lambda: self.navigate_history(-1)))
        if self.forward_button.enabled:
            actions.append(("Next note", lambda: self.navigate_history(1)))
        if self.up_button.enabled:
            actions.append(("Browse parent folder", self.browse_parent))
        actions.append(("All documents", self.host.show_documents))
        self.reader_actions = self.host.commands(
            self.reader_actions_button, actions, self.browse_parent
        )

    async def load_folder(self, path):
        if not self.valid() or path in self.loading:
            return False
        self.loading.add(path)
        self.notice.text = "Loading notes…"
        try:
            path = self.contained(path)
            rows = await asyncio.to_thread(
                self.library.folders, path, cancelled=lambda: not self.valid()
            )
            if not self.valid():
                return False
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
                        or PurePosixPath(row["name"]).suffix.lower() in MARKDOWN
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

    def render_tree(self):
        if not self.valid():
            return
        self.rows.clear()
        flattened = []

        def add(folder, depth=0):
            for entry in self.folders.get(folder, ()):
                if not self.host.folder_visible(
                    entry["path"], directory=entry["directory"]
                ):
                    continue
                flattened.append((entry, depth))
                if entry["directory"] and entry["path"] in self.expanded:
                    add(entry["path"], depth + 1)

        add(self.root)
        query = (self.search.value or "").casefold() if self.search is not None else ""
        flattened = [
            (entry, depth)
            for entry, depth in flattened
            if entry["directory"] or not query or query in entry["path"].casefold()
        ]
        for entry, depth in flattened[: self.shown]:
            path, directory = entry["path"], entry["directory"]

            async def choose(widget=None, path=path, directory=directory, **kwargs):
                if directory:
                    await self.toggle_folder(path)
                else:
                    await self.open_note(path)

            label = (
                ("▾ " if path in self.expanded else "▸ ") if directory else ""
            ) + entry["name"]
            button = self.host.list_button(
                toga.Button(label, on_press=choose, style=Pack(height=48, flex=1))
            )
            self.host.middle_filename(button)
            button.vault_path = path
            row = toga.Box(
                children=[
                    toga.Box(style=Pack(width=depth * 20)),
                    self.host.entry_icon(directory),
                    button,
                ],
                style=Pack(direction=ROW, align_items=CENTER),
            )
            self.host.highlight_entry(row, path == self.selected_path)
            self.host.highlight_entry(button, path == self.selected_path)
            self.rows.add(row)
        if len(flattened) > self.shown:

            def more(widget=None, **kwargs):
                self.shown += 500
                self.render_tree()

            self.rows.add(
                toga.Button("Show more notes", on_press=more, style=Pack(height=48))
            )
        elif not flattened:
            self.rows.add(toga.Label("No Markdown notes in this folder."))

    async def open_note(self, path, *, remember=True, fragment=""):
        if not self.valid():
            return False
        self.speech.close()
        self.epoch += 1
        epoch = self.epoch
        try:
            path = self.contained(path)
            if PurePosixPath(path).suffix.lower() not in MARKDOWN:
                raise ValueError("Choose a Markdown note.")

            def read():
                data = self.library.read(path, cancelled=lambda: not self.valid())
                html = self.host.preview(data.decode("utf-8-sig"))
                if self.provider.private and len(html.encode("utf-8")) > MAX_NOTE:
                    raise ValueError(
                        "Private preview exceeds the 2 MiB memory-only limit."
                    )
                return html

            html = await asyncio.to_thread(read)
            if not self.valid() or epoch != self.epoch:
                return False
            if remember and path != self.path:
                del self.history[self.history_index + 1 :]
                self.history.append(path)
                self.history_index = len(self.history) - 1
            self.path = self.selected_path = path
            self.render_tree()
            self.title.text = fill(PurePosixPath(path).name, width=28)
            self.base = "https://markdown.invalid/vault/" + uuid4().hex + "/"
            html = re.sub(
                r'href="([^"]*)"',
                lambda match: 'href="'
                + self.base
                + "?target="
                + quote(unescape(match[1]), safe="")
                + '"',
                html,
            )
            self.pending_fragment = fragment
            self.page_search.loading()
            self.web.set_content(self.base, html)
            self.edit.enabled = True
            self.speech.button.enabled = True
            self.notice.text = ""
            self.back_button.enabled = self.history_index > 0
            self.forward_button.enabled = self.history_index < len(self.history) - 1
            self.up_button.enabled = True
            self.refresh_reader_actions()
            self.sidebar.show_detail()
            self.host.render()
            return True
        except OperationCancelled:
            return False
        except (OSError, UnicodeError, ValueError) as error:
            if self.valid() and epoch == self.epoch:
                self.notice.text = fill(str(error)[:180], width=28)
            return False

    def follow_link(self, widget, url, **kwargs):
        if not self.valid() or self.path is None:
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
            path = self.contained(
                posixpath.normpath(
                    posixpath.join(posixpath.dirname(self.path), unquote(link.path))
                )
            )
        except ValueError:
            return False
        self.host.loop.create_task(self.open_note(path, fragment=link.fragment))
        return False

    def scroll_fragment(self, fragment):
        import json

        self.web.evaluate_javascript(
            "(function(){const h=document.getElementById("
            + json.dumps(unquote(fragment))
            + ");if(h)h.scrollIntoView();})()"
        )

    def page_loaded(self, widget=None, **kwargs):
        self.page_search.loaded(reveal=not bool(self.pending_fragment))
        if self.pending_fragment:
            fragment, self.pending_fragment = self.pending_fragment, ""
            self.scroll_fragment(fragment)

    def back_action(self):
        """Close compact browsing before retracing note links."""
        if not self.sidebar.expanded and self.sidebar.sidebar_open and self.path is not None:
            return self.sidebar.show_detail
        if self.history_index > 0:
            return lambda: self.navigate_history(-1)
        return None

    async def navigate_history(self, offset):
        index = self.history_index + offset
        if 0 <= index < len(self.history) and await self.open_note(
            self.history[index], remember=False
        ):
            self.history_index = index
            self.back_button.enabled = index > 0
            self.forward_button.enabled = index < len(self.history) - 1
            self.refresh_reader_actions()

    async def browse_parent(self, widget=None, **kwargs):
        if self.path is not None:
            parent = posixpath.dirname(self.path)
            self.expanded.add(parent)
            if parent not in self.folders:
                await self.load_folder(parent)
            self.sidebar.show_sidebar()
            self.render_tree()

    def present(self):
        if self.valid() and self.session is not None:
            self.destination = self.host.destination()
            self.host.workspace.activate(self.session.id)
            return self.host.show_view(
                self.view,
                route="notes-library:" + self.session.id,
                title=self.session.title,
            )

    async def open_editor(self, widget=None, **kwargs):
        if not self.valid() or self.path is None:
            return False
        return await self.host.open_editor(
            self.provider, self.path, self.destination, self.library.remote, self.client
        )

    def show_page_search(self, widget=None, **kwargs):
        if self.valid() and self.path is not None:
            self.sidebar.show_detail()
            self.page_search.show()

    def dispose(self):
        self.page_search.dispose()
        self.reader_actions.dispose()
        self.speech.close()
        self.speech.button.enabled = False
        self.cancelled.set()
        if self.search is not None:
            self.search.value = ""
        self.epoch += 1
        self.folders.clear()
        self.expanded.clear()
        self.rows.clear()
        self.path = self.selected_path = None
        self.root = ""
        self.title.text = "Notes Library closed"
        self.edit.enabled = False
        self.notice.text = "Reopen Notes Library from the location actions."
        self.history.clear()
        if self.session is not None and self.session.id in self.host.workspace.sessions:
            self.host.workspace.close(self.session.id, guard=lambda session: True)
        self.session = None
        from features.text_editor.mobile.markdown_editor import retire_webview

        if hasattr(self.web, "clear_private_content"):
            self.web.clear_private_content()
        else:
            retire_webview(self.web)
