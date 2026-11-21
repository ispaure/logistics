"""Logistics admission policy for shared cache-backed local search."""
from commonUtils.search.indexed import IndexedLocalSearch
from commonUtils.search.providers import search_resources


class LocalSearch(IndexedLocalSearch):
    def __init__(self, database):
        super().__init__(database, eligible=self.eligible_provider)
        from services.directory_index import coordinator_for
        self.cache.coordinator = coordinator_for(self.cache.database)

    def prepare(self, provider, directory, *, cancelled):
        if not self.supports(provider):
            return
        from services.directory_index import foreground
        with foreground(self.cache.database, provider._locate(directory)):
            return super().prepare(provider, directory, cancelled=cancelled)

    def search(self, provider, directory, query, **kwargs):
        indexed = getattr(provider, 'search_listing', None) or getattr(provider, 'indexed_list', None)
        if indexed is not None:
            return search_resources(provider, directory, query, list_children=indexed, **kwargs)
        if not self.supports(provider):
            return super().search(provider, directory, query, **kwargs)
        from services.directory_index import foreground
        with foreground(self.cache.database, provider._locate(directory)):
            kwargs.setdefault('cached_progress', True)
            from .local_sources import SharedFiles
            # SharedFiles admits managed subfolders through its own listing rules.
            if kwargs.get('progress') is not None and type(provider) is not SharedFiles:
                kwargs.setdefault('cold_search', self._search_without_snapshot)
            return super().search(provider, directory, query, **kwargs)

    def _search_without_snapshot(self, provider, directory, query, *, cancelled, progress):
        from commonUtils.filesystem.index.exclusions import scan_exclusions
        from commonUtils.filesystem.local_access import check_local_path

        root = provider._locate(directory)
        check_local_path(root, recursive=True)
        excluded = {path.relative_to(provider.root).as_posix()
                    for path in scan_exclusions(root, self.cache.database)}

        def names(folder, *, cancelled):
            if folder in excluded:
                return ()
            return (row for row in provider.list_names(folder, cancelled=cancelled)
                    if row['path'] not in excluded)

        try:
            result = search_resources(provider, directory, query, cancelled=cancelled, progress=progress,
                                      list_children=names, load_match=provider.entry)
            provider._guard(root)
            return result
        except ValueError:
            # The filesystem index can skip individual unsupported links and
            # special files when the rooted listing would reject the folder.
            return self._search(provider, directory, query, cancelled=cancelled, progress=progress)

    @staticmethod
    def eligible_provider(provider):
        # Explicit adapters only: encrypted LocalFiles subclasses map names and
        # must never be enumerated through a physical filesystem index.
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.locations import CollectionFiles
        from .local_sources import SharedFiles
        return (type(provider) in (LocalFiles, CollectionFiles, SharedFiles)
                and not provider.private and not getattr(provider, 'session_only', False)
                and not getattr(provider, 'remote_storage', False))
