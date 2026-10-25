"""Keep live text drafts bound to verified Move/Rename results."""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from commonUtils.persistence.publication import mutation_lock
from commonUtils.runtime.operations import MutationIncomplete, MutationResult
from commonUtils.runtime.resources.paths import resource_name
from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS


async def prepare_document_mutation(app, request):
    # Native formatted edits can still be queued in the WebView. Flush them
    # before replacing the reader identity used by its change callbacks.
    manager = app.provider_sessions()
    for owner in list(manager.controllers.values()):
        reader = owner.crypt_reader
        copies = getattr(owner, '_crypt_reader_store', None)
        if reader is not None and binding_relative(copies, reader, request) is not None:
            if owner.operation_busy or owner._crypt_cancel is not None:
                raise ValueError('Wait for the affected document operation to finish.')
            workflow = getattr(owner, '_provider_markdown', None)
            if workflow is not None:
                await workflow.flush()
    return DocumentMutation(app, request)


def relative_document(provider, key, source, path):
    """Match ordinary aliases by physical path; private views by namespace."""
    if provider is None:
        return None
    if source is None or path is None:
        raise ValueError('Select a file or folder first.')
    if not provider.private and not source.private:
        origin = Path(source.root).resolve() / path
        candidate = Path(provider.root).resolve() / key
    elif (provider.storage_id == source.storage_id
          and provider.storage_namespace == source.storage_namespace):
        origin, candidate = PurePosixPath(path), PurePosixPath(key)
    else:
        return None
    try:
        relative = candidate.relative_to(origin).as_posix()
        return '' if relative == '.' else relative
    except ValueError:
        return None


def binding_relative(copies, reader, request):
    downloaded = getattr(request.provider, 'copies', None)
    if (downloaded is not None and getattr(copies, 'provider', None) is None
            and Path(copies.root).resolve() == Path(downloaded.root).resolve()
            and reader.key == request.provider.key):
        return ''
    return relative_document(getattr(copies, 'provider', None), reader.key,
                             request.provider, request.path)


@dataclass(frozen=True)
class Binding:
    owner: object
    reader: object
    copies: object
    relative: str
    token: tuple
    readonly: bool


