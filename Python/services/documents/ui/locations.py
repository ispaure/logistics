"""Host resolution of the document providers contributed by one location."""
from pathlib import Path


def document_locations(entry):
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


def document_location_available(entry):
    return bool(entry.local is not None or entry.remote_source == 'rclone')
