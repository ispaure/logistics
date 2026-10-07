"""Discover one consistent set of folder sources for a page refresh."""

from dataclasses import dataclass

from features import registry
from features.contributions import LocalFolderSource, RemoteFolderSource
from models.local_folder import LocalFolder
from services.folder_entries import get_folder_entries


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


def discover_folder_sources() -> FolderSources:
    """Read each provider once; keep backend-owned context attached to its source."""

    remote_sources = tuple(
        RemoteSourceSnapshot(
            feature_name=registered.feature_name,
            label=registered.contribution.name,
            source=source,
            remote_names=tuple(source.get_remote_names()),
        )
        for registered in registry.get_remote_folder_sources()
        for source in registered.contribution.get_sources()
    )
    local_sources = tuple(
        LocalSourceSnapshot(
            feature_name=registered.feature_name,
            label=registered.contribution.name,
            source=source,
            folders=tuple(source.get_local_folders()),
        )
        for registered in registry.get_local_folder_sources()
        for source in registered.contribution.get_sources()
    )
    local_folders = tuple(
        entry.local for entry in get_folder_entries() if entry.local is not None
    )
    remote_entries = get_folder_entries(
        (name for source in remote_sources for name in source.remote_names),
        local_folders=(),
        include_local_only=False,
    )
    return FolderSources(
        local_folders=local_folders,
        local_sources=local_sources,
        remote_sources=remote_sources,
        represented_remote_names=frozenset(entry.name for entry in remote_entries),
    )
