"""Review and clear redundant imported documents, preserving edits and sources."""
import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.filesystem import format_size
from services.workflow_host import HostService


def stored_size(size):
    return format_size(size, binary_units=True)


class SavedFilesController:
    active_host = HostService('active_host')
    main_window = HostService('main_window')
    private_root = HostService('private_root')
    reader_manager = HostService('reader_manager')
    recent_documents = HostService('recent_documents')
    refresh_library = HostService('refresh_library')
    save_workspace = HostService('save_workspace')
    scene_manager = HostService('scene_manager')
    show_settings = HostService('show_settings')
    show_view = HostService('show_view')
    workspace = HostService('workspace')
    resource_imports = HostService('resource_imports')

    def __init__(self, app):
        self.app = app
        self.saved_files_message = ''

    def show_saved_files(self, widget=None, **kwargs):
        from .settings.titles import page_title
        from .cached_documents import inventory
        items, failures = inventory(self.app)
        total = sum(item['size'] for item in items)
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Button('Back to Settings', on_press=self.show_settings, style=Pack(height=48)))
        box.add(page_title('Clear cached documents'))
        self.saved_files_summary = toga.Label(f'{len(items)} saved file(s) · {stored_size(total)}',
                                             style=Pack(font_size=18, margin_bottom=8))
        box.add(self.saved_files_summary)
        box.add(toga.Label('Older imported books, comics and text documents.\n'
                          'Only copies identical to an available original are cleared.\n'
                          'Editing drafts, changed copies and originals are kept.\n'
                          'Clearing a book/comic copy also removes its progress and bookmarks.',
                          style=Pack(font_size=12, margin_bottom=12)))
        box.add(toga.Button('Refresh', on_press=self.show_saved_files, style=Pack(height=48)))
        box.add(toga.Button('Clear redundant copies…', on_press=self.delete_all_saved_files,
                            enabled=bool(items), style=Pack(height=48)))
        for item in items:
            row = toga.Box(style=Pack(direction=COLUMN, margin_top=12))
            row.add(toga.Label(item['name']))
            row.add(toga.Label(f"{item['kind']} · {stored_size(item['size'])}", style=Pack(font_size=12)))
            async def delete(widget=None, key=item['id'], provider=item['provider'], **kw):
                await self._delete_saved_files(key, provider=provider)
            row.add(toga.Button('Clear cached copy…', on_press=delete, style=Pack(height=48)))
            box.add(row)
        if not items:
            box.add(toga.Label('No saved imports.'))
        if failures:
            box.add(toga.Label(f'{len(failures)} item(s) could not be measured; they were preserved.'))
        self.saved_files_status = toga.Label(getattr(self, 'saved_files_message', ''), style=Pack(margin_top=12))
        box.add(self.saved_files_status)
        self.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)),
                       destination='settings', route='saved-files', title='Clear cached documents')

    async def delete_saved_file(self, key):
        await self._delete_saved_files(key)

    async def delete_all_saved_files(self, widget=None, **kwargs):
        await self._delete_saved_files()

    async def _delete_saved_files(self, key=None, *, provider='library'):
        if getattr(self, '_clearing', False):
            return
        self._clearing = True
        deleted = 0
        preserved = 0
        try:
            if len(self.scene_manager.owners.hosts) > 1:
                raise ValueError('Close other app windows before deleting a saved copy.')
            manager = self.reader_manager()
            # Scans and imports share the catalogue, not just the open reader.
            if any(owner.book_busy for owner in (manager.catalog, *manager.controllers.values())):
                raise ValueError('Wait for the reader or import operation to finish.')
            from .cached_documents import inventory, original_text_paths, duplicate_source, live_edits, import_index
            items, _ = inventory(self.app)
            targets = [item for item in items if key is None or (item['id'], item['provider']) == (key, provider)]
            if not targets:
                self.show_saved_files()
                return
            if key is None:
                title = 'Clear cached documents?'
                description = (f"Check {len(targets)} imported document copies "
                               f"({stored_size(sum(item['size'] for item in targets))}) from this device, ")
            else:
                title = 'Clear cached copy?'
                description = f"Check {targets[0]['name']} ({stored_size(targets[0]['size'])}), "
            if not await self.main_window.dialog(toga.ConfirmDialog(title, description +
                    'and clear copies identical to their originals, including imported reading progress and bookmarks? '
                    'Original files, unsaved drafts, changed copies and copies with missing originals are kept.')):
                return
            if not self.active_host:
                return
            if len(self.scene_manager.owners.hosts) > 1 or any(
                    owner.book_busy for owner in (manager.catalog, *manager.controllers.values())):
                raise ValueError('The library is busy. Try again after closing other windows or finishing the operation.')
            self.saved_files_message = 'Checking originals and preserving editing drafts…'
            self.show_saved_files()
            imports = import_index(self.app)
            text_paths = await asyncio.to_thread(original_text_paths, self.app)
            for item in targets:
                target, source_provider = item['id'], item['provider']
                if (live_edits(self.app, item)
                        or not await asyncio.to_thread(duplicate_source, self.app, item, text_paths)):
                    preserved += 1
                    continue
                if not self.active_host or len(self.scene_manager.owners.hosts) > 1:
                    raise ValueError('Document state changed; remaining copies were preserved.')
                if live_edits(self.app, item):
                    preserved += 1
                    continue
                for session in list(self.workspace.sessions.values()):
                    if session.identity == (source_provider, target) and not self.app.close_session(session.id):
                        raise ValueError('Wait for the document operation to finish before clearing.')
                # Check again after closing/checkpointing; never erase a draft
                # that changed while the confirmation or file comparison ran.
                if not await asyncio.to_thread(duplicate_source, self.app, item, text_paths):
                    preserved += 1
                    continue
                if (not self.active_host or len(self.scene_manager.owners.hosts) > 1
                        or live_edits(self.app, item)):
                    preserved += 1
                    continue
                if source_provider == 'library':
                    manager.catalog.library_store.delete_local_copy(target)
                else:
                    self.app.store.delete(self.app.store.open(target))
                deleted += 1
                self.recent_documents.forget(source_provider, target)
                imports.forget(source_provider, target)
            self.refresh_library()
            self.app.refresh_documents()
            self.save_workspace()
            self.saved_files_message = (f'{deleted} local copies deleted.' if key is None else 'Local copy deleted.')
            if preserved:
                self.saved_files_message = f'{deleted} copies cleared; {preserved} kept because they have edits, differ from the original, or lack a verified original.'
            self.show_saved_files()
        except (OSError, ValueError) as error:
            if deleted:
                self.refresh_library()
                self.save_workspace()
            self.saved_files_message = (f'{deleted} local copies deleted. ' if deleted else '') + 'Could not delete local copy: ' + str(error)
            self.show_saved_files()
        finally:
            self._clearing = False


# Compatibility import; instantiate the controller with its host.
SavedFilesUI = SavedFilesController
