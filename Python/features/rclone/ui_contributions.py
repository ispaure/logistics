"""
UI contributions exposed by the Logistics rclone feature.
"""

from pathlib import Path

from features.contributions import (
    Feature,
    FolderFeatureContribution,
    SettingsContribution,
    RemoteFolderSource,
    RemoteFolderSourceContribution,
    UIAction,
    WorkflowContribution,
)
from features.rclone import actions, configuration, credentials
from models.folder_entry import FolderEntry


def _get_config_path(entry: FolderEntry) -> Path | None:
    """Return the selected rclone config carried by this folder entry."""

    if entry.remote_source != 'rclone':
        return None

    if entry.remote_context is None:
        return None

    return Path(entry.remote_context)


def _is_available(entry: FolderEntry) -> bool:
    """Return whether rclone has sync actions for this logical folder."""

    return entry.has_remote and _get_config_path(entry) is not None


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    """Return rclone sync actions available for a logical folder entry."""

    config_path = _get_config_path(entry)

    if config_path is None:
        return []

    ui_actions = []

    if entry.local is not None and entry.remote_name is not None:
        ui_actions.append(
            UIAction(
                name='Push...',
                description=(
                    'Configure and push local data to the matching rclone remote.'
                ),
                workflow_id='rclone_push',
                workflow_data=entry
            )
        )

    if entry.remote_name is not None:
        from . import session
        from features.rclone.localcrypt.backend import LocalCryptFolder
        values = session.credentials(config_path)
        is_crypt = bool(config_path.suffix == '.session' and values
                        and values.get(entry.remote_name, {}).get('type') == 'crypt')
        encrypted = isinstance(entry.local, LocalCryptFolder)
        if encrypted:
            item = entry.local.connection
            ui_actions.append(UIAction(name='Pull',
                callback=lambda: actions.pull_encrypted_copy(entry.remote_name, config_path, item=item, review=True),
                description='Refresh this LocalCrypt copy with ciphertext from its backing remote.', destructive=True))
        elif is_crypt and entry.local is None:
            from features.rclone.transfers.ui.pull_dialog import pull_new_copy
            ui_actions.append(UIAction(name='Pull',
                callback=lambda: pull_new_copy(entry.remote_name, config_path),
                description='Choose LocalCrypt (recommended) or a readable Local copy.', destructive=True))
        else:
            association = getattr(entry.remote_context, 'item', None)
            ui_actions.append(UIAction(name='Pull',
                callback=lambda: actions.pull_remote(entry.remote_name, config_path, review=True, **({'package': association.package} if association else {})),
                description='Sync decrypted files into the Local folder.', destructive=True))
    return ui_actions


class CopyContext:
    def __init__(self, item):
        self.item = item
    def __fspath__(self):
        return str(self.item.context)
    def __str__(self):
        return str(self.item.data)
    def __eq__(self, other):
        return isinstance(other, CopyContext) and self.item == other.item


def _matching_local_folders(config_path, *, local_folders=None, copies=None, local_links=None):
    """Prefer ordinary Local on the account row; otherwise attach its crypt copy.

    Separate LocalCrypt sources remain selectable when both copies exist.
    Match package identity as well as remote names; session paths alone can collide.
    """
    from models.folder_discovery import get_local_folders
    from features.rclone.localcrypt.backend import connections, LocalCryptFolder
    from . import session
    folders = list(get_local_folders() if local_folders is None else local_folders)
    names = {folder.name for folder in folders}
    package = session.package_path(config_path)
    from features.rclone.localcrypt.connections import connections as local_connections
    linked = {item.data: item for item in (local_connections() if local_links is None else local_links)}
    folders = [folder for folder in folders if getattr(folder, 'path', None) not in linked
               or linked[folder.path].package == package]
    names = {folder.name for folder in folders}
    for item in connections() if copies is None else copies:
        if item.context == config_path and item.package == package and item.remote not in names:
            folders.append(LocalCryptFolder(item))
            names.add(item.remote)
    return folders


