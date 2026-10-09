"""Books page and reusable reader: navigation/UI separated from EPUB storage."""
from commonUtils.ui import pyside as qt
from math import isfinite
from .content import chapter_html
from .epub import EPUBBook, BookError, resolve_href
from .metadata import save_metadata
from .metadata_editor import MetadataEditor
from .preferences import THEMES, ReadingState, defaults
from .tasks import BookTask
from .reader_controls import build_controls
from .navigation import BookNavigation
from pathlib import Path


class BooksPage(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent=None, initial_path=None, *, state_folder=None, menu_bar=None):
        super().__init__(parent)
        self._external_menu_bar = menu_bar
        self.book = None
        self.worker = None
        self._state_folder = state_folder
        self._state = None
        self._bookmarks = []
        self._settings = defaults()
        self._current = 0
        self._path = None
        self._loading = False
        self._render_revision = 0
        self._closing = False
        build_controls(self)
        self.navigation = BookNavigation(self)
        self.save_timer = qt.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(600)
        self.save_timer.timeout.connect(self._save_state)
        self._set_busy(False)
        if initial_path:
            self.open_book(initial_path)

    def choose_book(self):
        directory = str(self.book.path.parent) if self.book else ''
        path, _ = qt.QFileDialog.getOpenFileName(self, 'Open EPUB', directory, 'EPUB books (*.epub *.EPUB)')
        if path:
            self.open_book(path)

    def show_find(self):
        self.find_panel.show()
        self.query.setFocus()
        self.query.selectAll()

    def hide_find(self):
        self.find_panel.hide()
        self.text.setFocus()

    def dismiss_overlay(self):
        if self.find_panel.isVisible():
            self.hide_find()
        else:
            self.fullscreen.leave()

    def go_to_page(self):
        if not self.book or self.worker or self._loading:
            return
        number, accepted = qt.QInputDialog.getInt(self, 'Go to page',
            f'Page in chapter {self._current + 1} (of {self.text.page_count}):',
            self.text.page_index + 1, 1, self.text.page_count)
        if accepted:
            self.text.show_page(number - 1)
            self.text.setFocus()

    def toggle_sidebar(self):
        self.sidebar.setVisible(self.sidebar_action.isChecked())

    def show_bookmarks(self):
        self.sidebar_action.setChecked(True)
        self.sidebar.show()
        self.sidebar.setCurrentIndex(1)

    def show_appearance(self):
        self.appearance.adjustSize()
        point = self.appearance_button.mapToGlobal(qt.QPoint(0, self.appearance_button.height()))
        screen = self.screen().availableGeometry()
        point.setX(max(screen.left(), min(point.x(), screen.right() - self.appearance.width())))
        point.setY(max(screen.top(), min(point.y(), screen.bottom() - self.appearance.height())))
        self.appearance.move(point)
        self.appearance.show()

    def toggle_fullscreen(self):
        self.fullscreen.toggle()

    def close_reader(self):
        if isinstance(self.window(), BookWindow):
            self.window().close()
            return
        if self.worker:
            return
        self._save_state()
        self.book = self.text.book = self._state = None
        self._path = None
        self._bookmarks = []
        self.text.clear()
        self.chapters.clear()
        self._populate_bookmarks()
        self.title.setText('EPUB reader')
        self.status.setText('Open an EPUB to start reading.')
        self.progress_label.clear()
        self.reading_area.setStyleSheet('')
        self._set_busy(False)

    def _set_busy(self, busy):
        self.open_button.setEnabled(not busy)
        self.menus.open_action.setEnabled(not busy)
        self.menus.recent.setEnabled(not busy)
        self.menus.metadata_action.setEnabled(self.book is not None and not busy)
        self.menus.find_action.setEnabled(self.book is not None and not busy)
        self.add_bookmark_action.setEnabled(self.book is not None and not busy)
        self.go_page_action.setEnabled(self.book is not None and not busy)
        self.appearance_action.setEnabled(self.book is not None and not busy)
        self.sidebar_action.setEnabled(self.book is not None)
        self.sidebar.setVisible(self.book is not None and self.sidebar_action.isChecked())
        self.empty_open.setEnabled(not busy)
        self.text.navigation_enabled = self.book is not None and not busy
        self.speech.action.setEnabled(self.text.navigation_enabled)
        for control in (self.font_family, self.font_size, self.theme, self.spacing, self.reading_width, self.query):
            control.setEnabled(not busy)
        enabled = self.book is not None and not busy
        for widget in (self.metadata_button, self.chapters, self.bookmark_button, self.bookmarks, self.remove_bookmark):
            widget.setEnabled(enabled)
        self.previous.setEnabled(enabled and (self._current > 0 or self.text.page_index > 0))
        self.next.setEnabled(enabled and (self.text.page_index + 1 < self.text.page_count
                                         or self._current + 1 < len(self.book.spine if self.book else [])))
        self.remove_bookmark.setEnabled(enabled and bool(self._bookmarks))
        self.previous_action.setEnabled(enabled and self._current > 0)
        self.next_action.setEnabled(enabled and self._current + 1 < len(self.book.spine if self.book else []))
        self.previous_page_action.setEnabled(self.previous.isEnabled())
        self.next_page_action.setEnabled(self.next.isEnabled())
        self.text.setVisible(self.book is not None)
        self.empty_panel.setVisible(self.book is None)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep enough text visible on compact windows, while allowing a wider
        # contents tree on desktop-sized readers. User splitter positions remain
        # intact within this responsive cap.
        self.sidebar.setMaximumWidth(max(170, min(420, round(self.width() * .3))))

    def _run(self, operation, done, message, *, failed=None):
        if self.worker is not None:
            return
        self.status.setText(message)
        self._set_busy(True)
        task = BookTask(operation, self)
        self.worker = task
        def finish():
            self.worker = None
            try:
                if task.error:
                    self.status.setText(task.error)
                    if failed is not None and not self._closing:
                        failed(task.error)
                elif not self._closing:
                    done(task.result)
            except Exception as error:
                self.status.setText(str(error))
            finally:
                self._set_busy(False)
                task.deleteLater()
                self.idle.emit()
                if self._closing:
                    target = self.window()
                    qt.QTimer.singleShot(0, target, target.close)
        task.finished.connect(finish)
        task.start()

    def open_book(self, path):
        if self.worker is not None:
            return
        self._save_state()
        self._closing = False
        if Path(path).suffix.lower() != '.epub':
            self.status.setText('This reader opens EPUB books. Open comics from File Browser in the comic reader.')
            return
        self._run(lambda cancelled: EPUBBook(path), self._loaded, 'Opening book…')

    def _remember(self, path):
        if self._state_folder is not None:
            self.menus.history.path = Path(self._state_folder) / 'recent.json'
        self.menus.remember(path)

    def _loaded(self, book):
        self.book = book
        self.text.book = book
        self.text.show()
        self.empty_panel.hide()
        self.title.setText(book.title)
        self.title.setToolTip(book.title)
        if isinstance(self.window(), BookWindow):
            self.window().setWindowTitle(book.title + ' — EPUB reader')
            self.window().setWindowFilePath(str(book.path))
        self._remember(book.path)
        self._state = ReadingState(book.path, folder=self._state_folder)
        state = self._state.load() if self._settings['remember'] else {}
        self._bookmarks = [item for item in state.get('bookmarks', [])[:50]
                           if isinstance(item, dict) and item.get('path') in book.spine
                           and isinstance(item.get('label'), str) and isinstance(item.get('position'), (int, float))
                           and isfinite(item['position'])]
        for control in (self.font_family, self.font_size, self.theme, self.spacing, self.reading_width):
            control.blockSignals(True)
        self.font_family.setCurrentFont(qt.QFont(str(state.get('font_family', self._settings['font_family']))))
        size = state.get('font_size', self._settings['font_size'])
        self.font_size.setValue(size if isinstance(size, int) else self._settings['font_size'])
        theme = state.get('theme', self._settings['theme'])
        self.theme.setCurrentIndex(self.theme.findData(theme) if theme in THEMES else 2)
        spacing = state.get('line_spacing', self._settings['line_spacing'])
        self.spacing.setValue(spacing if isinstance(spacing, int) else self._settings['line_spacing'])
        width = state.get('reading_width', self._settings['reading_width'])
        self.reading_width.setValue(width if isinstance(width, int) else self._settings['reading_width'])
        for control in (self.font_family, self.font_size, self.theme, self.spacing, self.reading_width):
            control.blockSignals(False)
        self._populate_chapters()
        self._populate_bookmarks()
        path = state.get('path')
        self._current = book.spine.index(path) if path in book.spine else 0
        self._render(position=state.get('position', 0), location=state.get('location'))
        self._set_busy(self.worker is not None)
        self.text.setFocus()

    def _populate_chapters(self):
        self.chapters.clear()
        self._chapter_items = {}
        parents = []
        for chapter in self.book.chapters:
            item = qt.QTreeWidgetItem([chapter.label])
            item.setToolTip(0, chapter.label)
            item.setData(0, qt.Qt.ItemDataRole.UserRole, chapter)
            self._chapter_items[(chapter.path, chapter.fragment)] = item
            depth = min(chapter.depth, len(parents))
            if depth:
                parents[depth - 1].addChild(item)
            else:
                self.chapters.addTopLevelItem(item)
            parents[depth:] = [item]
        self.chapters.expandAll()

    def _chapter_selected(self, item, column=0):
        if self.worker:
            return
        chapter = item.data(0, qt.Qt.ItemDataRole.UserRole)
        self.go_chapter(self.book.spine.index(chapter.path), fragment=chapter.fragment)

    def go_chapter(self, index, *, fragment=''):
        if not self.book or self.worker or not 0 <= index < len(self.book.spine):
            return
        previous = self._current
        self._current = index
        try:
            self._render(fragment=fragment)
        except (OSError, BookError) as error:
            self._current = previous
            self.status.setText(str(error))
        self._set_busy(False)

    def _position(self):
        bar = self.text.verticalScrollBar()
        return bar.value() / bar.maximum() if bar.maximum() else 0

    def turn_page(self, direction):
        if not self.book or self.worker or self._loading:
            return
        target = self.text.page_index + direction
        if 0 <= target < self.text.page_count:
            self.text.show_page(target)
        elif direction > 0 and self._current + 1 < len(self.book.spine):
            self.go_chapter(self._current + 1)
        elif direction < 0 and self._current > 0:
            self._current -= 1
            try:
                self._render(position=1)
            except (OSError, BookError) as error:
                self._current += 1
                self.status.setText(str(error))

    def _render(self, *, position=0, fragment='', location=None):
        if not self.book:
            return
        path = self.book.spine[self._current]
        background, foreground = THEMES[self.theme.currentData()]
        self.reading_area.setStyleSheet(f'background-color: {background};')
        self.text.setMaximumWidth(self.reading_width.value())
        html = chapter_html(self.book, path, foreground=foreground, spacing=self.spacing.value())
        self._loading = True
        self._render_revision += 1
        revision = self._render_revision
        base = qt.QUrl()
        base.setScheme('epub')
        base.setPath('/' + path)
        self.text.document().setBaseUrl(base)
        font = self.font_family.currentFont()
        font.setPointSize(self.font_size.value())
        family = font.family().replace('\\', '\\\\').replace('"', '\\"')
        self.text.setStyleSheet(f'QTextBrowser {{ background-color: {background}; color: {foreground}; '
                               f'font-family: "{family}"; font-size: {font.pointSize()}pt; border: none; padding: 24px; }}')
        self.text.ensurePolished()
        self.text.setFont(font)
        self.text.document().setDefaultFont(font)
        self.text.setHtml(html)
        self._path = path
        item = self._chapter_items.get((path, fragment))
        if item is None:
            item = next((item for (chapter_path, anchor), item in self._chapter_items.items() if chapter_path == path), None)
        if item is not None:
            self.chapters.setCurrentItem(item)
        chapter = next((entry.label for entry in self.book.chapters if entry.path == path and not entry.fragment), '')
        self.status.setText(f'Chapter {self._current + 1} of {len(self.book.spine)}' + (f' · {chapter}' if chapter else ''))
        def restore():
            if self._render_revision != revision:
                return
            self.text.repaginate()
            if fragment:
                self.text.scrollToAnchor(fragment)
                self.text.show_page(self.text.verticalScrollBar().value() // self.text.page_height)
            elif isinstance(location, int) and not isinstance(location, bool):
                self.text.show_location(location)
            elif isinstance(position, (int, float)) and isfinite(position):
                self.text.show_page(round(max(0, min(1, position)) * (self.text.page_count - 1)))
            self._loading = False
            self._position_changed()
        qt.QTimer.singleShot(0, self, restore)

    def _appearance_changed(self, *args):
        if self.book and not self.worker:
            try:
                self._render(location=self.text.location())
            except (OSError, BookError) as error:
                self.status.setText(str(error))

    def _link_clicked(self, url):
        if not self.book or self.worker:
            return
        try:
            if url.scheme() == 'epub':
                path, fragment = resolve_href('', url.path(qt.QUrl.ComponentFormattingOption.FullyEncoded).lstrip('/')
                                              + ('#' + url.fragment(qt.QUrl.ComponentFormattingOption.FullyEncoded) if url.fragment() else ''))
            else:
                path, fragment = resolve_href(self._path, url.toString())
            if path not in self.book.spine:
                raise BookError('This link is outside the book’s text chapters.')
            self.go_chapter(self.book.spine.index(path), fragment=fragment)
        except (OSError, BookError) as error:
            self.status.setText(str(error))

    def find_next(self):
        query = self.query.text().strip()
        if not query:
            return
        if self.text.find(query):
            self.text.show_location(self.text.textCursor().selectionStart())
            return
        cursor = self.text.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.Start)
        self.text.setTextCursor(cursor)
        if not self.text.find(query):
            self.status.setText('No match in this chapter. Search is case insensitive.')
        else:
            self.text.show_location(self.text.textCursor().selectionStart())

    def _position_changed(self, *args):
        if self.book:
            self.progress_label.setText(f'Page {self.text.page_index + 1} / {self.text.page_count}')
            self.progress_label.setMinimumWidth(self.progress_label.fontMetrics().horizontalAdvance(self.progress_label.text()) + 4)
            self.progress_label.setToolTip(f'Location {self._current + 1}:{self.text.location()} · '
                                          'Pages adapt to your font and window size; saved locations follow the text.')
            if not self._loading:
                self._set_busy(self.worker is not None)
        if self.book and not self._loading and not self.worker:
            self.save_timer.start()

    def _save_state(self):
        self.save_timer.stop()
        if not self._state or not self.book or not self._settings['remember']:
            return
        try:
            self._state.save(dict(path=self._path, position=self._position(), location=self.text.location(), bookmarks=self._bookmarks,
                                  theme=self.theme.currentData(), font_family=self.font_family.currentFont().family(),
                                  font_size=self.font_size.value(), line_spacing=self.spacing.value(), reading_width=self.reading_width.value()))
        except (OSError, ValueError) as error:
            self.status.setText(f'Reading position could not be saved: {error}')

    def _populate_bookmarks(self):
        self.bookmarks.clear()
        self.bookmark_list.clear()
        for item in self._bookmarks:
            self.bookmarks.addItem(item['label'])
            self.bookmark_list.addItem(item['label'])
            self.bookmark_list.item(self.bookmark_list.count() - 1).setToolTip(item['label'])
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

    def edit_metadata(self):
        if not self.book or self.worker:
            return
        dialog = MetadataEditor(self.book, self)
        try:
            if dialog.exec() != qt.QDialog.DialogCode.Accepted:
                return
            changes = dialog.changes()
        finally:
            dialog.deleteLater()
        if not changes:
            return
        current, location = self._current, self.text.location()
        def saved(result):
            book, backup = result
            self.book = self.text.book = book
            self.title.setText(book.title)
            self.title.setToolTip(book.title)
            self._current = current
            self._render(location=location)
            self.status.setText(f'Metadata saved. Original backup: {backup.name}')
        self._run(lambda cancelled: save_metadata(self.book, changes, cancelled=cancelled), saved, 'Saving metadata and backing up the original…')

    def prepare_close(self):
        self.speech.stop()
        self._closing = True
        self._save_state()
        if self.worker is not None:
            self.worker.requestInterruption()
            return False
        return True


class BookWindow(qt.QMainWindow):
    """Independent reader window retained by its browser controller."""
    def __init__(self, path, parent=None):
        super().__init__(parent, qt.Qt.WindowType.Window)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('EPUB reader')
        self.resize(1150, 850)
        self.setMinimumSize(640, 420)
        self.reader = BooksPage(self, initial_path=path, menu_bar=self.menuBar())
        self.setCentralWidget(self.reader)
        self.reader.idle.connect(self._finish_close)
        self._close_pending = False

    def _finish_close(self):
        if self._close_pending:
            self.close()

    def prepare_close(self):
        return self.reader.prepare_close()

    def closeEvent(self, event):
        if self.reader.prepare_close():
            event.accept()
        else:
            self._close_pending = True
            event.ignore()

    def reject(self):
        self.close()
