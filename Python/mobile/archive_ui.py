"""Mobile archive browser and File Browser resource actions."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from dataclasses import dataclass
from pathlib import PurePosixPath
from threading import Event
from types import SimpleNamespace

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from commonUtils import archives
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.resources.paths import resource_name
from .archive_operations import ArchiveItem, create_archive, extract_archive, ordinary
from .file_operations import retiring_work


@dataclass(frozen=True)
class ArchivePickerAction:
    kind: str
    workspace: object
    item: ArchiveItem
    sources: tuple = ()
    selected: tuple | None = None
    password: str | None = None

    @property
    def title(self):
        return {'archive-create': 'Create archive', 'archive-extract': 'Extract archive',
                'archive-add': 'Add archive member'}[self.kind]

    @property
    def primary(self):
        return {'archive-create': 'Create here', 'archive-extract': 'Extract here',
                'archive-add': 'Add item'}[self.kind]

    def execute(self, provider, folder, name, format, work_root, cancelled):
        if self.kind == 'archive-create':
            return create_archive(self.sources, provider, folder, name, format, work_root, cancelled)
        if self.kind == 'archive-extract':
            return extract_archive(self.item, provider, folder, name, cancelled, selected=self.selected,
                                   password=self.password)
        source = ArchiveItem(provider, '/'.join(filter(None, (folder, resource_name(name)))))
        return self.item.edit(cancelled, sources=(source,), password=self.password)


def controller(app):
    owner = getattr(app, '_archives', None)
    if owner is None:
        owner = app._archives = ArchiveWorkspace(app)
    return owner


def archive_commands(app, provider, row):
    if not app.feature_enabled('archives') or not ordinary(provider) or not row:
        return []
    item = ArchiveItem.from_row(provider, row)
    commands = [('Create archive…', lambda: controller(app).create((item,)))]
    if not row['directory'] and archives.is_supported_archive(item.path):
        commands.insert(0, ('Manage archive…', lambda: controller(app).open(item)))
    return commands


async def reopen_archive(app, source):
    from .document_sources import local_document_path, ordinary_browser_location
    if source['type'] != 'local':
        raise ValueError('Choose an on-device archive.')
    path = local_document_path(app, source['path'])
    if not app.feature_enabled('archives'):
        return False
    from commonUtils.filesystem.local_access import check_local_path
    check_local_path(path)
    location = ordinary_browser_location(app, path) if path.is_file() else None
    if location is None:
        raise FileNotFoundError('This archive is no longer available at its saved location.')
    _, provider, row = location
    return await controller(app).open(ArchiveItem.from_row(provider, row))


class ArchiveWorkspace:
    def __init__(self, app):
        self.app = app
        self.item = None
        self.view = None
        self.cancel = None
        self.folder = ''
        self.password = ''
        self.members = ()
        self.selected = None
        self.page = 0
        self.message = ''

    def enabled(self):
        return self.app.active_host and self.app.feature_enabled('archives')

    async def create(self, sources):
        if self.enabled() and sources and not self.app.cloud_busy:
            action = ArchivePickerAction('archive-create', self, sources[0], sources)
            await self.app.editor_picker().show_destination('Archive', action)

    async def run(self, work, *, completed=lambda result: None):
        if not self.enabled() or self.cancel is not None or self.app.cloud_busy:
            return False
        cancel = self.cancel = Event()
        try:
            await retiring_work(work, cancel, completed=completed)
            return True
        except OperationCancelled:
            self.message = 'Archive operation cancelled.'
        except Exception as error:
            self.message = str(error)[:300]
        finally:
            self.cancel = None
        return False

    async def open(self, item):
        if not self.enabled() or self.cancel is not None or self.app.cloud_busy:
            return False
        generation = self.app.navigation_generation
        result = []
        if not await self.run(item.inspect, completed=result.append):
            if self.enabled() and generation == self.app.navigation_generation:
                await self.app.main_window.dialog(toga.InfoDialog('Could not open archive', self.message))
            return False
        if not self.enabled() or generation != self.app.navigation_generation:
            return False
        self.item, self.members = result[0]
        self.folder, self.password, self.message = '', '', ''
        self.page = 0
        self.dispose_view()
        if not self.present():
            self.item = None
            return False
        from .favourites import resource_reference
        try:
            source, _ = resource_reference(self.app, self.item.provider, self.item.path)
            self.app.recent_documents.remember_file(SimpleNamespace(kind='archive', title=self.name), source)
        except (OSError, ValueError) as error:
            self.status.text = 'Could not save recent archive: ' + str(error)
        return True

    def matches_reference(self, source):
        from .favourites import resource_reference
        try:
            return source == resource_reference(self.app, self.item.provider, self.item.path)[0]
        except (OSError, ValueError):
            return False

    @property
    def name(self):
        return PurePosixPath(self.item.path).name

    def present(self):
        if not self.enabled() or self.item is None:
            return False
        if self.cancel is not None:
            return False
        if self.view is not None:
            return self.visible() or self.app.show_view(self.view, route='archive-workspace', title=self.name)
        self.selected = None
        from .browser_ui import BrowserStatusLabel
        self.status = BrowserStatusLabel(self.message)
        self.location = BrowserStatusLabel('')
        from .control_icons import icon_button
        self.up = icon_button('up', 'Parent folder', on_press=self.parent)
        self.rows = toga.Box(style=Pack(direction=COLUMN))
        self.previous_page = toga.Button('Previous', on_press=lambda widget: self.change_page(-1),
                                         style=Pack(height=48, flex=1))
        self.next_page = toga.Button('Next', on_press=lambda widget: self.change_page(1),
                                     style=Pack(height=48, flex=1))
        self.pages = toga.Box(children=[self.previous_page, self.next_page], style=Pack(direction=ROW))
        self.member_status = BrowserStatusLabel('')
        self.member_status.style.flex = self.status.style.flex = 0
        commands = [('Extract all…', self.extract), ('Extract selected…', self.extract_selected)]
        if archives.is_zip_archive(self.item.path):
            commands.extend([('Add item…', self.add), ('Remove selected…', self.remove)])
        commands.append(('Close archive', self.close))
        from .file_items import native_menu, row_actions
        self.menu_button = icon_button('overflow', 'Archive actions')
        item = self.item
        def load_actions():
            row = dict(path=item.path, revision=item.revision, directory=False)
            return [*commands, *row_actions(self.app, item.provider, row,
                                           anchor=self.menu_button, opener=dict(kind='archive'), favourite=True)]
        native_menu(self.app, self.menu_button, load_actions)
        self.menu = self.menu_button.document_actions
        self.cancel_button = toga.Button('Cancel operation', on_press=self.request_cancel, style=Pack(height=48))
        from commonUtils.ui.native.password_input import PasswordInput
        # Archive passwords are kept only in this workspace and cleared on close.
        self.password_input = None
        controls = [self.status, self.cancel_button]
        if any(item.encrypted for item in self.members):
            self.password_input = PasswordInput(value=self.password, placeholder='Archive password', style=Pack(height=48))
            controls.append(self.password_input)
        self.view = toga.Box(children=[
            toga.Box(children=[self.up, self.location, self.menu_button], style=Pack(direction=ROW)),
            *controls, self.member_status,
            toga.ScrollContainer(content=self.rows, horizontal=False, style=Pack(flex=1)), self.pages,
        ], style=Pack(direction=COLUMN, flex=1, margin=12))
        self.render_members()
        self.cancel_button.style.display = 'none'
        return self.app.show_view(self.view, route='archive-workspace', title=self.name)

    def render_members(self):
        self.up.enabled = bool(self.folder)
        self.location.text = self.folder or 'Archive contents'
        self.location.style.flex = 1
        self.member_status.text = ''
        self.selected = None
        rows = {}
        prefix = self.folder + '/' if self.folder else ''
        for entry in self.members:
            name = entry.name.rstrip('/')
            if name == self.folder or not name.startswith(prefix):
                continue
            first, child, _ = name[len(prefix):].partition('/')
            rows[first] = bool(child) or entry.directory
        ordered = sorted(rows, key=lambda name: (not rows[name], name.casefold(), name))
        size = 100
        self.page = min(self.page, max(0, (len(ordered) - 1) // size))
        self.pages.style.display = 'pack' if len(ordered) > size else 'none'
        self.previous_page.enabled = self.page > 0
        self.next_page.enabled = (self.page + 1) * size < len(ordered)
        for child in list(self.rows.children):
            self.rows.remove(child)
        for name in ordered[self.page * size:(self.page + 1) * size]:
            path = prefix + name
            directory = rows[name]
            self.rows.add(toga.Box(children=[
                toga.Button(name, style=Pack(height=48, flex=1),
                            on_press=lambda widget, p=path, d=directory: self.enter(p) if d else self.select(p)),
                *([toga.Button('Select', style=Pack(height=48),
                               on_press=lambda widget, p=path: self.select(p))] if directory else []),
            ], style=Pack(direction=ROW)))
        if not ordered:
            self.rows.add(toga.Label('This folder is empty.'))

    def change_page(self, delta):
        self.page += delta
        self.render_members()

    def parent(self, widget=None, **kwargs):
        self.enter(self.folder.rpartition('/')[0])

    def enter(self, path):
        self.folder = path
        self.page = 0
        self.render_members()

    def select(self, path):
        self.selected = path
        self.member_status.text = 'Selected: ' + PurePosixPath(path).name

    def secret(self):
        self.password = self.password_input.value if self.password_input is not None else ''
        return self.password or None

    async def extract(self, widget=None, *, selected=None, **kwargs):
        if self.enabled() and self.item and self.cancel is None:
            suffix = next(s for s in sorted(archives.ARCHIVE_SUFFIXES, key=len, reverse=True)
                          if self.name.lower().endswith(s))
            action = ArchivePickerAction('archive-extract', self, self.item, selected=selected, password=self.secret())
            await self.app.editor_picker().show_destination((self.name[:-len(suffix)] or 'Archive') + ' contents', action)

    async def extract_selected(self, widget=None, **kwargs):
        if self.selected is None:
            self.status.text = 'Select a member or folder first.'
            return
        await self.extract(selected=(self.selected,))

    async def add(self, widget=None, **kwargs):
        if self.enabled() and self.item and self.cancel is None:
            await self.app.editor_picker().show_destination('',
                ArchivePickerAction('archive-add', self, self.item, password=self.secret()))

    async def remove(self, widget=None, **kwargs):
        item, selected = self.item, self.selected
        if not self.enabled() or self.cancel is not None or item is None:
            return
        if selected is None:
            self.status.text = 'Select a member or folder first.'
            return
        if not await self.app.main_window.dialog(toga.ConfirmDialog(
                'Remove archive member?', f'{selected}\n\nThis removes the member and any contents from the archive.')):
            return
        if item is not self.item or not self.visible():
            return
        secret = self.secret()
        self.status.text = 'Rewriting archive…'
        self.cancel_button.style.display = 'pack'
        try:
            await self.run(lambda cancelled: item.edit(cancelled, remove=(selected,), password=secret),
                           completed=self.rewritten)
        finally:
            if self.visible():
                self.cancel_button.style.display = 'none'
                self.status.text = self.message

    def rewritten(self, item):
        if not self.enabled():
            return
        self.item = item
        # The caller has published successfully. Reload metadata separately so
        # a subsequent read failure is never interpreted as a failed rewrite.
        self.message = 'Archive updated.'
        self.app.loop.create_task(self.reload(item))

    async def reload(self, item):
        try:
            _, members = await asyncio.to_thread(item.inspect, lambda: self.item is not item)
        except (OSError, ValueError, OperationCancelled):
            return
        if self.item is item:
            self.members = members
            if self.view is not None:
                self.render_members()

    def visible(self):
        from .routes import contains
        return self.view is not None and contains(self.app.body, self.view)

    def request_cancel(self, widget=None, **kwargs):
        if self.cancel is not None:
            self.cancel.set()

    async def favourite(self, widget=None, **kwargs):
        if self.enabled() and self.item:
            from .favourites import favourite_resource
            try:
                await favourite_resource(self.app, self.item.provider, self.item.path, kind='archive')
                self.status.text = 'Added to Favourites.'
            except (OSError, ValueError) as error:
                self.status.text = str(error)

    def close(self, widget=None, **kwargs):
        if self.cancel is not None:
            self.request_cancel()
            return
        if self.item is None:
            return
        visible = self.visible()
        self.item, self.members, self.password = None, (), ''
        self.dispose_view()
        if visible:
            self.app.editor_picker().return_from_archive_picker()
        self.app.refresh_hub('documents')

    def dispose_view(self):
        if getattr(self, 'password_input', None) is not None:
            self.password_input.value = ''
        if self.view is not None:
            self.menu.dispose()
            self.view = None

    def retire(self):
        self.request_cancel()
        self.item, self.members, self.password = None, (), ''
        self.dispose_view()
