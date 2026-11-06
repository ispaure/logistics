"""Mobile host composition for document adapters; formats see provider sessions."""


def document_source(provider, path):
    """The sole mobile choice of provider-backed reader adapter and mapped key."""
    factory = getattr(provider, 'document_readers', None)
    key = getattr(provider, 'document_key', lambda path: path)(path)
    return (factory(), key) if factory is not None else (TextDocumentCopies(provider), key)


def document_copies(provider):
    return document_source(provider, '')[0]


async def open_provider_document(app, provider, path, *, destination=None, fullscreen=False, **options):
    """Resolve format dispatch before presenting a storage-neutral editor."""
    from pathlib import Path
    from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS
    from services.documents.storage import DocumentResource, DocumentPolicy
    if not app.require_document_feature(path):
        return False
    from services.documents.mobile_reading import reading_capabilities
    copies, key = document_source(provider, path)
    required = reading_capabilities(copies).required_feature
    if required is not None and not app.require_feature(required):
        return False
    suffix = Path(path).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        from features.video.mobile.player import open_video
        if fullscreen:
            return await open_video(app, provider, path, fullscreen=True)
        return await open_video(app, provider, path)
    if suffix == '.rmdoc':
        from services.documents.mobile_notebooks import open_notebook
        from features.notebooks.notebook import MAX_ARCHIVE
        if getattr(provider, 'remote_storage', False):
            raise ValueError('Cloud notebooks are read-only. Create a local copy before opening.')
        return await open_notebook(app, resource=DocumentResource(provider, path, max_bytes=MAX_ARCHIVE), destination=destination)
    from features.images.document import IMAGE_EXTENSIONS
    if suffix in SOURCE_EXTENSIONS or suffix in IMAGE_EXTENSIONS or not DocumentPolicy.for_provider(provider).persistent:
        return await app.open_crypt(copies=copies, key=key, destination=destination, **options)
    return await app.open_download(path=provider._locate(path), destination=destination)


from features.video.formats import VIDEO_EXTENSIONS
from services.documents.provider_documents import ProviderDocuments


def remember_video(app, content):
    """Publish reopen references through existing ordinary/encrypted history owners."""
    history = getattr(app, 'recent_documents', None)
    if history is None:
        return
    from pathlib import Path
    from mobile.document_sources import file_source
    from mobile.workspace import Session
    copies, key = document_source(content.provider, content.path)
    source = file_source(app, copies, key, session_only=True)
    if source is None:
        return
    session = Session('', 'file-reference', history.reference_id(source), 'video',
                      title=Path(content.path).name)
    manager = getattr(app, 'credential_document_lists', None)
    if manager is not None:
        manager.remember(session, source, opened=False)
    if not content.restricted:
        history.remember_file(session, file_source(app, copies, key))
    if manager is not None:
        manager.queue_views()


class TextDocumentCopies(ProviderDocuments):
    """Compatibility name for storage-neutral provider document sessions."""


async def confirm_export(app, resource):
    """An OS export or ordinary recovery target publishes outside private storage."""
    if resource is None or resource.policy.persistent:
        return True
    import toga
    return await app.main_window.dialog(toga.ConfirmDialog(
        'Export to unencrypted storage?',
        'This creates a decrypted copy outside private storage. Continue?'))


def notebook_binding(recovery, key):
    from pathlib import Path
    from features.notebooks.notebook import identifier
    return Path(recovery.root) / identifier(key) / 'source.json'


