"""Project text search borrows the ordinary browser's saved directory listings."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.search.files import search_files as _search_files
from features.ide.projects import is_excluded
from services.directory_index import cache_for


def search_files(roots, excluded, query, masks='', *, project_root=None, excluded_patterns=(), **kwargs):
    def exclude_path(path, search_root):
        base = project_root if project_root is not None and path.is_relative_to(project_root) else search_root
        return is_excluded(path.relative_to(base), excluded, excluded_patterns)

    with cache_for() as cache:
        return _search_files(roots, (), query, masks, cache=cache, exclude_path=exclude_path, **kwargs)
