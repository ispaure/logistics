"""Project-owned browser behavior contributed by CBZFile objects."""

from commonUtils.filesystem import BrowserPanel, BrowserDetails
from commonUtils.archives.zip_access import ArchivePasswordError
from features.comics.locked_preview import locked_preview


def folder_fields(item, stats):
    return (('Comics', f"{stats.extension_counts.get('cbz', 0):,}"),)


class ComicBrowserMixin:
    browser_has_thumbnail = True

    def browser_panels(self):
        return (BrowserPanel('comics.metadata', 'Comic Metadata', self._comic_details),)

    def _comic_details(self):
        from .pages import load_preview
        try:
            document, cover, error = load_preview(self.path)
        except ArchivePasswordError:
            return BrowserDetails((('Archive', 'Locked'),), locked_preview((360, 500)),
                                  'Encrypted comic. Open the reader or Edit Metadata to enter its password.')
        values = []
        for field, label in (('Series', 'Series'), ('Writer', 'Author'), ('Volume', 'Volume'),
                             ('Number', 'Issue'), ('Count', 'Issues'), ('Title', 'Title'),
                             ('Publisher', 'Publisher'), ('Year', 'Year'), ('Summary', 'Description')):
            try:
                value = document.info.get_field(field)
            except ValueError:
                value = ''
            if value:
                values.append((label, value))
        return BrowserDetails(tuple(values), cover, error, document)

    def browser_thumbnail(self, size):
        from .pages import ComicPages
        try:
            return ComicPages(self.path).cover(size)
        except ArchivePasswordError:
            return locked_preview(size)
