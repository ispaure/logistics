"""Books page and reusable reader: navigation/UI separated from EPUB storage."""
from commonUtils.ui.appearance.typography import point_size
from commonUtils.ui import pyside as qt
from math import isfinite
from features.books.ui.content import chapter_html
from features.books.epub import EPUBBook, BookError, resolve_href
from features.books.metadata import save_metadata
from features.books.ui.metadata_editor import MetadataEditor
from features.books.preferences import THEMES, ReadingState, defaults
from features.books.ui.bookmarks import Bookmarks
from features.books.ui.tasks import BookTask
from features.books.ui.reader_controls import build_controls
from features.books.ui.navigation import BookNavigation
from pathlib import Path
from services.documents.storage import DocumentPolicy, document_writable


class BooksPage(Bookmarks, qt.QWidget):
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
        self._rendered_colors = None
        self._closing = False
        build_controls(self)
        self.navigation = BookNavigation(self)
        self.save_timer = qt.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(600)
        self.save_timer.timeout.connect(self._save_state)
        self._set_busy(False)
        from commonUtils.ui.appearance.styling import styling
        styling().changed.connect(self._shared_settings_changed)
        from commonUtils.ui.settings.monitor import subscribe_settings
        from features.settings import settings_store
        store = settings_store(Path(__file__).parents[1] / 'config.ini')
        self._settings_subscription = subscribe_settings((store.defaults, store.personal), self._check_settings, self)
        if isinstance(initial_path, EPUBBook):
            self._loaded(initial_path)
        elif initial_path:
            self.open_book(initial_path)

    def choose_book(self):
        from services.documents.ui.readers import choose_reader_document
        return choose_reader_document(self.reader_window() or self, 'epub', current=self.book,
                                      open_local=None if self.private else self.open_book)

    @property
    def private(self):
        return self.book is not None and not DocumentPolicy.for_provider(self.book.source).persistent

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
        from commonUtils.ui.readers.reader_chrome import show_reader_popup
        if self.appearance.isVisible():
            self.appearance.hide()
            return
        self.appearance.adjustSize()
        show_reader_popup(self.appearance, self.appearance_button, align_right=True)

    def reading_font(self):
        # An empty shared family means Automatic. QFont('') can resolve to an
        # emoji font on macOS, whose space metrics stretch every word apart.
        font = qt.QFont(qt.QApplication.font())
        if self._settings['font_family'].strip():
            font.setFamily(self._settings['font_family'])
        font.setPointSizeF(point_size(self._settings['font_size']))
        return font

    def _save_appearance(self, key, value):
        from features.books.preferences import appearance_store, APPEARANCE_KEYS
        section, field = APPEARANCE_KEYS[key]
        try:
            appearance_store(key).save({(section, field): str(value)}, scope='personal')
        except (OSError, ValueError) as error:
            from desktop.notifications import notify
            notify('books', 'Could not save reading appearance', str(error), outcome='failure')
            self._settings_changed()
            return
        if key in ('font_family', 'font_size'):
            from commonUtils.ui.appearance.styling import styling
            styling().reload()
        self._check_settings()

    def _check_settings(self):
        if defaults() != self._settings:
            self._settings_changed()

    def _shared_settings_changed(self):
        if defaults() != self._settings:
            self._settings_changed()
            return
        if not self.book:
            return
        colors = THEMES[self.theme.currentData()]
        if self.theme.currentData() in ('dark', 'slate'):
            from commonUtils.ui.appearance.theme import configured_colors
            theme = configured_colors(True)
            colors = theme.surface, theme.text
        # Automatic reading fonts inherit UI typography. Slate/dark readers
        # adopt the shared tint; other shared preferences do not reimport EPUB.
        if (self.reading_font() != self.text.document().defaultFont()
                or colors != self._rendered_colors):
            self._appearance_changed()

    def _settings_changed(self):
        self._settings = defaults()
        for control in (self.font_family, self.font_size, self.theme, self.spacing, self.reading_width):
            control.blockSignals(True)
        self.font_family.setCurrentFont(self.reading_font())
        self.font_size.setValue(self._settings['font_size'])
        self.theme.setCurrentIndex(self.theme.findData(self._settings['theme']))
        self.spacing.setValue(self._settings['line_spacing'])
        self.reading_width.setValue(self._settings['reading_width'])
        for control in (self.font_family, self.font_size, self.theme, self.spacing, self.reading_width):
            control.blockSignals(False)
        self._appearance_changed()

    def toggle_fullscreen(self):
        self.fullscreen.toggle()

    def reader_window(self):
        from commonUtils.ui.document_host import document_owner
        return document_owner(self, BookWindow)

    def close_reader(self):
        if self.reader_window() is not None:
            from commonUtils.ui.document_host import close_document
            close_document(self.reader_window())
            return
        if self.worker:
            return
        self._save_state()
        self.book_progress.clear()
        self.book = self.text.book = self._state = None
        self._path = None
        self._bookmarks = []
        self.text.clear()
        self.chapters.clear()
        self._populate_bookmarks()
        self.title.setText('EPUB reader')
        self.status.setText('Open an EPUB to start reading.')
        self.progress_label.clear()
        self.book_progress.setEnabled(False)
        self.book_progress.fraction = 0
        self.book_progress.update()
        self.reading_area.setStyleSheet('')
        self._set_busy(False)

    def _set_busy(self, busy):
        self.open_button.setEnabled(not busy)
        self.menus.open_action.setEnabled(not busy)
        self.menus.recent.setEnabled(not busy and not self.private)
        read_only = not document_writable(getattr(self.book, 'source', None))
        self.menus.metadata_action.setVisible(not read_only)
        self.metadata_button.setVisible(not read_only)
        self.menus.metadata_action.setEnabled(self.book is not None and not busy and not read_only)
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
        self.metadata_button.setEnabled(enabled and not read_only)
        self.previous.setEnabled(enabled and (self._current > 0 or self.text.page_index > 0))
        self.next.setEnabled(enabled and (self.text.page_index + self.spread.step < self.text.page_count
                                         or self._current + 1 < len(self.book.spine if self.book else [])))
        self.remove_bookmark.setEnabled(enabled and bool(self._bookmarks))
        self.previous_action.setEnabled(enabled and self._current > 0)
        self.next_action.setEnabled(enabled and self._current + 1 < len(self.book.spine if self.book else []))
        self.previous_page_action.setEnabled(self.previous.isEnabled())
        self.next_page_action.setEnabled(self.next.isEnabled())
        self.text.setVisible(self.book is not None)
        self.empty_panel.setVisible(self.book is None)
        self.spread.update()

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
                    target = self.reader_window() or self
                    from commonUtils.ui.document_host import close_document
                    qt.QTimer.singleShot(0, target, lambda: close_document(target))
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
        self.title.setText(book.path.name)
        self.title.setToolTip(book.title)
        if self.reader_window() is not None:
            self.reader_window().setWindowTitle(('🕵️ Private - ' if self.private else '') + book.path.name)
            self.reader_window().setWindowFilePath(str(book.path))
        if not self.private:
            self._remember(book.path)
        self._state = None if self.private else ReadingState(book.path, folder=self._state_folder)
        state = self._state.load() if self._state and self._settings['remember'] else {}
        self._bookmarks = [item for item in state.get('bookmarks', [])[:50]
                           if isinstance(item, dict) and item.get('path') in book.spine
                           and isinstance(item.get('label'), str) and isinstance(item.get('position'), (int, float))
                           and isfinite(item['position'])]
        for control in (self.font_family, self.font_size, self.theme, self.spacing, self.reading_width):
            control.blockSignals(True)
        self.font_family.setCurrentFont(qt.QFont(self._settings['font_family']))
        size = self._settings['font_size']
        self.font_size.setValue(size if isinstance(size, int) else self._settings['font_size'])
        theme = self._settings['theme']
        self.theme.setCurrentIndex(self.theme.findData(theme) if theme in THEMES else 2)
        spacing = self._settings['line_spacing']
        self.spacing.setValue(spacing if isinstance(spacing, int) else self._settings['line_spacing'])
        width = self._settings['reading_width']
        self.reading_width.setValue(width if isinstance(width, int) else self._settings['reading_width'])
        for control in (self.font_family, self.font_size, self.theme, self.spacing, self.reading_width):
            control.blockSignals(False)
        self._populate_chapters()
        self.book_progress.set_book(book)
        self._populate_bookmarks()
        path = state.get('path')
        self._current = book.spine.index(path) if path in book.spine else 0
        self._render(position=state.get('position', 0), location=state.get('location'))
        self._set_busy(self.worker is not None)
        self.text.setFocus()

    def _populate_chapters(self):
        from commonUtils.ui.outline import OutlineEntry
        self.chapters.set_entries(OutlineEntry((chapter.path, chapter.fragment), chapter.label,
                                               chapter, chapter.depth)
                                  for chapter in self.book.chapters)
        self._chapter_items = self.chapters.items_by_id

    def _chapter_selected(self, item, column=0):
        if self.worker:
            return
        chapter = item.data(0, qt.Qt.ItemDataRole.UserRole)
        self.go_chapter(self.book.spine.index(chapter.path), fragment=chapter.fragment)

    def go_chapter(self, index, *, fragment=''):
        if not self.book or self.worker or not 0 <= index < len(self.book.spine):
            return
        self.speech.stop()
        previous = self._current
        self._current = index
        try:
            self._render(fragment=fragment, turn=index - previous)
        except (OSError, BookError) as error:
            self._current = previous
            self.status.setText(str(error))
        self._set_busy(False)

    def continue_speech(self):
        if self.speech.playback.duration and self.speech.playback.remaining <= 0:
            self.speech.message.setText('Timer finished · Play to start a new timer.')
            return
        if not self.book or self.worker or self._closing or self._current + 1 >= len(self.book.spine):
            if self.book and self._current + 1 == len(self.book.spine):
                self.speech.message.setText('Finished book.')
            return
        book, target = self.book, self._current + 1
        self.go_chapter(target)
        generation = self.speech.session.generation
        def resume():
            if (self.book is book and self._current == target and not self._loading
                    and not self._closing and self.speech.session.generation == generation):
                self.speech.start()
        qt.QTimer.singleShot(0, self, resume)

    def _position(self):
        bar = self.text.verticalScrollBar()
        return bar.value() / bar.maximum() if bar.maximum() else 0

    def turn_page(self, direction):
        if not self.book or self.worker or self._loading:
            return
        self.speech.stop()
        self.text._resize_anchor = None
        self.text.resize_settle.stop()
        target = self.text.page_index + direction * self.spread.step
        if 0 <= target < self.text.page_count:
            from services.documents.ui.page_transition import page_slide
            slide = page_slide(self.reading_area)
            slide.begin(direction)
            # QWidget.grab can make QTextEdit temporarily adopt an unpaged
            # backing layout. Restore pagination before committing the turn.
            self.text.repaginate()
            self.text.show_page(target)
            slide.finish()
            # Capturing the outgoing page can resize the text viewport and
            # queue another anchor. Subsequent layout must retain the page the
            # user just selected, rather than that capture-time position.
            self.text._resize_anchor = None
            self.text.resize_settle.stop()
        elif direction > 0 and self._current + 1 < len(self.book.spine):
            self.go_chapter(self._current + 1)
        elif direction < 0 and self._current > 0:
            self._current -= 1
            try:
                self._render(position=1, turn=-1)
            except (OSError, BookError) as error:
                self._current += 1
                self.status.setText(str(error))

    def seek_book(self, chapter, fraction):
        if self.book is not None and not self.worker and not self._loading:
            self._current = chapter
            try:
                self._render(position=fraction)
            except (OSError, BookError) as error:
                self.status.setText(str(error))

    def follow_speech(self, start, end):
        previous = self.text.read_pointer
        self.text.read_pointer = start if start >= 0 else None
        if start >= 0:
            self.text._resize_anchor = start
            self.text.show_location(start, center=True)
        elif previous is not None:
            self.text._resize_anchor = None
            self.text.show_location(previous)
        source = self.speech._highlight_widget
        tag = qt.QTextFormat.Property.UserProperty + 77
        for widget in (self.text, self.spread.second):
            if widget is not source:
                selections = [entry for entry in widget.extraSelections() if not entry.format.property(tag)]
                if source is not None:
                    selections += [entry for entry in source.extraSelections() if entry.format.property(tag)]
                widget.setExtraSelections(selections)

    def _render(self, *, position=0, fragment='', location=None, turn=0):
        if not self.book:
            return
        path = self.book.spine[self._current]
        background, foreground = THEMES[self.theme.currentData()]
        if self.theme.currentData() in ('dark', 'slate'):
            from commonUtils.ui.appearance.theme import configured_colors
            colors = configured_colors(True)
            background, foreground = colors.surface, colors.text
        self._rendered_colors = background, foreground
        self.reading_area.setStyleSheet(f'background-color: {background};')
        self.text.setMaximumWidth(self.reading_width.value())
        html = chapter_html(self.book, path, foreground=foreground, spacing=self.spacing.value())
        from services.documents.ui.page_transition import page_slide
        slide = page_slide(self.reading_area)
        slide.begin(turn)
        self._loading = True
        self.text._resize_anchor = location if isinstance(location, int) else 0
        self._render_revision += 1
        revision = self._render_revision
        base = qt.QUrl()
        base.setScheme('epub')
        base.setPath('/' + path)
        self.text.document().setBaseUrl(base)
        font = self.reading_font()
        family = font.family().replace('\\', '\\\\').replace('"', '\\"')
        self.text.setStyleSheet(f'QTextBrowser {{ background-color: {background}; color: {foreground}; '
                               f'font-family: "{family}"; font-size: {font.pointSizeF()}pt; border: none; padding: 24px; }}')
        self.text.ensurePolished()
        self.text.setFont(font)
        self.text.document().setDefaultFont(font)
        self.text.setHtml(html)
        self.spread.update()
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
            self.text._resize_anchor = None
            self.text.resize_settle.stop()
            self._position_changed()
            if turn:
                slide.finish()
        qt.QTimer.singleShot(0, self, restore)

    def _appearance_changed(self, *args):
        if self.book and not self.worker:
            try:
                self._render(location=self.text.read_pointer if self.text.read_pointer is not None else self.text.location())
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
            position = self.book_progress.update_position(self)
            label = position['mobile'] if self.width() < 900 else position['text']
            self.progress_label.setText(label)
            self.progress_label.setMinimumWidth(max(self.progress_label.fontMetrics().horizontalAdvance(line)
                                                    for line in label.splitlines()) + 4)
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
                                  chapter=self._current, chapters=len(self.book.spine)))
        except (OSError, ValueError) as error:
            self.status.setText(f'Reading position could not be saved: {error}')

    def edit_metadata(self):
        if not self.book or self.worker:
            return
        if not document_writable(self.book.source):
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
            self.title.setText(book.path.name)
            self.title.setToolTip(book.title)
            self._current = current
            self._render(location=location)
            self.status.setText(f'Metadata saved. Original backup: {backup.name}' if backup else 'Metadata saved.')
            if self.reader_window() is not None:
                self.reader_window().setWindowTitle(('🕵️ Private - ' if self.private else '') + book.path.name)
        self._run(lambda cancelled: save_metadata(self.book, changes, cancelled=cancelled), saved,
                  'Saving metadata…' if self.book.source is not None else 'Saving metadata and backing up the original…')

    def prepare_close(self):
        from commonUtils.ui.resources.picker import resource_tasks_pending
        self._closing = True
        self.book_progress.clear()
        if resource_tasks_pending(self.reader_window() or self):
            return False
        self.speech.stop()
        self._save_state()
        if self.worker is not None:
            self.worker.requestInterruption()
            return False
        return True


class BookWindow(qt.QMainWindow):
    document_editor_name = 'EPUB Reader'
    document_editor_id = 'epub'
    """Independent reader window retained by its browser controller."""
    idle = qt.Signal()

    def __init__(self, path, parent=None):
        super().__init__(parent, qt.Qt.WindowType.Window)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('EPUB reader')
        self.resize(1150, 850)
        self.setMinimumSize(640, 420)
        self.reader = BooksPage(self, initial_path=path, menu_bar=self.menuBar())
        self.workspace_controls = self.reader.workspace_controls
        self.setCentralWidget(self.reader)
        self.reader.idle.connect(self._finish_close)
        self.reader.idle.connect(self.idle)
        self._close_pending = False

    def _finish_close(self):
        if self._close_pending:
            from commonUtils.ui.document_host import close_document
            close_document(self)

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
