"""Desktop source categories without losing provider-owned action contexts."""
from pathlib import Path

from services.folders.entries import get_folder_entries


SOURCE_NAMES = ('Local', 'Cloud', 'Home Server')


def source_category(source):
    """Use mobile's explicit network-share package convention, not protocol guesses."""
    if source.feature_name != 'rclone':
        return 'Cloud'
    context = source.source.context
    item = getattr(context, 'item', None)
    path = item.package if item else context
    if path is not None and Path(path).stem.casefold() in {'network shares', 'session network shares'}:
        return 'Home Server'
    return 'Cloud'


def remote_entries(source, local_folders):
    return get_folder_entries(source.remote_names, remote_source=source.feature_name,
        remote_context=source.source.context, include_local_only=False,
        local_folders=source.local_folders if source.local_folders is not None else local_folders)


def local_entries(sources):
    """Merge by physical copy, preferring entries carrying loaded sync context."""
    entries = {}
    for source in sorted(sources.remote_sources, key=lambda source: hasattr(source.source.context, 'item')):
        for entry in remote_entries(source, sources.local_folders):
            if entry.local is not None:
                entries.setdefault(entry.local.path, entry)
    folders = [*sources.local_folders,
               *(folder for source in sources.local_sources for folder in source.folders),
               *(folder for source in sources.remote_sources for folder in source.local_folders or ())]
    for entry in get_folder_entries(local_folders=folders):
        entries.setdefault(entry.local.path, entry)
    return list(entries.values())


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
