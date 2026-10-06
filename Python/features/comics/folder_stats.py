"""Background folder totals using filesystem stats, without reading archive data."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass
class FolderStats:
    size: int = 0
    files: int = 0
    comics: int = 0
    folders: int = 0
    skipped: int = 0

    def include(self, other):
        self.size += other.size
        self.files += other.files
        self.comics += other.comics
        self.folders += other.folders + 1
        self.skipped += other.skipped


def scan_folders(root, cancelled=lambda: False):
    """Aggregate bottom-up. Links are skipped to avoid cycles/double counting."""
    totals = {}
    children = {}
    stack = [(Path(root), False)]
    while stack:
        if cancelled():
            return None
        folder, visited = stack.pop()
        if visited:
            stats = totals[folder]
            for child in children[folder]:
                stats.include(totals[child])
            continue
        stats = totals[folder] = FolderStats()
        children[folder] = []
        stack.append((folder, True))
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if cancelled():
                        return None
                    try:
                        if entry.is_symlink():
                            stats.skipped += 1
                        elif entry.is_dir(follow_symlinks=False):
                            child = Path(entry.path)
                            children[folder].append(child)
                            stack.append((child, False))
                        elif entry.is_file(follow_symlinks=False):
                            stats.size += entry.stat(follow_symlinks=False).st_size
                            stats.files += 1
                            stats.comics += Path(entry.name).suffix.lower() == '.cbz'
                    except OSError:
                        stats.skipped += 1
        except OSError:
            stats.skipped += 1
    return totals


def format_size(size):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:,} B' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
