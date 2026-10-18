"""Notes Library commands for the desktop location actions page."""
from pathlib import Path
from features.contributions import UIAction
from features.text_editor.notes import vault_root


def sources(entry):
    result = []
    if entry.local is not None:
        if getattr(entry.local, 'private', False):
            from features.rclone.localcrypt.backend import CryptResources
            result.append(('LocalCrypt', lambda: CryptResources(entry.local.connection), False))
        else:
            from commonUtils.runtime.local_files import LocalFiles
            result.append(('Local', lambda: LocalFiles(entry.local.path), False))
    if entry.remote_source == 'rclone' and entry.remote_name is not None and entry.remote_context is not None:
        def remote():
            from features.rclone.remote_resources import RemoteResources
            from features.rclone.executable import get_rclone_path
            return RemoteResources(Path(entry.remote_context), entry.remote_name, binary=get_rclone_path())
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
        commands.append(UIAction(name='Open Notes Library' + (' (' + label + ')' if len(found) > 1 else ''),
            callback=launch, description='Browse Markdown notes in Documents. Remote libraries have no search or recursive index.'))
    return commands
