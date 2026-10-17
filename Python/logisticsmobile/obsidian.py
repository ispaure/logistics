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
from toga.style.pack import COLUMN, ROW
from commonUtils.runtime.local_files import LocalFiles
from commonUtils.ui.native.adaptive import AdaptiveSidebar, allocated_width
from commonUtils.ui.native.presentation import list_button
from .control_icons import icon_button
from .preview import markdown_preview

MARKDOWN = {'.md', '.markdown'}
MAX_NOTE = 2 * 1024 * 1024


def vault_root(provider, directory, rows):
    """Only an actual local directory marker opts the current folder in."""
    provider = getattr(provider, 'provider', provider)
    if not isinstance(provider, LocalFiles):
        return None
    directory = provider.relative(directory)
    marker = posixpath.join(directory, '.obsidian')
    return directory if any(row['path'] == marker and row['directory'] for row in rows) else None


async def open_vault(app, provider, root, destination):
    if not app.checkpoint():
        return None
    previous = getattr(app, 'vault_browser', None)
    if previous is not None:
        previous.dispose()
    owner = VaultBrowser(app, provider, root, destination)
    app.vault_browser = owner
    if app.show_view(owner.view, destination=destination, route='obsidian-vault', title='Obsidian vault') is False:
        owner.dispose()
        return None
    await owner.load_folder(owner.root)
    return owner


