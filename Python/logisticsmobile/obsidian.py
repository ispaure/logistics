"""Provider-owned Obsidian vault browsing; private notes never become disk previews."""
import asyncio
import posixpath
import re
from html import unescape
from pathlib import PurePosixPath
from threading import Event
from textwrap import fill
from urllib.parse import parse_qs, quote, unquote, urlsplit
from uuid import uuid4

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from features.text_editor.notes import NotesLibrary, vault_root, MAX_NOTE, MARKDOWN
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.ui.native.adaptive import AdaptiveSidebar, allocated_width
from .appearance import list_button
from .control_icons import icon_button
from .browser_ui import entry_icon, highlight_entry
from .preview import markdown_preview

async def open_vault(app, provider, root, destination='documents', *, title='', rows=None):
    if not app.checkpoint():
        return None
    previous = getattr(app, 'vault_browser', None)
    if previous is not None:
        previous.dispose()
    owner = VaultBrowser(app, provider, root, destination)
    owner.session = app.workspace.open('notes-library', uuid4().hex, 'markdown',
        'Notes Library' + (' — ' + title if title else ''), transient=True)
    app.vault_browser = owner
    if app.show_view(owner.view, destination=destination, route='notes-library:' + owner.session.id, title=owner.session.title) is False:
        owner.dispose()
        return None
    if rows is None:
        await owner.load_folder(owner.root)
    else:
        owner.folders[owner.root] = owner.library.visible_rows(rows)
        owner.render_tree()
    return owner


