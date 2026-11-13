"""Desktop EPUB read-aloud following the book's chapter order."""

from commonUtils.runtime.speech import speech_word_starts
from commonUtils.ui import pyside as qt
from commonUtils.ui.readers.read_aloud import ReadAloud
from features.books.epub import BookError
from features.books.speech_sequence import ChapterSeek


class BookReadAloud(ReadAloud):
    def skip(self, seconds):
        page, session = self.owner, self.session
        if session is None or self._selected_passage or page.book is None:
            return super().skip(seconds)
        target = session.seek_position(seconds)
        if target is None:
            return
        seek = ChapterSeek(page._current, len(page.book.spine), target, session.words)
        try:
            while seek.index is not None:
                html, text = self._read_chapter(seek.index)
                seek.accept(speech_word_starts(text), (html, text))
        except (OSError, BookError):
            self.message.setText('Could not open this chapter. Try reopening the book.')
            return
        index, offset, prepared = seek.landing
        if prepared is None:
            session.seek_word(session.words.index(offset))
        else:
            self._play_chapter(index, offset, prepared, paused=session.state == 'paused')

    def advance(self):
        page, session = self.owner, self.session
        if self.playback.duration and self.playback.remaining <= 0:
            self.message.setText('Timer finished · Play to start a new timer.')
            return
        if page.book is None or page.worker or page._closing:
            return
        book, generation = page.book, session.generation
        current = page._current

        def next_chapter():
            if (page.book is not book or page._current != current or page._closing
                    or page.worker or session.generation != generation):
                return
            try:
                for index in range(current + 1, len(book.spine)):
                    html, text = self._read_chapter(index)
                    words = speech_word_starts(text)
                    if words:
                        self._play_chapter(index, words[0], (html, text))
                        return
            except (OSError, BookError):
                self.message.setText('Could not open the next chapter. Try reopening the book.')
                return
            self.message.setText('Finished book.')

        qt.QTimer.singleShot(0, page, next_chapter)

    def _read_chapter(self, index):
        page = self.owner
        html = page._chapter_html(index)
        document = qt.QTextDocument()
        document.setHtml(html)
        return html, document.toRawText().replace('\u2029', '\n').replace('\ufffc', ' ')

    def _play_chapter(self, index, offset, prepared, *, paused=False):
        page = self.owner
        html, text = prepared
        self.stop()
        page._show_chapter(index, location=offset, prepared_html=html)
        if page._current == index:
            self._source_base = 0
            self._highlight_widget = page.text
            self.play_passage(text, offset, paused=paused)

    def play_passage(self, text, start=0, **kwargs):
        # Qt represents inline images with a single UTF-16 object character.
        return super().play_passage(text.replace('\ufffc', ' '), start, **kwargs)
