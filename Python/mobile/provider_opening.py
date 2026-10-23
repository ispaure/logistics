"""Open and publish one provider document; session selection stays with the manager."""
import asyncio
import threading
from pathlib import Path
import toga
from commonUtils.runtime.operations import check_cancelled
from .provider_ui import private_label
from .provider_view import ProviderDocumentView


class ProviderDocumentOpening:
    def __init__(self, owner):
        self.owner = owner
        self.view = ProviderDocumentView(owner)

    async def open(self, widget=None, *, copies=None, key=None, prepared=None, independent=False, edit=False, **kwargs):
        owner = self.owner
        copies = copies or owner.crypt_copies
        key = key if key is not None else owner.crypt_labels.get(owner.crypt_selector.value)
        if (owner.cloud_busy and not (independent and owner.transfer_busy and getattr(copies, 'offline', False))) or key is None:
            return
        password = owner.crypt_password.value
        owner.crypt_password.value = ''
        if owner._crypt_cancel is not None:
            return
        if prepared is None and owner.private_dirty():
            owner.crypt_title.text = private_label('Unsaved changes: save, or discard and close.')
            owner.resume_crypt()
            return
        if not independent:
            owner.set_cloud_busy(True)
        owner._crypt_cancel = threading.Event()
        reader = None
        view = None
        try:
            if prepared is None:
                from .loading_progress import opening_options
                reader = await asyncio.to_thread(copies.open, key,
                    password=password, cancelled=owner._crypt_cancel.is_set, **opening_options(copies))
                owner._provider_comic_mode = owner.private_comic_mode()
                owner._provider_comic_sharing = owner.format_services.comic_sharing()
                owner._provider_comic_seam = owner.private_comic_seam()
                owner._provider_viewport = (max(1, owner.main_window.size.width), max(1, owner.main_window.size.height))
                kind, content = await asyncio.to_thread(owner.provider_page_content, reader, 0)
            else:
                reader, kind, content = prepared
            initial_preview, initial_preview_error = await self._prepare_initial_preview(
                owner, reader, copies, content, edit=edit)
            check_cancelled(owner._crypt_cancel.is_set)
            view = self.view.build(reader, copies, kind, content)
            if password:
                from features.rclone.mobile.session_privacy import ResumePassword
                view.privacy_gate = ResumePassword(password)
            elif getattr(owner, 'privacy_gate', None) is not None:
                view.privacy_gate = owner.privacy_gate
            handoff = (prepared is not None and getattr(owner, 'save_as_source_document', None) is owner.current
                       and getattr(owner.current, 'private', False))
            if not owner.show_view(view.crypt_view, checkpoint=not handoff, title=Path(reader.name).name):
                return False
            owner._crypt_cancel = None
            return await self._publish_view(owner, view, reader, edit=edit,
                                            initial_preview=initial_preview,
                                            initial_preview_error=initial_preview_error)
        except Exception as error:
            if owner._crypt_cancel is not None and owner._crypt_cancel.is_set():
                owner.cloud_status.value = 'Remote opening cancelled.' if getattr(copies, 'remote_storage', False) else 'Private reading cancelled.'
                return False
            owner.cloud_status.value = 'Private reading failed: ' + str(error)[:300]
            if getattr(copies, 'remote_storage', False):
                from commonUtils.archives.zip_access import ArchivePasswordError
                if isinstance(error, ArchivePasswordError):
                    row = next((row for row in owner.app.cloud_rows.values() if row['path'] == key),
                               dict(path=key, directory=False, size=0))
                    owner.app.show_remote_item_actions(row, password_required=True)
                    return False
                from features.rclone.remote_policy import LOCAL_COPY_MESSAGE
                await owner.main_window.dialog(toga.InfoDialog('Remote preview unavailable',
                    str(error)[:200] + '\n\n' + LOCAL_COPY_MESSAGE))
            else:
                await owner.main_window.dialog(toga.InfoDialog('Could not open document', str(error)[:300]))
        finally:
            if view is not None:
                view.discard()
            if (prepared is None and getattr(copies, 'remote_storage', False) and reader is not None
                    and getattr(owner, 'crypt_reader', None) is not reader):
                reader.source.close()
            password = None
            owner._crypt_cancel = None
            if not independent:
                owner.set_cloud_busy(False)

    async def _prepare_initial_preview(self, owner, reader, copies, content, *, edit):
        initial_preview = None
        initial_preview_error = None
        if (not edit and reader.editable and not getattr(reader, 'read_only', False)
                and reader.kind in {'.md', '.markdown'}):
            from .preview import markdown_preview, reader_image_source
            try:
                initial_preview = await asyncio.to_thread(markdown_preview, content,
                    int(owner.preferences.values['markdown_font_size']), image_source=reader_image_source(copies, reader))
            except ValueError as error:
                # Keep the established source fallback and error feedback.
                initial_preview_error = str(error)
        return initial_preview, initial_preview_error

    async def _publish_view(self, owner, view, reader, *, edit, initial_preview, initial_preview_error):
        owner.clear_private_reader(discard=True)
        view.adopt(owner)
        if reader.editable and not getattr(reader, 'read_only', False) and reader.kind in {'.md', '.markdown'}:
            if edit:
                owner.show_private_markdown_editor()
            elif initial_preview_error is not None:
                owner.crypt_title.text = private_label(initial_preview_error)
            else:
                owner.toggle_private_preview(initial=True, rendered=initial_preview)
        privacy = getattr(getattr(owner, 'app', owner), 'screen_privacy', None)
        if privacy is not None:
            privacy.refresh()
        owner.watch_provider_layout()
        owner.watch_provider_epub_width()
        if view.crypt_reader.kind in {'.cbz', '.zip'}:
            await owner.refresh_provider_comic_neighbors()
        return True