class VaultBrowser:
    def __init__(self, app, provider, root, destination):
        self.app, self.provider, self.destination = app, provider, destination
        self.library = NotesLibrary(provider, root)
        self.root = self.library.root
        self.history, self.history_index = [], -1
        self.session = None
        self.client = getattr(app, 'cloud_client', None)
        self.generation = getattr(self.client, 'generation', None)
        self.cancelled = Event()
        self.folders, self.expanded, self.loading = {}, {self.root}, set()
        self.path = None
        self.selected_path = None
        self.epoch = 0
        self.shown = 500
        self.base = 'https://markdown.invalid/vault/' + uuid4().hex + '/'
        self.rows = toga.Box(style=Pack(direction=COLUMN))
        self.notice = toga.Label('', style=Pack(font_size=12))
        self.tree = toga.Box(children=[toga.Label('Markdown notes', style=Pack(font_size=18)),
            toga.ScrollContainer(content=self.rows, horizontal=False, style=Pack(flex=1))],
            style=Pack(direction=COLUMN, flex=1))
        self.title = toga.Label('Choose a Markdown note', style=Pack(font_size=18, flex=1))
        self.edit = icon_button('edit', 'Edit Markdown', on_press=self.open_editor, enabled=False)
        from features.books.mobile.private_view import PrivateWebView, private_webview_supported
        web_type = PrivateWebView if provider.private and private_webview_supported() else toga.WebView
        self.pending_fragment = ''
        self.web = web_type(on_navigation_starting=self.follow_link, on_webview_load=self.page_loaded, style=Pack(flex=1))
        self.article = toga.Box(children=[self.web], style=Pack(direction=COLUMN, flex=1))
        from .markdown_speech import MarkdownSpeech
        self.speech = MarkdownSpeech(app, self.web, self.article,
            privacy_gate=lambda: getattr(app.cloud_client, "session_privacy", None) if self.provider.private else None,
            valid=lambda: not self.cancelled.is_set() and app.active_host
                and (not self.provider.private or (self.client is app.cloud_client
                    and self.generation == getattr(self.client, "generation", None))))
        self.speech.button.enabled = False
        self.sidebar = AdaptiveSidebar(self.tree, self.article, label='Vault folders and Markdown notes')
        from .workspace_navigation import menu_button
        self.menu = menu_button(self.sidebar.toggle, label='Browse Notes Library')
        self.back_button = icon_button('back', 'Previous note', on_press=lambda w: self.navigate_history(-1), enabled=False)
        self.forward_button = icon_button('forward', 'Next note', on_press=lambda w: self.navigate_history(1), enabled=False)
        self.up_button = icon_button('up', 'Browse parent folder', on_press=self.browse_parent, enabled=False)
        self.search = None
        if not self.library.remote:
            self.search = toga.TextInput(placeholder='Filter loaded notes', on_change=lambda w: self.render_tree(), style=Pack(height=48))
            self.tree.insert(1, self.search)
        self.toolbar = toga.Box(children=[self.menu, self.back_button, self.forward_button, self.up_button,
            toga.Box(style=Pack(flex=1)), self.edit, self.speech.button], style=Pack(direction=ROW))
        self.view = toga.Box(children=[self.toolbar, self.notice, self.sidebar.view], style=Pack(direction=COLUMN, flex=1))
        self.reflow(app.adaptive.content_width(destination, margin=0))
        self.sidebar.show_sidebar()

    def valid(self):
        if self.cancelled.is_set() or not self.app.active_host:
            return False
        if self.provider.private:
            return (self.client is getattr(self.app, 'cloud_client', None)
                    and self.generation == getattr(self.client, 'generation', None)
                    and not any(gate.locked for gate in self.app.screen_privacy.gates()))
        return True

    def contained(self, path):
        return self.library.contained(path)

    def reflow(self, width):
        available = max(0, allocated_width(self.view, width) - 24)
        self.sidebar.reflow(available)
        # Compact browsing still needs its menu while the article is hidden.
        # Wide layouts keep document commands over their own article pane.
        parent = self.article if self.sidebar.expanded else self.view
        if self.toolbar.parent is not parent:
            self.toolbar.parent.remove(self.toolbar)
            parent.insert(0, self.toolbar)
        self.rows.style.width = self.sidebar.policy.sidebar_width if self.sidebar.expanded else available
        self.menu.enabled = not self.sidebar.expanded

    async def load_folder(self, path):
        if not self.valid() or path in self.loading:
            return False
        self.loading.add(path)
        self.notice.text = 'Loading notes…'
        try:
            path = self.contained(path)
            rows = await asyncio.to_thread(self.library.folders, path, cancelled=lambda: not self.valid())
            if not self.valid():
                return False
            self.folders[path] = sorted((row for row in rows
                if not row['name'].startswith('.') and self.app.folder_path_visible(row['path'], directory=row['directory'])
                and (row['directory'] or PurePosixPath(row['name']).suffix.lower() in MARKDOWN)),
                key=lambda row: (not row['directory'], row['name'].casefold()))
            self.notice.text = ''
            self.render_tree()
            return True
        except OperationCancelled:
            return False
        except (OSError, ValueError) as error:
            if self.valid():
                self.notice.text = fill('Could not browse notes: ' + str(error)[:120], width=28)
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
                if not self.app.folder_path_visible(entry['path'], directory=entry['directory']):
                    continue
                flattened.append((entry, depth))
                if entry['directory'] and entry['path'] in self.expanded:
                    add(entry['path'], depth + 1)
        add(self.root)
        query = (self.search.value or '').casefold() if self.search is not None else ''
        flattened = [(entry, depth) for entry, depth in flattened
            if entry['directory'] or not query or query in entry['path'].casefold()]
        for entry, depth in flattened[:self.shown]:
            path, directory = entry['path'], entry['directory']
            async def choose(widget=None, path=path, directory=directory, **kwargs):
                if directory:
                    await self.toggle_folder(path)
                else:
                    await self.open_note(path)
            label = (('▾ ' if path in self.expanded else '▸ ') if directory else '') + entry['name']
            button = list_button(toga.Button(label, on_press=choose, style=Pack(height=48, flex=1)))
            from .browser_ui import middle_filename
            middle_filename(button)
            button.vault_path = path
            row = toga.Box(children=[toga.Box(style=Pack(width=depth * 20)), entry_icon(directory), button],
                style=Pack(direction=ROW, align_items=CENTER))
            highlight_entry(row, path == self.selected_path)
            highlight_entry(button, path == self.selected_path)
            self.rows.add(row)
        if len(flattened) > self.shown:
            def more(widget=None, **kwargs):
                self.shown += 500
                self.render_tree()
            self.rows.add(toga.Button('Show more notes', on_press=more, style=Pack(height=48)))
        elif not flattened:
            self.rows.add(toga.Label('No Markdown notes in this folder.'))

    async def open_note(self, path, *, remember=True, fragment=''):
        if not self.valid():
            return False
        self.speech.close()
        self.epoch += 1
        epoch = self.epoch
        try:
            path = self.contained(path)
            if PurePosixPath(path).suffix.lower() not in MARKDOWN:
                raise ValueError('Choose a Markdown note.')
            def read():
                data = self.library.read(path, cancelled=lambda: not self.valid())
                html = markdown_preview(data.decode('utf-8-sig'), int(self.app.preferences.values['font_size']), local_links=True)
                if self.provider.private and len(html.encode('utf-8')) > MAX_NOTE:
                    raise ValueError('Private preview exceeds the 2 MiB memory-only limit.')
                return html
            html = await asyncio.to_thread(read)
            if not self.valid() or epoch != self.epoch:
                return False
            if remember and path != self.path:
                del self.history[self.history_index + 1:]
                self.history.append(path)
                self.history_index = len(self.history) - 1
            self.path = self.selected_path = path
            self.render_tree()
            self.title.text = fill(PurePosixPath(path).name, width=28)
            self.base = 'https://markdown.invalid/vault/' + uuid4().hex + '/'
            html = re.sub(r'href="([^"]*)"', lambda match: 'href="' + self.base + '?target='
                          + quote(unescape(match[1]), safe='') + '"', html)
            self.pending_fragment = fragment
            self.web.set_content(self.base, html)
            self.edit.enabled = True
            self.speech.button.enabled = True
            self.notice.text = ''
            self.back_button.enabled = self.history_index > 0
            self.forward_button.enabled = self.history_index < len(self.history) - 1
            self.up_button.enabled = True
            self.sidebar.show_detail()
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
        elif url.split('?', 1)[0] == self.base:
            target = parse_qs(parsed.query).get('target', [''])[0]
        else:
            return False
        link = urlsplit(target)
        if not link.path and link.fragment:
            self.scroll_fragment(link.fragment)
            return False
        if link.scheme or link.netloc or link.query or not link.path or link.path.startswith(('/', '\\')):
            return False
        try:
            path = self.contained(posixpath.normpath(posixpath.join(posixpath.dirname(self.path), unquote(link.path))))
        except ValueError:
            return False
        self.app.loop.create_task(self.open_note(path, fragment=link.fragment))
        return False

    def scroll_fragment(self, fragment):
        import json
        self.web.evaluate_javascript('(function(){const h=document.getElementById('
            + json.dumps(unquote(fragment)) + ');if(h)h.scrollIntoView();})()')

    def page_loaded(self, widget=None, **kwargs):
        if self.pending_fragment:
            fragment, self.pending_fragment = self.pending_fragment, ''
            self.scroll_fragment(fragment)

    async def navigate_history(self, offset):
        index = self.history_index + offset
        if 0 <= index < len(self.history) and await self.open_note(self.history[index], remember=False):
            self.history_index = index
            self.back_button.enabled = index > 0
            self.forward_button.enabled = index < len(self.history) - 1

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
            self.app.workspace.activate(self.session.id)
            return self.app.show_view(self.view, destination='documents',
                route='notes-library:' + self.session.id, title=self.session.title)

    async def open_editor(self, widget=None, **kwargs):
        if not self.valid() or self.path is None:
            return False
        from features.text_editor.resources import LocalTextCopies
        from features.rclone.localcrypt.mobile.resources import encrypted_document
        if self.library.remote:
            from features.rclone.mobile.remote_readers import RemoteReaders
            return await self.app.open_crypt(copies=RemoteReaders(self.client, self.provider.remote),
                key=self.path, destination='documents')
        source = encrypted_document(self.provider, self.path)
        copies, key = source if source is not None else (LocalTextCopies(self.provider), self.path)
        return await self.app.open_crypt(copies=copies, key=key, destination=self.destination)

    def dispose(self):
        self.speech.close()
        self.speech.button.enabled = False
        self.cancelled.set()
        if self.search is not None:
            self.search.value = ''
        self.epoch += 1
        self.folders.clear()
        self.expanded.clear()
        self.rows.clear()
        self.path = self.selected_path = None
        self.root = ''
        self.title.text = 'Notes Library closed'
        self.edit.enabled = False
        self.notice.text = 'Reopen Notes Library from the location actions.'
        self.history.clear()
        if self.session is not None and self.session.id in self.app.workspace.sessions:
            self.app.workspace.close(self.session.id, guard=lambda session: True)
        self.session = None
        from features.text_editor.mobile.markdown_editor import retire_webview
        if hasattr(self.web, 'clear_private_content'):
            self.web.clear_private_content()
        else:
            retire_webview(self.web)
