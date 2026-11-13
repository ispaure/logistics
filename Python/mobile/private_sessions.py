"""Bounded, memory-only provider sessions; private bytes never enter recovery."""
from .composition.assembly import composed_workflow
from features.books.mobile.provider_controller import ProviderBookController
from features.comics.mobile.provider_controller import ProviderComicController

from hashlib import sha256
from pathlib import Path
from mobile.provider_ui import ProviderUI
from .reader_host import ReaderHost
from services.documents.mobile_reading import reading_capabilities

MAX_PRIVATE_SESSIONS = 4
from .reading.reader_memory import PRIVATE_BUFFERS, private_buffer_bytes

MAX_PRIVATE_BYTES = PRIVATE_BUFFERS


@composed_workflow('provider_book_controller', ProviderBookController)
@composed_workflow('provider_comic_controller', ProviderComicController)
class PrivateController(ReaderHost, ProviderUI):
    from services.workflow_host import OwnedAttribute

    operation_busy = OwnedAttribute('provider_document', 'busy')

    def __init__(self, manager, session):
        self.manager, self.app, self.session = manager, manager.app, session
        from .composition.presentation import reading_presentation
        self.format_services = reading_presentation(self)
        self.provider_document()
        self._crypt_cancel = None
        self.operation_busy = False
        import asyncio
        self.operation_idle = asyncio.Event()
        self.operation_idle.set()
        self.presentation_destination = self.app.native_host.state.destination
        self.privacy_gate = None

    def watch_provider_layout(self):
        if self.crypt_reader is not None and self.crypt_reader.kind == '.pdf':
            return None
        return self.provider_comic_controller().watch_provider_layout()

    @property
    def cloud_busy(self):
        return self.operation_busy

    def set_cloud_busy(self, busy):
        """Compatibility entry for existing reader tools."""
        self.set_document_busy(busy)

    def set_document_busy(self, busy):
        if busy and (self.manager.terminal or self.provider_document().terminal or not self.app.active_host):
            raise OSError('This private document has retired.')
        self.operation_busy = busy
        if busy:
            self.operation_idle.clear()
        else:
            self.operation_idle.set()
        self.manager.update_session(self)
        if not busy:
            self.manager.revoke_stale()

    def cancel_cloud(self, widget=None, **kwargs):
        if self._crypt_cancel is not None:
            self._crypt_cancel.set()

    def _show_crypt_content(self, kind, content, *, view=None):
        return self.app._show_crypt_content(kind, content, view=view or self, owner=self)

    def show_view(self, view, **kwargs):
        origin = getattr(self, '_opening_origin', None)
        if origin is not None:
            if not self.app.active_host or not self.app.workspace.accepts(self._opening_token):
                return False
            destination, navigation, selection = origin
            if (self.app.native_host.state.destination != destination or self.app.navigation_generation != navigation
                    or self.app.workspace.active != selection):
                # The loaded session stays available without taking over the
                # view or selection the user chose while its bytes were read.
                return True
        self.manager.bind(self)
        reader = self.crypt_reader
        document_title = Path(reader.name).name if reader is not None else self.session.title
        suffix = ':metadata' if view is getattr(self, 'crypt_metadata_view', None) else ''
        kwargs.update(destination=self.__dict__.get('presentation_destination', 'documents'), route=kwargs.get('route') or 'private:' + self.session.id + suffix,
                      title=kwargs.get('title') or document_title or 'Private document')
        epub = getattr(self, 'provider_epub_view', None)
        if epub is not None:
            epub.on_tools_changed = self.app.adaptive.render
        presented = self.app.show_view(view, **kwargs)
        if origin is not None:
            self._open_presented = bool(presented)
        return presented

    def resume_crypt(self, widget=None, **kwargs):
        if self.manager.available(self.session.id) and self.crypt_reader is not None:
            self.show_view(self.crypt_view)
            mode = getattr(self, 'crypt_markdown_mode', None)
            if mode == 'preview' and getattr(self, 'crypt_preview', None) not in self.crypt_content.children:
                self.toggle_private_preview()
            elif (mode == 'edit' and getattr(self.crypt_edit_mode, 'value', '') == 'Formatted'
                  and getattr(self, 'crypt_formatted', None) is None):
                self.show_private_markdown_editor()
            resume = self.resume_suspended_page()
            progress = getattr(self, '_provider_progress', None)
            if progress is not None and self.crypt_reader.editable:
                progress.watch_surface(initial=True)
            return resume

    def resume_suspended_page(self):
        """Reload released pixels without changing the retained route or chrome."""
        task = getattr(self, '_resume_page_task', None)
        if (not getattr(self, 'page_suspended', False)
                or not self.manager.available(self.session.id)
                or (task is not None and not task.done())):
            return

        async def reload_when_idle():
            import asyncio
            # A suspended reader can still own a draining decode or an
            # encrypted progress write. Wait without cancelling the writer.
            await self.operation_idle.wait()
            progress = getattr(self, '_provider_progress', None)
            if progress is not None and progress.worker is not None:
                await asyncio.wait({progress.task})
            if (self.page_suspended and self.provider_document().can_start()
                    and self.manager.active is self and self.manager.available(self.session.id)
                    and self.app.visible_reader() == self.session.id):
                await self.read_crypt_page()

        self._resume_page_task = self.app.loop.create_task(reload_when_idle())
        return self._resume_page_task

    def close_crypt(self, widget=None, **kwargs):
        return self.app.request_reader_close(self.session.id)

    async def discard_crypt(self, widget=None, **kwargs):
        progress = getattr(self, '_provider_progress', None)
        if progress is not None:
            progress.sample_surface()
            await progress.flush()
        if self.app.active_host and self.manager.controllers.get(self.session.id) is self:
            return self.app.close_session(self.session.id, choice='discard')

    async def show_editor_open(self, widget=None, **kwargs):
        return await self.app.show_editor_open(widget, **kwargs)

    async def show_crypt_save_as(self, widget=None, **kwargs):
        if self.app.cloud_busy or self.session.id not in self.app.workspace.sessions:
            return
        self.manager.bind(self)
        return await self.app.show_crypt_save_as(widget, owner=self, **kwargs)


