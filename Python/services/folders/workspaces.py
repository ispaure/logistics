"""Desktop source categories without losing provider-owned action contexts."""

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
    """Cloud destinations come from live credential sources, never local copies."""
    result = []
    for source in sources.remote_sources:
        if source.feature_name == 'rclone':
            context = source.source.context
            if context is None or hasattr(context, 'item'):
                continue
        result.append(source)
    return result
