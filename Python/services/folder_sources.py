"""Discover one consistent set of folder sources for a page refresh."""

from dataclasses import dataclass

from features import registry
from features.contributions import LocalFolderSource, RemoteFolderSource
from models.local_folder import LocalFolder
from services.folder_entries import get_folder_entries
from commonUtils.runtime.operations import check_cancelled


@dataclass(frozen=True)
class LocalSourceSnapshot:
    """Local folders read from one backend context during a refresh."""

    feature_name: str
    label: str
    source: LocalFolderSource
    folders: tuple[LocalFolder, ...]


@dataclass(frozen=True)
class RemoteSourceSnapshot:
    """Remote names read from one backend context during a refresh."""

    feature_name: str
    label: str
    source: RemoteFolderSource
    remote_names: tuple[str, ...]


@dataclass(frozen=True)
class FolderSources:
    """A page's source data, with exclusions applied to represented names."""

    local_folders: tuple[LocalFolder, ...]
    local_sources: tuple[LocalSourceSnapshot, ...]
    remote_sources: tuple[RemoteSourceSnapshot, ...]
    represented_remote_names: frozenset[str]


def discover_folder_sources(*, remote_providers=None, local_providers=None, cancelled=lambda: False) -> FolderSources:
    """Read each provider once; keep backend-owned context attached to its source."""

    remote_providers = registry.get_remote_folder_sources() if remote_providers is None else remote_providers
    local_providers = registry.get_local_folder_sources() if local_providers is None else local_providers
    remote_sources, local_sources = [], []
    for registered in remote_providers:
        check_cancelled(cancelled)
        for source in registered.contribution.get_sources():
            check_cancelled(cancelled)
            remote_sources.append(RemoteSourceSnapshot(registered.feature_name, registered.contribution.name,
                                                       source, tuple(source.get_remote_names())))
    for registered in local_providers:
        check_cancelled(cancelled)
        for source in registered.contribution.get_sources():
            check_cancelled(cancelled)
            local_sources.append(LocalSourceSnapshot(registered.feature_name, registered.contribution.name,
                                                     source, tuple(source.get_local_folders())))
    check_cancelled(cancelled)
    local_folders = tuple(
        entry.local for entry in get_folder_entries() if entry.local is not None
    )
    remote_entries = get_folder_entries(
        (name for source in remote_sources for name in source.remote_names),
        local_folders=(),
        include_local_only=False,
    )
    check_cancelled(cancelled)
    return FolderSources(
        local_folders=local_folders,
        local_sources=tuple(local_sources),
        remote_sources=tuple(remote_sources),
        represented_remote_names=frozenset(entry.name for entry in remote_entries),
    )
