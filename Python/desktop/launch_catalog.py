"""Logistics-owned document launch catalog, shared by all chooser surfaces."""
from features import registry
from features.contributions import DocumentLauncherContribution


def _open_markdown(parent):
    from commonUtils.ui import pyside as qt
    from services.local_storage import install_local_storage_policy
    install_local_storage_policy()
    from services.documents.ui.editors import install_editor_dialogs
    install_editor_dialogs()
    from commonUtils.ui.markdown.window import open_markdown
    from services.documents.ui.editors import choose_editor_resource, open_editor_choice
    choice = choose_editor_resource(parent, 'open', markdown=True)
    if choice is None:
        return None
    if getattr(choice.provider, 'private', False):
        return open_editor_choice(choice, parent, markdown=True)
    path = choice.provider.root / choice.path
    choice.close()
    return open_markdown(path, allow_edit=True)


def _new_markdown(parent):
    from services.local_storage import install_local_storage_policy
    install_local_storage_policy()
    from services.documents.ui.editors import install_editor_dialogs
    install_editor_dialogs()
    from commonUtils.ui.markdown.window import open_markdown
    return open_markdown(None, allow_edit=True)


def document_launchers():
    """Core Markdown plus enabled feature registrations, in declared order."""
    entries = [DocumentLauncherContribution('markdown', 'Markdown Editor', _open_markdown,
               'markdown', 20, _new_markdown, 'Write and preview formatted notes.')]
    entries.extend(entry.contribution for entry in registry.get_document_launchers())
    return {entry.editor_id: entry for entry in sorted(entries, key=lambda entry: entry.order)}
