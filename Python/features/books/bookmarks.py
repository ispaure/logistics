"""Reader bookmark commands; location interpretation and state stay with EPUB."""
from commonUtils.ui import pyside as qt
from .epub import BookError


class Bookmarks:
    def _populate_bookmarks(self):
        self.bookmarks.clear()
        from commonUtils.ui.outline import OutlineEntry
        self.bookmark_list.set_entries(OutlineEntry(index, item['label'], item)
                                      for index, item in enumerate(self._bookmarks))
        for item in self._bookmarks:
            self.bookmarks.addItem(item['label'])
        self.remove_bookmark.setEnabled(bool(self._bookmarks) and self.worker is None)

    def add_bookmark(self):
        if not self.book or self.worker:
            return
        if len(self._bookmarks) >= 50:
            self.status.setText('This book has 50 bookmarks. Remove one to add another.')
            return
        label, accepted = qt.QInputDialog.getText(self, 'Bookmark', 'Name:', text=f'Chapter {self._current + 1}')
        if accepted and label.strip():
            self._bookmarks.append(dict(label=label.strip(), path=self._path, position=self._position(), location=self.text.location()))
            self._populate_bookmarks()
            self._save_state()

    def open_bookmark(self, index):
        if self.worker or not 0 <= index < len(self._bookmarks):
            return
        item = self._bookmarks[index]
        self._current = self.book.spine.index(item['path'])
        try:
            self._render(position=item['position'], location=item.get('location'))
        except (OSError, BookError) as error:
            self.status.setText(str(error))
        self._set_busy(False)

    def delete_bookmark(self):
        index = self.bookmark_list.currentRow()
        if index < 0:
            index = self.bookmarks.currentIndex()
        if 0 <= index < len(self._bookmarks):
            del self._bookmarks[index]
            self._populate_bookmarks()
            self._save_state()

