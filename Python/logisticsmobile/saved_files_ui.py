"""Inventory and deletion of device-retained library imports."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.filesystem import format_size


def stored_size(size):
    return format_size(size, binary_units=True)


class SavedFilesUI:
    def show_saved_files(self, widget=None, **kwargs):
        from .hub_ui import heading
        store = self.reader_manager().catalog.library_store
        items, failures = store.stored_files()
        total = sum(item['size'] for item in items)
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Button('Back to Settings', on_press=self.show_settings, style=Pack(height=48)))
        box.add(heading('Saved books & comics'))
        self.saved_files_summary = toga.Label(f'{len(items)} saved file(s) · {stored_size(total)}',
                                             style=Pack(font_size=18, margin_bottom=8))
        box.add(self.saved_files_summary)
        box.add(toga.Label('Imports kept on this device, including closed documents.\n'
                          'Closing a document keeps its saved copy.\n'
                          'Sizes include archives and reading records;\n'
                          'Local / LocalCrypt folders and RAM previews are separate.',
                          style=Pack(font_size=12, margin_bottom=12)))
        box.add(toga.Button('Refresh', on_press=self.show_saved_files, style=Pack(height=48)))
        for item in items:
            row = toga.Box(style=Pack(direction=COLUMN, margin_top=12))
            row.add(toga.Label(item['name']))
            row.add(toga.Label(f"{item['kind']} · {stored_size(item['size'])}", style=Pack(font_size=12)))
            row.add(toga.Label('Saved import · original source was not recorded', style=Pack(font_size=12)))
            async def delete(widget=None, key=item['id'], **kw):
                await self.delete_saved_file(key)
            row.add(toga.Button('Delete local copy…', on_press=delete, style=Pack(height=48)))
            box.add(row)
        if not items:
            box.add(toga.Label('No saved imports.'))
        if failures:
            box.add(toga.Label(f'{len(failures)} item(s) could not be measured; they were preserved.'))
        self.saved_files_status = toga.Label(getattr(self, 'saved_files_message', ''), style=Pack(margin_top=12))
        box.add(self.saved_files_status)
        self.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)),
                       destination='settings', route='saved-files', title='Saved books & comics')

    async def delete_saved_file(self, key):
        try:
            if len(self.scene_manager.owners.hosts) > 1:
                raise ValueError('Close other app windows before deleting a saved copy.')
            manager = self.reader_manager()
            # Scans and imports share the catalogue, not just the open reader.
            if any(owner.book_busy for owner in (manager.catalog, *manager.controllers.values())):
                raise ValueError('Wait for the reader or import operation to finish.')
            items, _ = manager.catalog.library_store.stored_files()
            item = next((item for item in items if item['id'] == key), None)
            if item is None:
                self.show_saved_files()
                return
            if not await self.main_window.dialog(toga.ConfirmDialog('Delete local copy?',
                    f"Delete {item['name']} ({stored_size(item['size'])}) from this device, "
                    'including its reading progress and bookmarks? The original source or cloud file is unchanged.')):
                return
            if not self.active_host:
                return
            if len(self.scene_manager.owners.hosts) > 1 or any(
                    owner.book_busy for owner in (manager.catalog, *manager.controllers.values())):
                raise ValueError('The library is busy. Try again after closing other windows or finishing the operation.')
            for session in list(self.workspace.sessions.values()):
                if session.identity == ('library', key) and not manager.close(session.id):
                    raise ValueError('Wait for the reader operation to finish before deleting.')
            self.recent_documents.forget('library', key)
            from .resource_imports import ResourceImports
            imports = getattr(self, 'resource_imports', None)
            if imports is None:
                imports = ResourceImports(self.private_root)
            imports.forget('library', key)
            manager.catalog.library_store.delete_local_copy(key)
            self.refresh_library()
            self.save_workspace()
            self.saved_files_message = 'Local copy deleted.'
            self.show_saved_files()
        except (OSError, ValueError) as error:
            self.saved_files_message = 'Could not delete local copy: ' + str(error)
            self.show_saved_files()
