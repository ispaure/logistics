"""Feature-owned EPUB type; browser activation is supplied by Books."""
from commonUtils.filesystem.files import File


class EPUBFile(File):
    """An EPUB archive, with metadata read lazily by the Books feature."""
    def open_book(self):
        from .epub import EPUBBook
        return EPUBBook(self.path)

    browser_has_thumbnail = True

    def browser_panels(self):
        from commonUtils.filesystem import BrowserPanel
        return (BrowserPanel('books.metadata', 'Book Metadata', self._book_details),)

    def _book_details(self):
        from commonUtils.filesystem import BrowserDetails
        from .preview import cover_thumbnail
        book = self.open_book()
        fields = [('Title', book.title)]
        for key, label in (('creator', 'Author'), ('language', 'Language'), ('publisher', 'Publisher'),
                           ('date', 'Published'), ('subject', 'Tags'), ('description', 'Description')):
            values = book.values(key)
            if values:
                fields.append((label, '\n'.join(values)))
        cover, message = cover_thumbnail(book, (960, 1320))
        return BrowserDetails(tuple(fields), cover, message)

    def browser_thumbnail(self, size):
        from .preview import cover_thumbnail
        return cover_thumbnail(self.open_book(), size)[0]
