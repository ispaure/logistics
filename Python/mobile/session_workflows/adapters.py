"""Reader-specific close/retirement adapters; model/privacy policy stays source-owned."""
from features.text_editor.mobile.ui import TextEditorView


def close_notes_library(host, key, choice, *, leaving_reader=False):
    owner = getattr(host, 'vault_browser', None)
    if owner is not None and owner.session is host.workspace.sessions[key]:
        owner.dispose()
    else:
        host.workspace.close(key, guard=lambda session: True)
    host.reader_closed(key)
    return True

def close_credential_reference(host, key, choice, *, leaving_reader=False):
    host.credential_document_lists.closed(host.workspace.sessions[key])
    host.workspace.close(key, guard=lambda session: True)
    host.save_workspace()
    host.reader_closed(key)
    return True

def close_provider_session(host, key, choice, *, leaving_reader=False):
    if not host.provider_sessions().close(key, discard=choice == 'discard'):
        return False
    host.reader_closed(key)
    return True

def close_library(host, key, choice, *, leaving_reader=False):
    return host.reader_manager().close(key)


def close_managed_text(host, key, choice, *, leaving_reader=False):
    owner = host.text_views.get(key)
    def guard(session):
        if owner is None:
            return True
        if choice == 'keep' and getattr(owner.document, 'private', False) and owner.document.modified:
            owner.status.text = 'Save this session-only draft before closing.'
            return False
        try:
            if choice == 'delete':
                host.recent_documents.forget(session.provider, session.resource)
                from ..resource_imports import ResourceImports
                imports = getattr(host, 'resource_imports', None) or ResourceImports(host.private_root)
                imports.forget(session.provider, session.resource)
                host.store.delete(owner.document)
            elif choice == 'save':
                host.store.save(owner.document)
            elif choice == 'discard':
                host.store.discard(owner.document)
            else:
                host.store.checkpoint(owner.document)
            return True
        except (OSError, ValueError) as error:
            owner.status.text = 'Could not close; edits retained: ' + str(error)
            if hasattr(host, 'close_notice'):
                host.close_notice.text = owner.status.text
            return False
    was_current = owner is host.editor_view
    if not host.workspace.close(key, guard=guard):
        return False
    host.text_views.pop(key, None)
    if owner is not None:
        from ..reader_lifecycle import scroll_position
        owner.capture()
        positions = host.__dict__.setdefault('_closed_text_positions', {})
        positions.pop(owner.session.resource, None)
        positions[owner.session.resource] = (dict(owner.session.view), scroll_position(owner.preview))
        while len(positions) > 256:
            del positions[next(iter(positions))]
        owner.dispose()
    if was_current:
        host.current = None
        remaining = host.workspace.sessions.get(host.workspace.active)
        if remaining is not None and remaining.provider == 'managed-text':
            host.open_document(remaining.resource)
        else:
            host.editor_view = TextEditorView(host)
            host.editor_view.bind()
    host.save_workspace()
    host.refresh_documents()
    host.reader_closed(key)
    if was_current and host.adaptive.split is not None and not leaving_reader:
        if host.current is not None:
            host.adaptive.present(host.document_view, route='editor', title=host.current.name if host.current else 'New document')
            host.adaptive.show_list()
        else:
            host.adaptive.clear_details()
    return True


from features.notebooks.mobile.documents import close_notebook


ADAPTERS = {
    'notebook': close_notebook,
    'notes-library': close_notes_library,
    'credential-reference': close_credential_reference,
    'provider-session': close_provider_session,
    'library': close_library,
    'managed-text': close_managed_text,
}
