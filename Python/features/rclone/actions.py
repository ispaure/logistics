"""
Actions for the Logistics rclone feature.
"""

from pathlib import Path

import config

from commonUtils.filesystem import directories as dirUtils
from commonUtils.runtime.diagnostics import Severity, log

from features.rclone.transfers import sync as rclone_sync
from models.local_folder import LocalFolder


def _transfer(source, destination, *, review=False, operation='Push', **kwargs):
    if review:
        from features.rclone.transfers.workflow import reviewed_sync
        return reviewed_sync(source, destination, operation=operation, **kwargs)
    return rclone_sync.rclone_sync(source, destination, **kwargs)


def pull_remote(remote_name: str, config_path: str | Path, *, package=None, review=False) -> bool:
    """Pull an rclone remote to its matching local Logistics folder."""

    from features.rclone.localcrypt.ui.views import ensure_session
    if not ensure_session(config_path, package=package):
        return False
    source_path = remote_name + ':'
    destination_path = Path(
        config.LogisticsConfig().path_remote_local,
        remote_name
    )

    from . import session
    from features.rclone.localcrypt.connections import LocalConnection
    credential_package = session.package_path(config_path)
    association = (LocalConnection(Path(credential_package).absolute(), remote_name, destination_path.parent.absolute())
                   if credential_package and session.credentials(config_path) is not None else None)
    if association:
        association.check()
    accepted = _transfer(
        source_path,
        destination_path,
        config_path=config_path, review=review, operation='Pull',
        **({'before_start': association.publish} if association and review else {})
    )
    if accepted and association and not review:
        association.publish()
    return accepted


def push_to_cloud(
    folder: LocalFolder,
    config_path: str | Path,
    track_renames: bool = False, *, review=False
) -> bool:
    """Push a local Logistics folder to its rclone remote."""

    from features.rclone.localcrypt.ui.views import ensure_session
    from features.rclone.localcrypt.connections import for_path as local_connection
    association = local_connection(folder.path) if getattr(folder, 'path', None) is not None else None
    if association:
        config_path = association.context
    if not ensure_session(config_path, package=association.package if association else None):
        return False
    from features.rclone.localcrypt.backend import push_target, for_path
    source_path = folder.path
    destination_path = push_target(source_path, config_path, folder.name)

    return _transfer(
        source_path,
        destination_path,
        config_path=config_path,
        track_renames=track_renames,
        copy_links=for_path(source_path) is None, review=review
    )


def push_specific_directory(
    folder: LocalFolder,
    config_path: str | Path,
    directory_path: str,
    bandwidth_limit: str | None = None, *, review=False
) -> bool:
    """Push a specific directory into a Logistics folder's rclone remote."""

    directory = dirUtils.Directory(Path(directory_path))

    if not directory.is_dir():
        log(
            Severity.ERROR,
            'Push Individual Folder',
            'The path you have given is not a valid directory!',
            popup=True
        )
        return False

    if bandwidth_limit == '':
        bandwidth_limit = None

    from features.rclone.localcrypt.ui.views import ensure_session
    from features.rclone.localcrypt.connections import for_path as local_connection
    association = local_connection(folder.path) if getattr(folder, 'path', None) is not None else None
    if association:
        config_path = association.context
    if not ensure_session(config_path, package=association.package if association else None):
        return False
    from features.rclone.localcrypt.backend import for_path, push_target
    item = for_path(directory.path)
    destination_path = push_target(directory.path, config_path, folder.name, specific=True)

    return _transfer(
        directory.path,
        destination_path,
        config_path=config_path,
        bw_limit=bandwidth_limit,
        copy_links=item is None, review=review
    )


def pull_encrypted_copy(remote_name, config_path, *, item=None, review=False):
    from features.rclone.localcrypt.backend import connection, backing_target, unlock
    from features.rclone.localcrypt.ui.views import ensure_session
    if not ensure_session(config_path, package=item.package if item else None):
        return False
    item = item or connection(config_path, remote_name)
    values = unlock(item)
    from features.rclone.localcrypt.backend import validate_ciphertext_tree
    validate_ciphertext_tree(item)
    if review:
        from features.rclone.transfers.workflow import reviewed_sync
        return reviewed_sync(backing_target(values, remote_name), item.data, operation='Pull',
            config_path=config_path, copy_links=False, crypt_item=item, before_start=item.publish)
    item.publish()
    return rclone_sync.rclone_sync(backing_target(values, remote_name), item.data, config_path=config_path, copy_links=False)