class _ReplacementReceipt:
    """Ephemeral observations produced only by this manager's flush path."""
    def __init__(self, manager, observations):
        self.manager, self.observations = manager, observations


class PrivateSessions:
    def __init__(self, app):
        self.app = app
        self.controllers = {}
        self.active = None
        self.terminal = False
        from .protection import for_app
        for_app(app).register(self, self.privacy_gates)

    def _replacement_observations(self):
        from commonUtils.ui.native.text_size import native_backend
        if self.terminal or not self.app.active_host or getattr(self.app, 'private_sessions', self) is not self:
            raise OSError('The previous private workspace is no longer available.')
        observations = []
        members = tuple(self.controllers.items())
        # Access checks may invoke provider code. Run them before taking the
        # all-controller state observation, so one cannot stale an earlier row.
        for _, owner in members:
            try:
                owner.document_access()
            except ValueError:
                raise OSError('Unlock the private document before replacing this workspace.') from None
        for key, owner in members:
            document = owner.__dict__.get('_provider_document')
            if document is None:
                raise OSError('The private document owner changed during replacement.')
            workspace, session = self.app.workspace, owner.session
            token = workspace.token(key)
            if (owner.manager is not self or owner.app is not self.app
                    or workspace.sessions.get(key) is not session or not workspace.accepts(token)
                    or document.terminal or document.busy or document.worker is not None
                    or document.cancel is not None or getattr(owner, '_opening_token', None) is not None
                    or owner.private_dirty()):
                raise OSError('Save or finish the private document before replacing this workspace.')
            progress = getattr(owner, '_provider_progress', None)
            if progress is not None:
                progress.require_idle()
            reader = document.reader
            workflow = getattr(owner, '_provider_markdown', None)
            editor = getattr(workflow, 'formatted', None)
            content = getattr(workflow, 'content', None)
            view = getattr(editor, 'view', None)
            mounted = editor is not None and content is not None and view in content.children
            native = mounted and not getattr(reader, 'read_only', False) and native_backend(view).startswith(('toga_iOS.', 'toga_android.'))
            if (getattr(workflow, 'closed', False) or (mounted and getattr(editor, 'closed', False))
                    or getattr(workflow, 'preparing_formatted', None) is not None
                    or (getattr(workflow, 'pending', None) is not None and not workflow.pending.done())):
                raise OSError('Finish the private editor before replacing this workspace.')
            # Keep owner references in the receipt; ids only compare exact identity,
            # never overloaded equality on controllers or native view wrappers.
            state = (key, id(owner), id(owner.manager), id(owner.app), id(workspace), id(session), token,
                     id(document), id(reader), id(getattr(reader, 'source', None)), id(workflow),
                     id(content), id(getattr(workflow, 'source', None)), id(editor), id(view), mounted, native,
                     id(progress), id(getattr(progress, 'state', None)),
                     (progress.generation, progress.snapshot()) if progress is not None else None,
                     getattr(editor, 'bridge', None), getattr(editor, '_revision', None))
            observations.append((owner, editor if native else None, state,
                                 (self.app, workspace, session, document, reader, getattr(reader, 'source', None),
                                  workflow, content, getattr(workflow, 'source', None), editor, view,
                                  progress, getattr(progress, 'state', None))))
        if tuple((key, id(owner)) for key, owner in self.controllers.items()) != tuple((key, id(owner)) for key, owner in members):
            raise OSError('The private workspace changed during replacement.')
        return observations

    async def prepare_replacement(self, *, valid=lambda: True):
        # Complete already admitted observations before taking the receipt.
        # Receipt validation still rejects page/editor changes during preparation.
        for owner in tuple(self.controllers.values()):
            progress = getattr(owner, '_provider_progress', None)
            if progress is not None and not owner.operation_busy:
                await progress.prepare_replacement()
            if not valid():
                import asyncio
                raise asyncio.CancelledError
        observations = self._replacement_observations()
        for index, (owner, editor, state, references) in enumerate(observations):
            if editor is None:
                continue
            try:
                await editor.flush()
            except (ValueError, OSError):
                raise OSError('Could not preserve private editor input. Keep the document open.') from None
            if not valid():
                import asyncio
                raise asyncio.CancelledError
            current = self._replacement_observations()
            if (len(current) != len(observations) or current[index][2][:-1] != state[:-1]
                    or type(editor._revision) is not int or editor._revision <= state[-1]):
                raise OSError('The private editor changed during replacement.')
            observations[index] = current[index]
        self.require_replacement_safe(_ReplacementReceipt(self, observations))
        for index, (owner, editor, state, references) in enumerate(observations):
            progress = getattr(owner, '_provider_progress', None)
            if progress is None:
                continue
            try:
                await progress.prepare_replacement()
            except (OSError, ValueError):
                raise OSError('Could not preserve private reader progress.') from None
            if not valid():
                import asyncio
                raise asyncio.CancelledError
            current = self._replacement_observations()
            if (len(current) != len(observations) or current[index][2][:-3] != state[:-3]
                    or current[index][2][-2:] != state[-2:]):
                raise OSError('The private workspace changed during replacement.')
            observations[index] = current[index]
        receipt = _ReplacementReceipt(self, observations)
        self.require_replacement_safe(receipt)
        return receipt

    def prepare_replacement_sync(self):
        for owner in tuple(self.controllers.values()):
            progress = getattr(owner, '_provider_progress', None)
            if progress is not None and not owner.operation_busy:
                progress.checkpoint_sync()
        self.require_replacement_safe()
        observations = self._replacement_observations()
        for index, (owner, editor, state, references) in enumerate(observations):
            progress = getattr(owner, '_provider_progress', None)
            if progress is None:
                continue
            progress.checkpoint_replacement()
            current = self._replacement_observations()
            if (len(current) != len(observations) or current[index][2][:-3] != state[:-3]
                    or current[index][2][-2:] != state[-2:]):
                raise OSError('The private workspace changed during replacement.')
            observations[index] = current[index]
        receipt = _ReplacementReceipt(self, observations)
        self.require_replacement_safe(receipt)
        return receipt

    def require_replacement_safe(self, receipt=None):
        current = self._replacement_observations()
        if receipt is None:
            if any(editor is not None for _, editor, _, _ in current):
                raise OSError('Save or close the native private editor before replacing this workspace.')
        elif (not isinstance(receipt, _ReplacementReceipt) or receipt.manager is not self
              or [row[2] for row in current] != [row[2] for row in receipt.observations]):
            raise OSError('The private workspace changed during replacement.')

    def _admit_retirement(self):
        # Plain-state transition only. The lifecycle validates immediately before
        # this segment, then claims the successor before invoking any callbacks.
        self.terminal = True
        for owner in self.controllers.values():
            owner._provider_document.terminal = True

    def retire(self, receipt=None):
        """Accepted replacement only; no manifest, history or credential writes."""
        if not self.terminal:
            self.require_replacement_safe(receipt)
            self._admit_retirement()
        failed = False
        for owner in self.controllers.values():
            try:
                owner.provider_document().dispose()
            except Exception:
                failed = True
        if failed:
            raise OSError('Private document cleanup is incomplete; retry retirement.')

    def privacy_gates(self):
        return tuple(owner.privacy_gate for owner in self.controllers.values())

    async def opening_rejected(self, message):
        """Admission failures must be visible from every folder entry point."""
        import toga
        self.app.document_status.value = message
        await self.app.main_window.dialog(toga.InfoDialog('Could not open document', message))
        return False

    def revoke_stale(self):
        """A credential replacement in any scene also retires displayed bytes."""
        import toga
        for key, owner in list(self.controllers.items()):
            try:
                owner.document_access()
            except ValueError:
                pass
            else:
                continue
            self.app.workspace.invalidate(key)
            pending = owner._crypt_cancel
            if pending is not None:
                pending.set()
            progress = getattr(owner, '_provider_progress', None)
            if pending is None and not owner.operation_busy and getattr(progress, 'worker', None) is None:
                self.close(key, discard=True, force=True)
            # A busy owner retains its source until the actual worker retires.
            # Visible widgets are detached immediately below; finish_operation
            # retries this policy once it can safely close the retained reader.
            owner.session.title = ''
            view = getattr(owner, 'crypt_view', None)
            if view is not None:
                for child in list(view.children):
                    view.remove(child)
                view.add(toga.Label('Private session locked. Reopen after unlocking.'))

    def identity(self, copies, key):
        from services.documents.progress import document_identity
        identity = document_identity(copies, key, app=self.app)
        # The transient workspace model uses strings. Keep protected lookup
        # tuples inside the progress layer and never publish them as references.
        return sha256(repr(identity).encode()).hexdigest()

    def available(self, key):
        owner = self.controllers.get(key)
        if self.terminal or not self.app.active_host or owner is None or owner.crypt_reader is None:
            return False
        try:
            owner.document_access()
        except ValueError:
            return False
        return True

    def bind(self, owner):
        if self.terminal or not self.app.active_host:
            raise OSError('This private workspace has retired.')
        self.suspend(except_owner=owner)
        readers = getattr(self.app, 'readers', None)
        if readers is not None and readers.active is not None:
            readers.active.suspend()
        self.active = owner
        self.app.workspace.activate(owner.session.id)
        self.update_session(owner)

    def update_session(self, owner):
        owner.session.dirty = owner.private_dirty()

    def flush_visible_progress(self):
        owner = self.active
        progress = getattr(owner, '_provider_progress', None)
        if progress is not None:
            progress.sample_surface()
            progress.schedule(immediate=True)

    def suspend(self, *, except_owner=None, keep_active_markdown=False):
        from .ios_content_background import clear
        clear(self.app)
        for owner in self.controllers.values():
            if owner is except_owner:
                continue
            progress = getattr(owner, '_provider_progress', None)
            if progress is not None:
                progress.sample_surface()
                progress.schedule(immediate=True)
            # Memory trimming also runs when Android backgrounds the activity.
            # The retained reader must still show the same surface on wake;
            # clearing its preview would expose the source input underneath.
            if (keep_active_markdown and owner is self.active
                    and getattr(owner.crypt_reader, 'kind', None) in {'.md', '.markdown'}):
                continue
            if progress is not None:
                progress.stop_surface()
            for name in ('_provider_layout_task', '_provider_width_task'):
                task = getattr(owner, name, None)
                if task is not None:
                    task.cancel()
                    setattr(owner, name, None)
            from .page_animation import cancel_page_slide
            cancel_page_slide(getattr(owner, 'crypt_content', None))
            owner.clear_private_preview()
            for name in ('provider_spread', 'provider_epub_view'):
                view = getattr(owner, name, None)
                if view is not None:
                    view.dispose()
                    if view in owner.crypt_content.children:
                        owner.crypt_content.remove(view)
                    delattr(owner, name)
                    owner.page_suspended = True
            image = getattr(owner, 'crypt_image', None)
            if image is not None and (image.image is not None or hasattr(image, 'scroll')):
                image.image = None
                owner.page_suspended = True
            source = getattr(owner.crypt_reader, 'source', None)
            from .reading.reader_memory import trim_content_cache
            trim_content_cache(source)
        from .external_display import sync as sync_external
        sync_external(self.app)

    async def open(self, copies, key, *, prepared=None, destination=None, privacy_gate=None, edit=False,
                   image_immersive=None):
        import asyncio
        if self.terminal or not self.app.active_host:
            return False
        if not self.app.require_document_feature(key, copies=copies):
            return False
        destination = destination or self.app.native_host.state.destination
        from .files_ui import local_read_available, ordinary_local_copies
        if reading_capabilities(copies).credential_bound and not hasattr(self.app, 'cloud_view'):
            self.app.show_cloud(present=False)
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None and not ordinary_local_copies(copies):
                await restore
        independent = (self.app.cloud_busy and reading_capabilities(copies).offline
            and local_read_available(self.app, private=not ordinary_local_copies(copies)))
        if self.app.cloud_busy and not independent:
            if reading_capabilities(copies).remote:
                from features.rclone.mobile.cloud_ui import explain_remote_busy
                await explain_remote_busy(self.app)
            return False
        try:
            identity = self.identity(copies, key)
        except (OSError, ValueError) as error:
            return await self.opening_rejected(str(error))
        existing = next((owner for owner in self.controllers.values()
                         if owner.session.resource == identity), None)
        if existing is not None and prepared is None and not self.available(existing.session.id):
            self.app.document_status.value = 'Unlock the connection again before reopening this private document.'
            return False
        if existing is not None and prepared is None:
            held = reading_capabilities(existing._crypt_reader_store)
            gate_for = getattr(copies, 'privacy_gate_for', None)
            incoming_gate = privacy_gate if privacy_gate is not None else (
                gate_for(key) if gate_for is not None else getattr(copies, 'privacy_gate', None))
            if (held != reading_capabilities(copies)
                    or (incoming_gate is not None and incoming_gate is not existing.privacy_gate)):
                return await self.opening_rejected(
                    'Close this document before reopening it with different access.')
            capture = getattr(copies, 'capture_access', None)
            if capture is not None:
                try:
                    capture(key)()
                except (OSError, ValueError):
                    return await self.opening_rejected('Unlock this document before opening it again.')
            existing.presentation_destination = destination
            if image_immersive is not None and getattr(existing.crypt_reader, 'image_document', False):
                existing.crypt_immersive = image_immersive
                existing.reading_frame.set_immersive(image_immersive, comic=False, image=True)
            self.app.document_password.value = ''
            self.bind(existing)
            resume = existing.resume_crypt()
            if resume is not None:
                await resume
            if edit and existing.crypt_reader.kind in {'.md', '.markdown'} and not getattr(existing.crypt_reader, 'read_only', False):
                existing.clear_private_preview()
                existing.show_private_markdown_editor()
            return True
        if len(self.controllers) >= MAX_PRIVATE_SESSIONS:
            return await self.opening_rejected(
                f'All {MAX_PRIVATE_SESSIONS} file document slots are in use. Local, LocalCrypt and remote files share this limit. '
                'Go to Documents → Open documents and close one, then try again. Existing documents and unsaved edits were kept.')
        if prepared is None and not self.app.checkpoint():
            return False
        previous = self.active
        # A restored list entry is only metadata; release its placeholder slot
        # before claiming the real reader, and restore it automatically on failure.
        from .document_sources import file_source
        try:
            source = file_source(self.app, copies, key, session_only=True)
        except (OSError, ValueError, AttributeError, KeyError):
            source = None
        if source is not None:
            for pending in list(self.app.workspace.sessions.values()):
                if pending.provider == 'credential-reference' and getattr(pending, 'cache_source', None) == source:
                    self.app.workspace.close(pending.id, guard=lambda session: True)
        selection = self.app.workspace.active
        origin = self.app.native_host.state.destination, self.app.navigation_generation, selection
        capabilities = reading_capabilities(copies)
        password = self.app.document_password.value
        protected = capabilities.private or capabilities.credential_bound or bool(password) or privacy_gate is not None
        from features.images.document import IMAGE_EXTENSIONS
        suffix = Path(key).suffix.lower()
        shared_read = not protected and (not capabilities.writable or suffix in {'.pdf', *IMAGE_EXTENSIONS})
        try:
            session = self.app.workspace.open('provider-session', identity, 'text', transient=True,
                                              protected=protected, shared_read=shared_read)
        except ValueError as error:
            return await self.opening_rejected(str(error) + '\n\nGo to Documents → Open documents to manage open items.')
        self.app.workspace.active = selection
        try:
            owner = self._register_opening_owner(session, copies, key=key, destination=destination,
                                                 privacy_gate=privacy_gate, independent=independent)
        except (OSError, ValueError) as error:
            self.app.workspace.close(session.id, guard=lambda session: True)
            return await self.opening_rejected(str(error))
        token = self.app.workspace.token(session.id)
        owner._opening_origin, owner._opening_token, owner._open_presented = origin, token, False
        owner.initial_image_immersive = image_immersive
        def retire_open():
            bound = self.active is owner
            self.close(session.id, discard=True, force=True)
            if bound and self.app.active_host and previous is not None and previous.session.id in self.controllers:
                previous.resume_crypt()
        remote_open = reading_capabilities(copies).remote
        if remote_open:
            self.app.remote_read_busy = True
            self.app.set_cloud_busy(True)
        try:
            password = self.app.document_password.value
            self.app.document_password.value = ''
            if password:
                from services.session_auth import ResumePassword
                owner.privacy_gate = ResumePassword(password)
                from .protection import for_app
                for_app(self.app).changed()
            opened = await owner.provider_document().opening.open(
                copies=copies, key=key, password=password, prepared=prepared, edit=edit)
            if not opened or not self.app.active_host or not self.app.workspace.accepts(token):
                retire_open()
                return False
            reader = owner.crypt_reader
            total = private_buffer_bytes(self.controllers.values())
            if total > MAX_PRIVATE_BYTES:
                retire_open()
                return await self.opening_rejected(
                    'This document would exceed the shared 32 MiB file content memory budget. '
                    'Go to Documents → Open documents and close an item, then try again. '
                    'A document that exceeds the budget by itself cannot be opened. Existing documents and unsaved edits were kept.')
            return await self._publish_opened_session(owner, session, reader, copies, key,
                                                      privacy_gate=privacy_gate)
        except (Exception, asyncio.CancelledError):
            retire_open()
            raise
        finally:
            password = None
            owner._opening_origin = owner._opening_token = owner.initial_image_immersive = None
            owner._independent_operation = False
            if remote_open:
                self.app.set_cloud_busy(False)
                self.app.remote_read_busy = False

    def _register_opening_owner(self, session, copies, *, key, destination, privacy_gate, independent):
        owner = PrivateController(self, session)
        capture = getattr(copies, 'capture_access', None)
        owner.document_access = capture(key) if capture is not None else lambda: None
        gate_for = getattr(copies, 'privacy_gate_for', None)
        owner.privacy_gate = gate_for(key) if gate_for is not None else getattr(copies, 'privacy_gate', None)
        if privacy_gate is not None:
            owner.privacy_gate = privacy_gate
        owner.credential_client = self.app.cloud_client
        owner.credential_generation = getattr(self.app.cloud_client, 'generation', None)
        owner.presentation_destination = destination
        owner._independent_operation = independent
        self.controllers[session.id] = owner
        from .protection import for_app
        for_app(self.app).changed()
        return owner

    async def _publish_opened_session(self, owner, session, reader, copies, key, *, privacy_gate):
        # Initial resume is one opening, not a user visit to the placeholder page.
        for name in ('comic_navigation', 'pdf_navigation'):
            navigation = getattr(reader, name, None)
            if navigation is not None:
                navigation.visits.previous.clear()
        session.kind = ('image' if getattr(reader, 'image_document', False) else 'pdf' if reader.kind == '.pdf' else 'epub' if reader.kind == '.epub' else 'comic' if not reader.editable
                        else 'markdown' if reader.kind in {'.md', '.markdown'} else 'text')
        session.title = Path(reader.name).name
        from .document_sources import file_source
        try:
            session.history_source = file_source(self.app, copies, key) if privacy_gate is None else None
        except (OSError, ValueError, AttributeError, KeyError):
            session.history_source = None
        if privacy_gate is None:
            try:
                source = file_source(self.app, copies, key, session_only=True)
                self.app.credential_document_lists.remember(session, source)
            except (OSError, ValueError, AttributeError, KeyError):
                self.app.credential_document_lists.notice()
        if owner._open_presented:
            self.bind(owner)
        else:
            self.suspend(except_owner=self.active)
        self.app.save_workspace()
        return True

    @staticmethod
    def offline_owner(owner):
        source = getattr(getattr(owner, 'crypt_reader', None), 'source', None)
        return (reading_capabilities(getattr(owner, '_crypt_reader_store', None)).offline
                or (getattr(source, 'cache_token', None) is not None and not source.closed))

    def activate(self, key, *, destination=None):
        destination = destination or self.app.native_host.state.destination
        owner = self.controllers.get(key)
        from .files_ui import ordinary_local_copies
        local = ordinary_local_copies(getattr(owner, '_crypt_reader_store', None))
        if not self.available(key) or (self.app.cloud_busy and not (local or ((getattr(self.app, 'transfer_busy', False) or getattr(self.app, 'remote_read_busy', False)) and self.offline_owner(owner)))):
            if self.available(key) and reading_capabilities(getattr(owner, '_crypt_reader_store', None)).remote:
                from features.rclone.mobile.cloud_ui import explain_remote_busy
                self.app.loop.create_task(explain_remote_busy(self.app))
            return False
        owner.presentation_destination = destination
        self.bind(owner)
        owner.resume_crypt()
        self.app.credential_document_lists.remember(owner.session)
        self.app.save_workspace()
        return True

    def dirty(self):
        return any(owner.private_dirty() for owner in self.controllers.values())

    def close(self, key, *, discard=False, force=False):
        if self.terminal:
            return False
        owner = self.controllers.get(key)
        if owner is None:
            return False
        from .files_ui import ordinary_local_copies
        local = (ordinary_local_copies(getattr(owner, '_crypt_reader_store', None))
            or ((getattr(self.app, 'transfer_busy', False) or getattr(self.app, 'remote_read_busy', False)) and self.offline_owner(owner)))
        if not force and ((self.app.cloud_busy and not local) or owner._crypt_cancel is not None or owner.operation_busy):
            return False
        if not force and owner.private_dirty() and not discard:
            owner.resume_crypt()
            owner.crypt_title.text = 'Unsaved changes: save,\nor discard and close.'
            return False
        if getattr(getattr(owner, '_provider_progress', None), 'worker', None) is not None:
            return False
        progress = getattr(owner, '_provider_progress', None)
        if not force and progress is not None:
            progress.sample_surface()
            if progress.schedule(immediate=True) is not None:
                return False
        if not ProviderUI.clear_private_reader(owner, discard=True):
            return False
        if not force:
            self.app.credential_document_lists.closed(owner.session)
        owner.session.title = ''
        owner.session.view.clear()
        owner.session.dirty = False
        self.app.workspace.close(key, guard=lambda session: True)
        del self.controllers[key]
        if self.active is owner:
            self.update_session(owner)
            self.active = None
        self.app.save_workspace()
        privacy = getattr(self.app, 'screen_privacy', None)
        if privacy is not None:
            privacy.refresh()
        return True

    def clear(self, *, discard=False):
        if self.terminal:
            return False
        owners = list(self.controllers.values())
        if any(owner._crypt_cancel is not None or owner.operation_busy
               or getattr(getattr(owner, '_provider_progress', None), 'worker', None) is not None
               for owner in owners):
            return False
        dirty = next((owner for owner in owners if owner.private_dirty()), None)
        if dirty is not None and not discard:
            dirty.resume_crypt()
            dirty.crypt_title.text = 'Unsaved changes: save,\nor discard and close.'
            return False
        self.flush_visible_progress()
        if any(progress.schedule(immediate=True) is not None for owner in owners
               if (progress := getattr(owner, '_provider_progress', None)) is not None):
            return False
        for owner in owners:
            if not self.close(owner.session.id, discard=True, force=True):
                return False
        return True
