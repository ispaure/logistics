"""Desktop source categories without losing provider-owned action contexts."""
from pathlib import Path

from services.folders.entries import get_folder_entries
from .catalog import FolderCopy, project_catalog, source_category as catalog_category


SOURCE_NAMES = ('Local', 'Cloud', 'Home Server')


def source_category(source):
    """Use mobile's explicit network-share package convention, not protocol guesses."""
    context = source.source.context
    item = getattr(context, 'item', None)
    package = item.package if item else context
    return catalog_category(source.feature_name, package)


def remote_entries(source, local_folders):
    return get_folder_entries(source.remote_names, remote_source=source.feature_name,
        remote_context=source.source.context, include_local_only=False,
        local_folders=source.local_folders if source.local_folders is not None else local_folders)


def local_entries(sources):
    """Merge by physical copy, preferring entries carrying loaded sync context."""
    copies = []
    for source in sorted(sources.remote_sources, key=lambda source: hasattr(source.source.context, 'item')):
        for entry in remote_entries(source, sources.local_folders):
            if entry.local is not None:
                copies.append(FolderCopy(entry.local.path, entry.name, payload=entry))
    folders = [*sources.local_folders,
               *(folder for source in sources.local_sources for folder in source.folders),
               *(folder for source in sources.remote_sources for folder in source.local_folders or ())]
    copies.extend(FolderCopy(entry.local.path, entry.name, payload=entry)
                  for entry in get_folder_entries(local_folders=folders))
    return [group.copies[0].payload for group in project_catalog(copies, grouping='physical')]


def local_entry_category(entry, sources):
    """Classify physical copies by their owner, including unloaded rclone copies."""
    path = entry.local.path
    if any(source.feature_name == 'dropbox' and any(folder.path == path for folder in source.folders)
           for source in sources.local_sources):
        return 'Dropbox'
    if (entry.remote_source == 'rclone'
            or any(folder.path == path for folder in sources.local_folders)
            or any(source.feature_name == 'rclone' and any(folder.path == path for folder in source.folders)
                   for source in sources.local_sources)
            or any(source.feature_name == 'rclone' and any(folder.path == path for folder in source.local_folders or ())
                   for source in sources.remote_sources)):
        return 'Rclone'
    return 'Others'


def workspace_remote_sources(sources):
    """Keep offline account destinations and unassociated rclone copies in Cloud.

    A saved copy association identifies a remote even while its ZIP is locked.
    Local and LocalCrypt copies of that remote share one online destination.
    """
    from dataclasses import replace
    from features.contributions import RemoteFolderSource
    from features.rclone import session
    from services.folders.sources import RemoteSourceSnapshot

    declared = list(sources.remote_sources)
    represented_copies = {folder.path for source in declared for folder in source.local_folders or ()
                          if folder.name in source.remote_names}
    for entry in local_entries(sources):
        if getattr(entry.local, 'private', False) and entry.local.path not in represented_copies:
            from features.rclone.ui_contributions import CopyContext
            item = entry.local.connection
            source = RemoteFolderSource(item.package.stem, lambda name=entry.name: [name], context=CopyContext(item))
            declared.append(RemoteSourceSnapshot('rclone', 'rclone', source, (entry.name,), (entry.local,)))
    loaded = [source for source in declared
              if source.feature_name != 'rclone' or not hasattr(source.source.context, 'item')]
    groups = {}
    for source in declared:
        item = getattr(source.source.context, 'item', None) if source.feature_name == 'rclone' else None
        if item is None:
            continue
        if any(other.feature_name == 'rclone' and other.source.context is not None
               and Path(other.source.context) == item.context
               and session.package_path(item.context) == item.package for other in loaded):
            continue
        groups.setdefault((item.context, item.package), []).append(source)

    result = list(loaded)
    for (context, package), group in groups.items():
        names, folders, encrypted = set(), {}, set()
        for source in group:
            names.update(source.remote_names)
            encrypted.update(source.encrypted_remote_names)
            for folder in source.local_folders or ():
                if getattr(folder, 'private', False):
                    encrypted.add(folder.name)
                current = folders.get(folder.name)
                if current is None or getattr(current, 'private', False):
                    folders[folder.name] = folder
        unlocked = session.credentials(context) is not None and session.package_path(context) == package
        source = replace(group[0].source, name=f'{package.stem} ({"session" if unlocked else "locked"})')
        result.append(replace(group[0], source=source, remote_names=tuple(sorted(names)),
                              local_folders=tuple(folders.values()), encrypted_remote_names=frozenset(encrypted)))

    represented = {entry.local.path for source in declared if source.feature_name == 'rclone'
                   for entry in remote_entries(source, sources.local_folders) if entry.local is not None}
    unassociated = [entry.local for entry in local_entries(sources)
                    if local_entry_category(entry, sources) == 'Rclone' and entry.local.path not in represented]
    # Local/LocalCrypt copies can share a remote name; the online placeholder is one destination.
    folders = {folder.name: folder for folder in unassociated}
    if folders:
        names = tuple(sorted(folders))
        source = RemoteFolderSource('Credentials required', lambda: list(names), context=None)
        result.append(RemoteSourceSnapshot('rclone', 'rclone', source, names, tuple(folders.values())))
    return result
