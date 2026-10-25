"""Mobile host composition for document adapters; formats see provider sessions."""


def document_source(provider, path):
    """The sole mobile choice of provider-backed reader adapter and mapped key."""
    if getattr(provider, 'remote_storage', False):
        resource = getattr(provider, 'resource', provider)
        if hasattr(resource, 'readers'):
            return resource.readers(), path
    from features.rclone.localcrypt.mobile.resources import encrypted_document
    source = encrypted_document(provider, path)
    return source if source is not None else (TextDocumentCopies(provider), path)


def document_copies(provider):
    return document_source(provider, '')[0]


async def open_provider_document(app, provider, path, *, destination=None, **options):
    """Resolve format dispatch before presenting a storage-neutral editor."""
    from pathlib import Path
    from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS
    from services.documents.storage import DocumentResource, DocumentPolicy
    suffix = Path(path).suffix.lower()
    if suffix == '.rmdoc':
        from services.documents.mobile_notebooks import open_notebook
        from features.notebooks.notebook import MAX_ARCHIVE
        if getattr(provider, 'remote_storage', False):
            raise ValueError('Cloud notebooks are read-only. Create a local copy before opening.')
        return await open_notebook(app, resource=DocumentResource(provider, path, max_bytes=MAX_ARCHIVE), destination=destination)
    copies, key = document_source(provider, path)
    if suffix in SOURCE_EXTENSIONS or not DocumentPolicy.for_provider(provider).persistent:
        app.show_cloud(present=False)
        return await app.open_crypt(copies=copies, key=key, destination=destination, **options)
    return await app.open_download(path=provider._locate(path), destination=destination)


class TextDocumentCopies:
    """Text presentation over a generic document provider."""
    encrypted = False

    def __init__(self, provider):
        self.provider = provider

    @property
    def offline(self):
        from commonUtils.runtime.resources.local import LocalFiles
        return isinstance(self.provider, LocalFiles)

    def open(self, key, *, password='', cancelled=lambda: False, read_provider=None):
        from services.documents.storage import DocumentResource
        with DocumentResource(read_provider if read_provider is not None else self.provider, key,
                              max_bytes=1024 * 1024, independent=False) as resource:
            data = resource.read(cancelled=cancelled)
            from features.text_editor.resources import TextReader
            reader = TextReader(resource.name, data, key=resource.path, revision=resource.revision)
        from services.documents.storage import document_writable
        reader.read_only = not document_writable(self.provider)
        return reader

    def save(self, reader, text, *, cancelled=lambda: False):
        from services.documents.storage import document_writable
        if not document_writable(self.provider, reader):
            raise ValueError('Remote Markdown is read-only. Create a local copy before editing.')
        from services.documents.storage import DocumentResource
        data = reader.session.encode(text)
        revision = DocumentResource.publish(self.provider, reader.key, data, max_bytes=1024 * 1024,
            expected_revision=reader.revision, cancelled=cancelled)
        from features.text_editor.resources import TextReader
        return TextReader(reader.name, data, key=reader.key, revision=revision)


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
    if not Path(value['root']).is_dir():
        return None, value
    provider = LocalFiles(value['root'])
    return DocumentResource(provider, value['path'], max_bytes=MAX_ARCHIVE), value


def remember_notebook_resource(document):
    """Host policy permits ordinary references; format code supplies no paths."""
    from commonUtils.persistence import atomic_write_json
    resource = document.resource
    if resource is None or not resource.policy.persistent or document.recovery is None:
        return
    atomic_write_json(notebook_binding(document.recovery, document.key),
        dict(root=str(resource.provider.root), path=resource.path,
             revision=resource.revision, dirty=document.dirty), durable_directory=True)


class NotesDocumentAccess:
    """Host-owned access/privacy policy for a retained Notes Library surface."""
    def __init__(self, provider, *, client, active, privacy_gate, privacy_gates):
        from services.documents.storage import DocumentPolicy
        self.provider, self.client, self.active = provider, client, active
        self.privacy_gate, self.privacy_gates = privacy_gate, privacy_gates
        self.policy = DocumentPolicy.for_provider(provider)
        self.original_client = client()
        self.generation = getattr(self.original_client, 'generation', None)
        self.label = 'Remote' if getattr(provider, 'remote_storage', False) else ('Private storage' if not self.policy.persistent else 'Local')

    def valid(self):
        if not self.active():
            return False
        if not self.policy.persistent and (self.original_client is not self.client()
                or self.generation != getattr(self.client(), 'generation', None)
                or any(gate.locked for gate in self.privacy_gates())):
            return False
        # Provider I/O validates its grant. Do not call check() from a cancellation
        # predicate: scoped provider checks themselves consult this predicate.
        return True

    def webview(self, *, max_bytes, **options):
        from types import SimpleNamespace
        from services.documents.mobile_views import document_webview
        view = document_webview(SimpleNamespace(policy=self.policy), **options)
        if not self.policy.persistent:
            view.max_html_bytes = max_bytes
        return view

    def title(self, path):
        return path if self.policy.persistent else ''

    def speech_gate(self):
        return None if self.policy.persistent else self.privacy_gate()

    def validate_preview(self, html, max_bytes):
        if not self.policy.persistent and len(html.encode('utf-8')) > max_bytes:
            raise ValueError('Private preview exceeds its memory-only limit.')


def attach_notes_return(app, library, owner):
    if owner is None:
        return
    workflow = owner._provider_markdown
    if workflow is None:
        return
    path = library.path
    destination = library.destination

    async def return_to_library():
        from features.text_editor.mobile.document_dialogs import DocumentDialog
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
