"""Forms for creating and renaming entries in the mobile Notes Library."""
import asyncio
import posixpath
from pathlib import PurePosixPath
from textwrap import fill

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from commonUtils.runtime.operations import OperationCancelled
from services.documents.names import document_name
from ..library_files import renamed_path
from ..notes import MARKDOWN


class LibraryFileForms:
    """Present file commands through the browser's existing Notes routes."""

    def new_note(self, widget=None, **kwargs):
        async def choose():
            if not self.valid() or not self.library.supports('create'):
                return False
            extension = await self.host.choose_type() if self.host.choose_type else 'md'
            if self.valid() and extension in ('md', 'rmdoc'):
                self.name_document(extension)
        return self.host.loop.create_task(choose())

    def name_document(self, extension, filename=''):
        suffixes = MARKDOWN if extension == 'md' else {'.' + extension}
        suffix = PurePosixPath(filename).suffix
        suffix = suffix if suffix.lower() in suffixes else '.' + extension
        name = self.host.presentation.filename_input(
            value=filename, extension=suffix, placeholder='Untitled', style=Pack(height=48))
        status = toga.Label('')

        async def next_step(widget=None, **kwargs):
            try:
                filename = document_name(name.value or 'Untitled.' + extension)
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
                await self._create_document(name, extension, parent)
            except OperationCancelled:
                return
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

    def manage_entry(self, *, folder=False, move=False, return_side=None):
        if not self.valid() or not self.library.supports('rename' if move else 'create'):
            return False
        source = self.selected_path if move else None
        if move and source is None:
            return False
        title = 'Rename' if move else 'New folder'
        initial = PurePosixPath(source).name if move else ''
        directory = not move or self.library.provider.entry(source)['directory']
        name = self.host.presentation.filename_input(value=initial, directory=directory, style=Pack(height=48))
        status = toga.Label('Links are not rewritten.' if move else '')
        submit_button = toga.Button('Rename' if move else 'Create folder', style=Pack(height=48))
        cancel = toga.Button('Cancel', on_press=lambda widget: self.return_from_file_action(view=action_view),
                             style=Pack(height=48))
        parent = self.selected_parent()

        async def submit(widget=None, **kwargs):
            if self.file_command_busy or not self.file_action_current(action_view):
                return
            submit_button.enabled = cancel.enabled = False
            try:
                if move:
                    target = renamed_path(source, name.value)
                    if not await self.move_entry_to(source, target):
                        if self.file_action_current(action_view):
                            status.text = self.notice.text
                        return
                elif not await self._create_folder(name.value, parent):
                    return
                self.return_from_file_action(view=action_view)
                if not move and self.valid():
                    self.refresh_reader_actions()
            except OperationCancelled:
                return
            except (OSError, ValueError) as error:
                if self.file_action_current(action_view):
                    status.text = str(error) if move else fill(str(error)[:180], width=28)
            finally:
                submit_button.enabled = cancel.enabled = True
        submit_button.on_press = submit
        form = toga.Box(children=[toga.Label(title, style=Pack(font_size=20)),
            toga.Label('Name' if move else 'Folder name'),
            name, status, submit_button, cancel], style=Pack(direction=COLUMN, margin=16))
        action_view = toga.ScrollContainer(content=form, horizontal=False, style=Pack(flex=1))
        return self.show_file_action(action_view,
                                     route='notes-manage', title=title, return_side=return_side)
