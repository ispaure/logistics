"""Project text search borrows the ordinary browser's saved directory listings."""
from commonUtils.search.files import search_files as _search_files
from features.ide.projects import is_excluded
from services.directory_index import cache_for


def search_files(roots, excluded, query, masks='', *, project_root=None, excluded_patterns=(), **kwargs):
    def exclude_path(path, search_root):
        base = project_root if project_root is not None and path.is_relative_to(project_root) else search_root
        return is_excluded(path.relative_to(base), excluded, excluded_patterns)

    with cache_for() as cache:
        return _search_files(roots, (), query, masks, cache=cache, exclude_path=exclude_path, **kwargs)
