"""Cache-first local filename search; private/virtual providers stay in RAM."""
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.search import SearchResult, search_resources


class LocalSearch:
    def __init__(self, database):
        from commonUtils.filesystem.index import DirectoryCache
        self.cache = DirectoryCache(database=database)

    @staticmethod
    def supports(provider):
        # Explicit adapters only: encrypted LocalFiles subclasses map names and
        # must never be enumerated through a physical filesystem index.
        from commonUtils.runtime.resources.local import LocalFiles
        from features.rclone.mobile.storage_location import CollectionFiles
        from .local_sources import SharedFiles
        return (type(provider) in (LocalFiles, CollectionFiles, SharedFiles)
                and not provider.private and not getattr(provider, 'session_only', False)
                and not getattr(provider, 'remote_storage', False))

    def prepare(self, provider, directory, *, cancelled):
        if not self.supports(provider):
            return
        folder = provider._locate(directory)
        from commonUtils.filesystem.local_access import check_local_path
        check_local_path(folder, recursive=True)
        with self.cache.get(folder, cancelled=cancelled, validate_files=False):
            check_cancelled(cancelled)
            provider._guard(folder)

    def search(self, provider, directory, query, *, cancelled=lambda: False, progress=None):
        if not self.supports(provider):
            return search_resources(provider, directory, query, cancelled=cancelled, progress=progress)
        directory = provider.relative(directory)
        folder = provider._locate(directory)
        from commonUtils.filesystem.local_access import check_local_path
        check_local_path(folder, recursive=True)
        snapshot = self.cache.peek(folder, cancelled=cancelled)
        if snapshot is None:
            snapshot = self.cache.get(folder, cancelled=cancelled, validate_files=False)
        with snapshot:
            rows, errors = [], [(str(path), error) for path, error in snapshot.errors]
            for entry in snapshot.search(query, cancelled=cancelled):
                check_cancelled(cancelled)
                if entry.symlink:
                    continue
                try:
                    # Recheck the provider boundary and revision before publishing
                    # a cached hit; saved names are never authority to open files.
                    path = entry.path.relative_to(provider.root).as_posix()
                    row = provider.entry(path)
                except FileNotFoundError:
                    continue
                except (OSError, ValueError) as error:
                    errors.append((str(entry.path), str(error)))
                    continue
                row['name'] = entry.path.relative_to(folder).as_posix()
                rows.append(row)
            provider._guard(folder)
            return SearchResult(rows, len(snapshot.entries), snapshot.complete and not errors, errors)