def _get_remote_sources() -> list[RemoteFolderSource]:
    """Return one Folders source for every loaded credential config."""

    from models.folder_discovery import get_local_folders
    from features.rclone.localcrypt.backend import connections, LocalCryptFolder
    sources = []
    represented_copies = set()
    configs = credentials.get_loaded_credential_config_paths()
    copies = connections()
    from features.rclone.localcrypt.connections import connections as local_connections
    links = local_connections()
    ordinary = get_local_folders() if configs else []
    for config_path in configs:
        folders = _matching_local_folders(config_path, local_folders=ordinary, copies=copies, local_links=links)
        represented_copies.update(folder.connection for folder in folders if isinstance(folder, LocalCryptFolder))
        sources.append(RemoteFolderSource(
            name=config_path.stem + (' (session)' if config_path.suffix == '.session' else ''),
            get_remote_names=lambda config_path=config_path: configuration.get_rclone_remote_names(config_path),
            context=config_path,
            get_local_folders=lambda folders=folders: folders))
    from models.local_folder import LocalFolder
    from . import session
    for item in links:
        if any(session.package_path(path) == item.package for path in configs):
            continue
        sources.append(RemoteFolderSource(
            name=f'{item.package.stem} — Local',
            get_remote_names=lambda item=item: [item.remote], context=CopyContext(item),
            get_local_folders=lambda item=item: [LocalFolder(item.data)]))
    for item in copies:
        if item in represented_copies:
            continue
        sources.append(RemoteFolderSource(
            name=f'{item.package.stem} — LocalCrypt',
            get_remote_names=lambda item=item: [item.remote], context=CopyContext(item),
            get_local_folders=lambda item=item: [LocalCryptFolder(item)]))
    return sources


def _open_browse_workflow(data=None, parent=None):
    from .ui.remote_browser import open_remote
    association = getattr(data.remote_context, 'item', None)
    return open_remote(_get_config_path(data), data.remote_name, parent,
                       package=association.package if association else None)


def _open_push_workflow(data=None, parent=None):
    from features.rclone.transfers.ui.push_dialog import RclonePushDialog
    from features.rclone.localcrypt.ui.views import ensure_session
    package = getattr(data.remote_context, "item", None)
    if not ensure_session(Path(data.remote_context), package=package.package if package else None, parent=parent):
        return False
    dialog = RclonePushDialog(data, parent=parent)
    return dialog.exec()


def _create_page(parent=None):
    from features.rclone.ui.page import RclonePage

    return RclonePage(parent=parent)


def _push_settings(parent=None):
    from features.rclone.transfers.ui.push_settings import PushSettings
    return PushSettings(parent)


def _software_settings_note(parent):
    from commonUtils.ui import pyside as qt
    note = qt.QLabel('When changing a version, update its URLs and SHA-256 hashes together.', parent)
    note.setWordWrap(True)
    return note


def get_contributions() -> Feature:
    """Return UI contributions provided by rclone."""

    from . import initialize
    return Feature(
        id='rclone', label='rclone', initialize=initialize,
        remote_folder_sources=[
            RemoteFolderSourceContribution(
                name='rclone',
                get_sources=_get_remote_sources,
                order=10
            )
        ],
        folder_features=[
            FolderFeatureContribution(
                name='rclone',
                is_available=_is_available,
                get_actions=_get_actions,
                order=10,
                actions_horizontal=True,
                supports_private_folders=True
            )
        ],
        workflows=[
            WorkflowContribution(workflow_id='rclone_browse', handler=_open_browse_workflow),
            WorkflowContribution(
                workflow_id='rclone_push',
                handler=_open_push_workflow
            )
        ],
        settings=[
            SettingsContribution(
                name='Credential packages',
                settings_id='credentials',
                create_widget=_create_page,
                order=10,
                separate_tab=True,
                scope="personal",
            ),
            SettingsContribution('Push exclusions', 'push_exclusions', _push_settings, order=15, scope='personal'),
            SettingsContribution(
                'Software downloads', 'software_downloads', _software_settings_note,
                config_files=(Path(__file__).with_name('config.ini'),), order=20)
        ]
    )
