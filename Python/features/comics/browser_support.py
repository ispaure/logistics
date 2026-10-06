"""Project-owned browser behavior contributed by CBZFile objects."""

from commonUtils.dirUtils import Directory
from commonUtils.filesystem import BrowserAction, BrowserPanel, BrowserDetails


def comic_targets(context):
    from .cbz import CBZFile
    return [item.path for item in context.selection if isinstance(item, (CBZFile, Directory))]


def directory_actions(item, context):
    if isinstance(item, Directory):
        return (BrowserAction('comics.edit_metadata', 'Edit Metadata',
                              lambda context: context.invoke('comics.edit_metadata', comic_targets(context))),)
    return ()


def folder_fields(item, stats):
    return (('Comics', f"{stats.extension_counts.get('cbz', 0):,}"),)


class ComicBrowserMixin:
    browser_has_thumbnail = True

    def browser_panels(self):
        return (BrowserPanel('comics.metadata', 'Comic Metadata', self._comic_details),)

    def _comic_details(self):
        from .pages import load_preview
        document, cover, error = load_preview(self.path)
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
        return ComicPages(self.path).cover(size)

    def browser_actions(self, context):
        return (BrowserAction('comics.edit_metadata', 'Edit Metadata',
                              lambda context: context.invoke('comics.edit_metadata', comic_targets(context))),)

    def browser_activate(self, context):
        context.invoke('comics.read', self.path)
        return True
