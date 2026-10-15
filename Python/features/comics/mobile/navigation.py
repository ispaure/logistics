"""Portable native-reader spread loading and spread-aware page commands."""
from features.comics.reading import visible_pages
from .validation import image_dimensions


class ComicNavigation:
    def __init__(self, read_page, count, *, double_pages=(), right_to_left=False):
        self.read_page, self.count = read_page, count
        self.double_pages, self.right_to_left = set(double_pages), right_to_left
        self.sizes = {}
        self.visible = ()

    def load(self, start, *, viewport, mode='auto'):
        if mode not in {'single', 'auto', 'double'}:
            raise ValueError('Choose single, auto or double page layout.')
        if not 0 <= start < self.count:
            raise IndexError('Page does not exist.')
        # Mobile auto layout follows the actual reading pane, including split
        # screens and rotation, rather than the desktop fit-at-full-height rule.
        if mode == 'auto':
            mode = 'double' if viewport[0] > viewport[1] > 1 else 'single'
        data = {start: self.read_page(start)[0]}
        self.sizes[start] = image_dimensions(data[start])
        if (mode != 'single' and start + 1 < self.count
                and start not in self.double_pages and start + 1 not in self.double_pages
                and self.sizes[start][0] < self.sizes[start][1]):
            data[start + 1] = self.read_page(start + 1)[0]
            self.sizes[start + 1] = image_dimensions(data[start + 1])
        indices = visible_pages(start, self.sizes, viewport, mode, self.double_pages)
        # Commit only after every required page has loaded and validated.
        return indices, [data[index] for index in indices]

    def previous(self, start, *, viewport, mode='auto'):
        if start <= 0:
            return None
        if start >= 2 and mode != 'single':
            indices, _ = self.load(start - 2, viewport=viewport, mode=mode)
            if len(indices) == 2:
                return start - 2
        return start - 1

    def next(self, start):
        target = (self.visible[-1] + 1) if self.visible and self.visible[0] == start else start + 1
        return target if target < self.count else None


def provider_navigation(reader):
    """Adapt an injected provider reader without taking ownership of its source."""
    from features.comics.pages import double_page_indices
    try:
        double_pages = double_page_indices(reader.comic.info, len(reader.pages))
    except (OSError, ValueError, SyntaxError):
        double_pages = ()
    return ComicNavigation(lambda index: (reader.page(index)[1], 'image'), len(reader.pages), double_pages=double_pages,
                           right_to_left=getattr(reader, 'right_to_left', False))


def adjacent_comic(entries, current, direction):
    """Entries are (identity, display name), already filtered by host policy."""
    from features.comics.pages import natural_key
    ordered = sorted(entries, key=lambda item: natural_key(item[1]))
    index = next((i for i, item in enumerate(ordered) if item[0] == current), None)
    if index is None:
        return None
    target = index + (1 if direction > 0 else -1)
    return ordered[target][0] if 0 <= target < len(ordered) else None
