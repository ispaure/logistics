"""Notes Library commands for the desktop location actions page."""
from pathlib import Path
from features.contributions import UIAction
from features.text_editor.notes import vault_root


def sources(entry):
    result = []
    remote_scope = entry.storage_scope == 'remote' or (entry.storage_scope is None and entry.local is None)
    if not remote_scope and entry.local is not None:
        if getattr(entry.local, 'private', False):
            from features.rclone.desktop_service import service
            result.append(('LocalCrypt', lambda: service.localcrypt.open(entry.local.connection), False))
        else:
            from commonUtils.runtime.resources.local import LocalFiles
            result.append(('Local', lambda: LocalFiles(entry.local.path), False))
    if remote_scope and entry.remote_source == 'rclone' and entry.remote_name is not None and entry.remote_context is not None:
        def remote():
            from features.rclone.desktop_service import service
            from features.rclone.remote_access import DesktopRemoteLocation
            return service.remotes.open(DesktopRemoteLocation(Path(entry.remote_context), entry.remote_name))
        result.append(('Remote', remote, True))
    return result


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