def restore_notebook_resource(recovery, key):
    """Ordinary recovery references only; private sessions never call this adapter."""
    import json
    from commonUtils.runtime.resources.local import LocalFiles
    from services.documents.storage import DocumentResource
    from features.notebooks.notebook import MAX_ARCHIVE
    path = notebook_binding(recovery, key)
    if not path.exists():
        return None, None
    if path.is_symlink() or path.stat().st_size > 16384:
        raise ValueError('Invalid notebook source binding.')
    value = json.loads(path.read_text())
    from pathlib import Path
    source_root = Path(value['root'])
    relative = Path(value['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid notebook source path.')
    from types import SimpleNamespace
    from mobile.document_sources import local_document_path
    original = source_root / relative
    relocated = local_document_path(SimpleNamespace(private_root=Path(recovery.root).parent), original)
    if relocated != original:
        source_root = relocated
        for _ in relative.parts:
            source_root = source_root.parent
    if not source_root.is_dir():
        return None, value
    provider = LocalFiles(source_root)
    return DocumentResource(provider, value['path'], max_bytes=MAX_ARCHIVE), value


def remember_notebook_resource(document):
    """Publish ordinary references and return a rollback for this exact write."""
    import json
    from commonUtils.persistence import atomic_write_json
    from commonUtils.persistence.atomic import atomic_write_bytes
    from commonUtils.persistence.publication import mutation_lock
    from features.notebooks.protocol import RecoveryIncomplete
    resource = document.resource
    if resource is None or not resource.policy.persistent or document.recovery is None:
        return
    path = notebook_binding(document.recovery, document.key)
    state = dict(root=str(resource.provider.root), path=resource.path,
                 revision=resource.revision, dirty=document.dirty)
    expected = json.dumps(state, ensure_ascii=False, allow_nan=False).encode('utf-8')
    def observed():
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
    with mutation_lock:
        previous = observed()
        def rollback():
            with mutation_lock:
                def validate():
                    if observed() != expected:
                        raise ValueError('Notebook source binding changed in another window.')
                if observed() == previous:
                    return
                validate()
                try:
                    if previous is None:
                        path.unlink()
                    else:
                        atomic_write_bytes(path, previous, validate=validate)
                except Exception:
                    if observed() != previous:
                        raise
        try:
            atomic_write_json(path, state, durable_directory=True)
        except Exception:
            try:
                rollback()
            except Exception as error:
                raise RecoveryIncomplete('Notebook source binding could not be restored. '
                                         'Keep this draft open and use Save As.', published=None) from error
            raise
        return rollback


class NotesDocumentAccess:
    """Host-owned access/privacy policy for a retained Notes Library surface."""
    def __init__(self, provider, *, client, active, privacy_gate, privacy_gates):
        from services.documents.storage import DocumentPolicy
        self.provider, self.client, self.active = provider, client, active
        self.privacy_gate, self.privacy_gates = privacy_gate, privacy_gates
        self.policy = DocumentPolicy.for_provider(provider)
        capture = getattr(provider, 'capture_access', None)
        self._check_access = capture('') if capture is not None else lambda: None
        self.label = 'Remote' if getattr(provider, 'remote_storage', False) else ('Private storage' if not self.policy.persistent else 'Local')

    def valid(self):
        if not self.active():
            return False
        if not self.policy.persistent and any(gate.locked for gate in self.privacy_gates()):
            return False
        try:
            self._check_access()
        except ValueError:
            return False
        # Provider I/O validates its grant. Do not call check() from a cancellation
        # predicate: scoped provider checks themselves consult this predicate.
        return True

    def webview(self, *, max_bytes, **options):
        from types import SimpleNamespace
        from services.documents.mobile_views import document_webview
        view = document_webview(SimpleNamespace(policy=self.policy), inline_video=True, **options)
        if not self.policy.persistent:
            view.max_html_bytes = max_bytes
        return view

    def title(self, path):
        return path if self.policy.persistent else ''

    def speech_gate(self):
        return None if self.policy.persistent else self.privacy_gate()

    def validate_preview(self, html, max_bytes):
        if not self.policy.persistent and len(html.encode('utf-8')) > max_bytes:
            raise ValueError(f'This page exceeds the {max_bytes / (1024 * 1024):g} MiB '
                             'in-memory preview limit. Reduce its embedded media and try again.')


def attach_notes_return(app, library, owner):
    if owner is None:
        return
    workflow = owner._provider_markdown
    if workflow is None:
        return
    path = library.path
    destination = library.destination

    async def return_to_library():
        from services.documents.authoring.document_dialogs import DocumentDialog
        if not library.valid() or owner.session.id not in app.workspace.sessions:
            return
        try:
            await workflow.flush()
        except ValueError as error:
            owner.crypt_title.text = str(error)
            return
        if owner.private_dirty():
            choice = await app.main_window.dialog(DocumentDialog(
                'Save changes before returning?', 'Save this note or discard its unsaved changes.',
                discard_label='Discard changes'))
            if not library.valid() or owner.session.id not in app.workspace.sessions:
                return
            if choice == 'save':
                await owner.save_crypt()
                if owner.private_dirty():
                    return
            elif choice != 'discard':
                return
        if not app.private_sessions.close(owner.session.id, discard=True):
            return
        library.present(destination=destination)
        await library.open_note(path, remember=False)

    workflow.action_items = [item for item in workflow.action_items if item[0] != 'Return to Notes Library']
    workflow.action_items.insert(0, ('Return to Notes Library', return_to_library))
    workflow.menu_state = None
    workflow.refresh_controls()