class VaultBrowser:
    def __init__(self, app, provider, root, destination):
        self.app, self.provider, self.destination = app, provider, destination
        self.root = provider.relative(root)
        self.client = getattr(app, 'cloud_client', None)
        self.generation = getattr(self.client, 'generation', None)
        self.cancelled = Event()
        self.folders, self.expanded, self.loading = {}, {self.root}, set()
        self.path = None
        self.epoch = 0
        self.shown = 500
        self.base = 'https://markdown.invalid/vault/' + uuid4().hex + '/'
        self.rows = toga.Box(style=Pack(direction=COLUMN))
        self.notice = toga.Label('', style=Pack(font_size=12))
        self.tree = toga.Box(children=[toga.Label('Markdown notes', style=Pack(font_size=18)),
            toga.ScrollContainer(content=self.rows, horizontal=False, style=Pack(flex=1))],
            style=Pack(direction=COLUMN, flex=1))
        self.title = toga.Label('Choose a Markdown note', style=Pack(font_size=18, flex=1))
        self.edit = toga.Button('Open in editor', on_press=self.open_editor, enabled=False, style=Pack(height=48))
        self.web = toga.WebView(on_navigation_starting=self.follow_link, style=Pack(flex=1))
        self.article = toga.Box(children=[self.title, self.edit, self.web], style=Pack(direction=COLUMN, flex=1))
        from .markdown_speech import MarkdownSpeech
        self.speech = MarkdownSpeech(app, self.web, self.article)
        self.article.insert(2, self.speech.button)
        self.speech.button.enabled = False
        self.sidebar = AdaptiveSidebar(self.tree, self.article, label='Vault folders and Markdown notes')
        self.menu = icon_button('obsidian', 'Browse Obsidian vault notes', on_press=self.sidebar.toggle)
        self.view = toga.Box(children=[toga.Box(children=[self.menu, self.notice], style=Pack(direction=ROW)),
            self.sidebar.view], style=Pack(direction=COLUMN, margin=12, flex=1))
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
        path = self.provider.relative(path)
        if self.root and path != self.root and not path.startswith(self.root + '/'):
            raise ValueError('That note is outside this vault.')
        relative = PurePosixPath(path).relative_to(self.root or '.')
        if any(part.startswith('.') for part in relative.parts):
            raise ValueError('Vault configuration is not a note.')
        return path

    def reflow(self, width):
        available = max(0, allocated_width(self.view, width) - 24)
        self.sidebar.reflow(available)
        self.rows.style.width = self.sidebar.policy.sidebar_width if self.sidebar.expanded else available
        self.menu.enabled = not self.sidebar.expanded

    async def load_folder(self, path):
        if not self.valid() or path in self.loading:
            return False
        self.loading.add(path)
        self.notice.text = 'Loading notes…'
        try:
            path = self.contained(path)
            rows = await asyncio.to_thread(self.provider.list, path, cancelled=lambda: not self.valid())
            if not self.valid():
                return False
            self.folders[path] = sorted((row for row in rows
                if not row['name'].startswith('.') and self.app.folder_path_visible(row['path'], directory=row['directory'])
                and (row['directory'] or PurePosixPath(row['name']).suffix.lower() in MARKDOWN)),
                key=lambda row: (not row['directory'], row['name'].casefold()))
            self.notice.text = ''
            self.render_tree()
            return True
        except (OSError, ValueError) as error:
            if self.valid():
                self.notice.text = fill('Could not browse notes: ' + str(error)[:120], width=28)
            return False
        finally:
            self.loading.discard(path)

    async def toggle_folder(self, path):
        if not self.valid():
            return
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
            self.rows.add(toga.Box(children=[toga.Box(style=Pack(width=depth * 20)), button], style=Pack(direction=ROW)))
        if len(flattened) > self.shown:
            def more(widget=None, **kwargs):
                self.shown += 500
                self.render_tree()
            self.rows.add(toga.Button('Show more notes', on_press=more, style=Pack(height=48)))
        elif not flattened:
            self.rows.add(toga.Label('No Markdown notes in this folder.'))

    async def open_note(self, path):
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
                before = self.provider.entry(path)
                # CryptFiles reports ciphertext bytes, including block tags.
                if before['directory'] or before['size'] > MAX_NOTE + 4096:
                    raise ValueError('Note exceeds the 2 MiB preview limit. Open it in the file browser.')
                with self.provider.open(path) as stream:
                    data = stream.read(MAX_NOTE + 1)
                if len(data) > MAX_NOTE or self.provider.entry(path) != before:
                    raise ValueError('Note changed or is too large. Reopen it in the file browser.')
                return markdown_preview(data.decode('utf-8-sig'), int(self.app.preferences.values['font_size']), local_links=True)
            html = await asyncio.to_thread(read)
            if not self.valid() or epoch != self.epoch:
                return False
            self.path = path
            self.title.text = fill(PurePosixPath(path).name, width=28)
            self.base = 'https://markdown.invalid/vault/' + uuid4().hex + '/'
            html = re.sub(r'href="([^"]*)"', lambda match: 'href="' + self.base + '?target='
                          + quote(unescape(match[1]), safe='') + '"', html)
            self.web.set_content(self.base, html)
            self.edit.enabled = True
            self.speech.button.enabled = True
            self.notice.text = ''
            self.sidebar.show_detail()
            return True
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
        if link.scheme or link.netloc or link.query or not link.path or link.path.startswith(('/', '\\')):
            return False
        try:
            path = self.contained(posixpath.normpath(posixpath.join(posixpath.dirname(self.path), unquote(link.path))))
        except ValueError:
            return False
        self.app.loop.create_task(self.open_note(path))
        return False

    async def open_editor(self, widget=None, **kwargs):
        if not self.valid() or self.path is None:
            return False
        from features.text_editor.resources import LocalTextCopies
        from features.rclone.localcrypt.mobile.resources import encrypted_document
        source = encrypted_document(self.provider, self.path)
        copies, key = source if source is not None else (LocalTextCopies(self.provider), self.path)
        return await self.app.open_crypt(copies=copies, key=key, destination=self.destination)

    def dispose(self):
        self.speech.close()
        self.speech.button.enabled = False
        self.cancelled.set()
        self.epoch += 1
        self.folders.clear()
        self.expanded.clear()
        self.rows.clear()
        self.path = None
        self.root = ''
        self.title.text = 'Vault closed'
        self.edit.enabled = False
        self.notice.text = 'Reopen the vault from its file browser.'
        from features.text_editor.mobile.markdown_editor import retire_webview
        retire_webview(self.web)
