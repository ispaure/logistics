"""Host resolution of the document providers contributed by one location."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path


def document_locations(entry):
    result = []
    remote_scope = entry.storage_scope == 'remote' or (entry.storage_scope is None and entry.local is None)
    if not remote_scope and entry.local is not None:
        if getattr(entry.local, 'private', False):
            from features.rclone.desktop_service import service
            result.append(('Encrypted Copy', lambda: service.localcrypt.open(entry.local.connection), False))
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