class DocumentMutation:
    """Capture on the UI thread, verify/move off-thread, adopt without rebuilding UI.

    The widget retains the draft, selection and undo state. Only the saved-byte
    baseline and resource identity change. A failed handoff never accepts edits
    as saved and never silently recreates the old source.
    """
    def __init__(self, app, request):
        self.app, self.request = app, request
        self.bindings = []
        from .notebook_mutations import NotebookMutations
        self.notebooks = NotebookMutations(app, request)
        manager = app.provider_sessions()
        owners = getattr(app.workspace, 'window_owners', None)
        hosts = list(owners.hosts.values()) if owners is not None else [app]
        try:
            for host in hosts:
                sessions = getattr(host, 'private_sessions', None)
                for owner in list(sessions.controllers.values()) if sessions else ():
                    reader = owner.crypt_reader
                    copies = getattr(owner, '_crypt_reader_store', None)
                    if reader is None:
                        continue
                    relative = binding_relative(copies, reader, request)
                    if relative is None:
                        continue
                    if host is not app:
                        raise ValueError('Close the affected document in the other window before moving it.')
                    if (not manager.available(owner.session.id) or owner.operation_busy
                            or owner._crypt_cancel is not None):
                        raise ValueError('Wait for the affected document operation to finish or unlock it again.')
                    if not reader.editable or getattr(reader, 'read_only', False):
                        raise ValueError('Close the affected reader before moving or renaming its file or folder.')
                    self.bindings.append(Binding(owner, reader, copies, relative,
                        app.workspace.token(owner.session.id), owner.crypt_text.readonly))
            for binding in self.bindings:
                binding.owner.set_cloud_busy(True)
                binding.owner.crypt_text.readonly = True
        except BaseException:
            self.release()
            raise

    def execute(self, cancelled):
        from features.text_editor.resources import LocalTextCopies
        from features.rclone.localcrypt.mobile.resources import encrypted_document
        request = self.request
        destination = request.provider if request.kind == 'rename' else request.destination.resolve()
        target = (('/'.join(p for p in (request.path.rpartition('/')[0], request.target) if p))
                  if request.kind == 'rename' else request.target)
        if request.kind == 'rename':
            resource_name(request.target)
        target = destination.relative(target)
        if request.provider.private and not destination.private and not request.plaintext_approved:
            raise ValueError('Use Move to confirm moving private content to unencrypted storage.')
        destination_document = encrypted_document(destination, target) if self.bindings and destination.private else None
        copies = (destination_document[0] if destination_document else LocalTextCopies(destination)) if self.bindings else None
        with mutation_lock:
            for binding in self.bindings:
                key = '/'.join(p for p in (target, binding.relative) if p)
                suffix = Path(key).suffix.lower()
                if (suffix not in SOURCE_EXTENSIONS
                        or (suffix in {'.md', '.markdown'}) != (binding.reader.kind in {'.md', '.markdown'})):
                    raise ValueError('Close the affected document before changing its editor type.')
                current = binding.copies.open(binding.reader.key, cancelled=cancelled)
                if current.data != binding.reader.data or current.revision != binding.reader.revision:
                    raise ValueError('An open document changed on disk. Reload or use Save As before moving it.')
            self.notebooks.prepare(destination, target, cancelled)
            result = request.execute(cancelled, destination=destination)
            updated = []
            try:
                notebooks = self.notebooks.reopen(destination)
                for binding in self.bindings:
                    key = '/'.join(p for p in (
                        destination_document[1] if destination_document else target, binding.relative) if p)
                    # Publication is complete. Late cancellation must not leave a
                    # surviving editor saving to a source that no longer exists.
                    reader = copies.open(key)
                    if reader.data != binding.reader.data:
                        raise ValueError('The moved document changed before reopening.')
                    updated.append((binding, copies, reader))
            except Exception as error:
                raise MutationIncomplete('The file was moved, but the editor could not follow it. '
                    'Edits are retained; use Save As and inspect the destination before retrying.',
                    MutationResult(destination_published=True, source_state='removed')) from error
        return result, updated, notebooks

    def apply(self, result):
        from .private_sessions import PrivateSessions
        from .provider_ui import private_label
        from .document_sources import file_source
        app = self.app
        for binding, copies, reader in result[1]:
            encrypted = getattr(copies, 'encrypted', True)
            owner, session = binding.owner, binding.owner.session
            if (not app.active_host or not app.workspace.accepts(binding.token)
                    or owner.crypt_reader is not binding.reader
                    or not app.private_sessions.available(session.id)):
                continue
            old_identity = session.identity
            previous_source = getattr(session, 'history_source', None)
            try:
                app.credential_document_lists.relocated(session)
                if previous_source is not None:
                    from .recent_documents import RecentDocuments
                    app.recent_documents.forget('file-reference', RecentDocuments.reference_id(previous_source))
            except (OSError, ValueError):
                app.credential_document_lists.notice()
            owner.crypt_reader, owner._crypt_reader_store = reader, copies
            owner.credential_client = app.cloud_client
            owner.credential_generation = getattr(app.cloud_client, 'generation', None)
            session.resource = PrivateSessions.identity(copies, reader.key)
            session.title = Path(reader.name).name
            owners = getattr(app.workspace, 'window_owners', None)
            if owners is not None and session.identity != old_identity:
                owners.claim(app.workspace.window_id, session.identity, private=session.transient)
                owners.release(app.workspace.window_id, old_identity)
            app.workspace.invalidate(session.id)
            owner.crypt_text.set_filename(reader.name)
            owner.crypt_title.text = private_label(session.title)
            owner.crypt_page.items = reader.labels
            owner.crypt_page.value = reader.labels[0]
            owner.crypt_save.text = 'Save encrypted copy' if encrypted else 'Save local file'
            workflow = getattr(owner, '_provider_markdown', None)
            if workflow is not None:
                workflow.relocated(private=encrypted)
            # Keep an existing session-only privacy gate across plaintext moves.
            # New encrypted locations adopt their current credential gate too.
            if encrypted:
                owner.privacy_gate = owner.privacy_gate or getattr(app.cloud_client, 'session_privacy', None)
            session.history_source = None
            for name in ('cache_id', 'cache_source'):
                session.__dict__.pop(name, None)
            app.private_sessions.update_session(owner)
            try:
                if owner.privacy_gate is None:
                    session.history_source = file_source(app, copies, reader.key)
                if owner.privacy_gate is None or encrypted:
                    app.credential_document_lists.remember(session, file_source(app, copies, reader.key, session_only=True))
                if session.history_source is not None:
                    app.recent_documents.remember_file(session, session.history_source)
            except (OSError, ValueError):
                app.credential_document_lists.notice()
        self.notebooks.apply(result[2])
        app.save_workspace()

    def release(self):
        self.notebooks.release()
        for binding in self.bindings:
            owner = binding.owner
            if (not self.app.active_host or self.app.private_sessions.controllers.get(owner.session.id) is not owner
                    or owner.crypt_reader is None):
                owner.operation_busy = False
                owner.operation_idle.set()
                continue
            owner.crypt_text.readonly = binding.readonly
            owner.set_cloud_busy(False)
            owner.refresh_private_text_controls()
