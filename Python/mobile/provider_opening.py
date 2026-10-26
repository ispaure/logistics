"""Open and publish one provider document; session selection stays with the manager."""
import asyncio
import threading
from pathlib import Path
from commonUtils.runtime.operations import check_cancelled
from services.documents.mobile_reading import reading_capabilities, close_document_reader
from .provider_ui import private_label
from .provider_view import ProviderDocumentView


class ProviderDocumentOpening:
    def __init__(self, owner, session):
        self.owner, self.session = owner, session
        self.view = ProviderDocumentView(owner)

    async def open(self, *, copies, key, password='', prepared=None, edit=False):
        owner = self.owner
        session = self.session
        capabilities = reading_capabilities(copies)
        if session.busy or key is None:
            return
        if session.cancel is not None:
            return
        if prepared is None and owner.private_dirty():
            owner.crypt_title.text = private_label('Unsaved changes: save, or discard and close.')
            owner.resume_crypt()
            return
        cancelled = session.cancel = threading.Event()
        session.set_busy(True)
        reader = None
        view = None
        try:
            if prepared is None:
                from .loading_progress import opening_options
                reader = await asyncio.to_thread(copies.open, key,
                    password=password, cancelled=cancelled.is_set, **opening_options(copies))
                owner._provider_comic_mode = owner.private_comic_mode()
                owner._provider_comic_sharing = owner.format_services.comic_sharing()
                owner._provider_comic_seam = owner.private_comic_seam()
                owner._provider_viewport = (max(1, owner.main_window.size.width), max(1, owner.main_window.size.height))
                kind, content = await asyncio.to_thread(owner.provider_page_content, reader, 0)
            else:
                reader, kind, content = prepared
            if not owner.app.require_document_feature(reader.name):
                return False
            from services.documents.storage import document_writable
            reader.read_only = not capabilities.writable or not document_writable(copies, reader)
            initial_preview, initial_preview_error = await self._prepare_initial_preview(
                owner, reader, copies, content, edit=edit)
            check_cancelled(cancelled.is_set)
            view = self.view.build(reader, copies, kind, content)
            if getattr(owner, 'privacy_gate', None) is not None:
                view.privacy_gate = owner.privacy_gate
            handoff = (prepared is not None and getattr(owner, 'save_as_source_document', None) is owner.current
                       and getattr(owner.current, 'private', False))
            if not owner.show_view(view.crypt_view, checkpoint=not handoff, title=Path(reader.name).name):
                return False
            session.cancel = None
            return await self._publish_view(owner, view, reader, edit=edit,
                                            initial_preview=initial_preview,
                                            initial_preview_error=initial_preview_error)
        except Exception as error:
            if cancelled.is_set():
                owner.document_open_cancelled(remote=capabilities.remote)
                return False
            await owner.document_open_failed(error, remote=capabilities.remote, key=key)
        finally:
            try:
                if view is not None:
                    view.discard()
                if prepared is None and session.reader is not reader:
                    close_document_reader(reader)
            finally:
                password = None
                session.cancel = None
                session.set_busy(False)

    async def _prepare_initial_preview(self, owner, reader, copies, content, *, edit):
        initial_preview = None
        initial_preview_error = None
        if ((not edit or getattr(reader, 'read_only', False)) and reader.editable
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
        self.session.reader = reader
        if reader.editable and reader.kind in {'.md', '.markdown'}:
            if edit and not getattr(reader, 'read_only', False):
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
