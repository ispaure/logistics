"""Bounded project search snapshots, including live open buffers."""
from bisect import bisect_right
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
import os
import re
from commonUtils.persistence.text import read_text_file
from commonUtils.ui.code_editor.search import find_matches


@dataclass(frozen=True)
class SearchHit:
    path: Path
    line: int
    column: int
    start: int
    length: int
    excerpt: str
    excerpt_start: int
    excerpt_end: int


@dataclass(frozen=True)
class SearchResult:
    hits: tuple
    files: int
    limited: bool


def search_files(roots, excluded, query, masks='', *, case=False, whole=False,
                 regex=False, buffers=None, cancelled=lambda: False, limit=500):
    if not query:
        return SearchResult((), 0, False)
    # Validate regex even when there are no eligible files.
    find_matches('', query, case=case, whole=whole, regex=regex, cancelled=cancelled)
    roots = tuple(Path(root).resolve() for root in roots)
    buffers = buffers or {}
    patterns = [mask.strip().casefold() for mask in re.split('[;,]', masks) if mask.strip()]
    paths, visited = [], set()
    limited = False
    entries = 0
    def excluded_path(relative):
        return (any(part in excluded for part in relative.parts)
                or any(relative.as_posix() == name
                       or relative.as_posix().startswith(name.rstrip('/') + '/')
                       for name in excluded))
    def eligible(path, root):
        relative = path.relative_to(root)
        return (not excluded_path(relative)
                and (not patterns or any(fnmatchcase(path.name.casefold(), pattern)
                     or fnmatchcase(relative.as_posix().casefold(), pattern) for pattern in patterns)))
    for root in roots:
        if not root.is_dir():
            raise ValueError(f'Search directory is unavailable: {root}')
        for directory, folders, files in os.walk(root, followlinks=False):
            if cancelled():
                return SearchResult((), 0, False)
            parent = Path(directory)
            folders[:] = sorted(name for name in folders if not (parent / name).is_symlink()
                                and not excluded_path((parent / name).relative_to(root)))
            entries += len(folders) + len(files)
            for name in sorted(files):
                path = parent / name
                if path not in visited and not path.is_symlink() and eligible(path, root):
                    paths.append(path); visited.add(path)
                if len(paths) >= 10000:
                    break
            if len(paths) >= 10000 or entries >= 100000:
                limited = True
                break
        if limited:
            break
    for path in buffers:
        path = Path(path)
        if path not in visited and any(path.is_relative_to(root) and eligible(path, root) for root in roots):
            if len(paths) >= 10000:
                limited = True
                break
            paths.append(path); visited.add(path)
    hits, matched_files = [], set()
    for path in paths:
        if cancelled():
            return SearchResult((), 0, False)
        try:
            if path in buffers:
                text = buffers[path]
                if len(text) > 1024 * 1024:
                    continue
            else:
                if path.stat().st_size > 1024 * 1024:
                    continue
                text = read_text_file(path).text
        except (OSError, ValueError):
            continue
        matches, capped = find_matches(text, query, case=case, whole=whole, regex=regex, cancelled=cancelled)
        lines = text.splitlines(keepends=True)
        starts = [0]
        for line in lines:
            starts.append(starts[-1] + len(line.encode('utf-16-le')) // 2)
        for match in matches:
            row = min(bisect_right(starts, match.start) - 1, len(lines))
            content = lines[row].rstrip('\r\n') if row < len(lines) else ''
            column = len(content.encode('utf-16-le')[:(match.start - starts[row]) * 2].decode('utf-16-le'))
            width = len(content.encode('utf-16-le')[(match.start - starts[row]) * 2:
                        (match.start - starts[row] + match.length) * 2].decode('utf-16-le'))
            left = max(0, column - 70)
            excerpt = content[left:left + 240]
            hits.append(SearchHit(path, row + 1, column, match.start, match.length,
                                  excerpt, column - left, min(len(excerpt), column - left + width)))
            matched_files.add(path)
            if len(hits) >= limit:
                return SearchResult(tuple(hits), len(matched_files), True)
        limited |= capped
    return SearchResult(tuple(hits), len(matched_files), limited)


def preview_text(path, buffer=None):
    if buffer is not None:
        return buffer
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Preview is limited to files up to 1 MiB.')
    return read_text_file(path).text
