"""Logistics admission policy for shared cache-backed local search."""
from commonUtils.runtime.resources.indexed_search import IndexedLocalSearch


class LocalSearch(IndexedLocalSearch):
    def __init__(self, database):
        super().__init__(database, eligible=self.eligible_provider)

    @staticmethod
    def eligible_provider(provider):
        # Explicit adapters only: encrypted LocalFiles subclasses map names and
        # must never be enumerated through a physical filesystem index.
        from commonUtils.runtime.resources.local import LocalFiles
        from features.rclone.mobile.storage_location import CollectionFiles
        from .local_sources import SharedFiles
        return (type(provider) in (LocalFiles, CollectionFiles, SharedFiles)
                and not provider.private and not getattr(provider, 'session_only', False)
                and not getattr(provider, 'remote_storage', False))
