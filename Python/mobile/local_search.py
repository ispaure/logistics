"""Logistics admission policy for shared cache-backed local search."""
from commonUtils.search.indexed import IndexedLocalSearch


class LocalSearch(IndexedLocalSearch):
    def __init__(self, database):
        super().__init__(database, eligible=self.eligible_provider)

    def search(self, provider, directory, query, **kwargs):
        indexed = getattr(provider, 'indexed_list', None)
        if indexed is not None:
            from commonUtils.search.providers import search_resources
            return search_resources(provider, directory, query, list_children=indexed, **kwargs)
        return super().search(provider, directory, query, **kwargs)

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
