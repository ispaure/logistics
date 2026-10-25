"""Notes Library commands for the desktop location actions page."""
from features.contributions import UIAction
from features.text_editor.notes import vault_root


def sources(entry):
    from services.documents.ui.locations import document_locations
    return document_locations(entry)


def available(entry):
    return bool(entry.local is not None or entry.remote_source == 'rclone')


def actions(entry):
    found = []
    for label, factory, remote in sources(entry):
        provider = None
        try:
            provider = factory()
            if vault_root(provider, '', provider.list('')) is not None:found.append((label, factory, remote))
        except (OSError, ValueError, KeyError):
            continue
        finally:
            if provider is not None and hasattr(provider, 'close'):provider.close()
    commands = []
    for label, factory, remote in found:
        def launch(factory=factory, remote=remote):
            from .ui.notes_library import open_notes
            return open_notes(factory, entry.name, remote=remote)
        commands.append(UIAction(name='Open Notes Library',
            callback=launch, description=('Read cloud notes in Documents.' if remote else
                         'Edit Markdown notes in this local copy in Documents.')))
    return commands
