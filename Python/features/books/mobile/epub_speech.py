"""Play and seek ordered chapters through the same native speech panel."""

from collections import deque

from commonUtils.runtime.speech import speech_word_starts
from features.books.speech_sequence import ChapterSeek
from .speech_view import ReadAloudPanel


class EpubReadAloudPanel(ReadAloudPanel):
    def __init__(self, *, location, read_chapter, show_chapter, can_read=lambda: True, **kwargs):
        self.location, self.read_chapter, self.show_chapter = location, read_chapter, show_chapter
        self.can_read = can_read
        self.pending_skips = deque()
        self.movement = None
        self.blocked = False
        self.publishing = False
        super().__init__(seek=self.seek_chapters, **kwargs)
        self.session.on_exhausted = self.advance

    def _moving(self):
        return self.movement is not None and not self.movement.done()

    def _cancel_movement(self):
        if self._moving():
            self.movement.cancel()
            self.movement = None
        self.pending_skips.clear()

    def stop_playback(self, widget=None, **kwargs):
        self._cancel_movement()
        self.publishing = False
        self.blocked = False
        super().stop_playback(widget, **kwargs)

    def pause_playback(self):
        was_advancing = self._moving() and self.session.state == 'speaking'
        self._cancel_movement()
        if self.publishing or was_advancing:
            self.blocked = was_advancing and not self.publishing
            self.publishing = False
            self.session.stop()
        else:
            super().pause_playback()

    def change_speed(self, widget=None, **kwargs):
        if self._moving():
            self.pause_playback()
        super().change_speed(widget, **kwargs)

    def resume_playback(self, *, explicit=True):
        if self._moving():
            return
        super().resume_playback(explicit=explicit)

    async def play(self, widget=None, **kwargs):
        if self._moving():
            return
        if self.blocked and not self.closed:
            if not self.can_read():
                self.set_status('Unlock and return to the book to continue.')
                return
            if self.playback is None or self.playback.request_start():
                self.blocked = False
                self.advance()
            return
        await super().play(widget, **kwargs)

    def seek_chapters(self, seconds):
        if self.playback is not None and not self.playback.can_start():
            return
        if not self.continue_book:
            return self.session.skip(seconds)
        if self._moving():
            self.pending_skips.append(seconds)
            return self.movement
        target = self.session.seek_position(seconds)
        if target is None:
            return
        index, count = self.location()
        seek = ChapterSeek(index, count, target, self.session.words)
        if seek.index is None:
            self.session.seek_word(self.session.words.index(seek.landing[1]))
            return
        if not self.can_read():
            self.set_status('Unlock and return to the book to skip between chapters.')
            return
        paused = self.session.state == 'paused'
        # Freeze the old utterance and position while chapter reads are pending.
        self.session.pause()
        return self._schedule(self._seek(seek, paused))

    def _schedule(self, coroutine):
        task = self.movement = self.speech_loop.create_task(coroutine)
        task.add_done_callback(self._movement_done)
        return task

    def _guard(self):
        session, generation = self.session, self.session.generation
        return lambda: (not self.closed and self.session is session
                        and session.generation == generation
                        and (self.playback is None or self.playback.can_start()))

    async def _seek(self, seek, paused):
        current = self._guard()
        original = self.location()[0]
        try:
            while seek.index is not None:
                if not current() or not self.can_read():
                    if current():
                        self.set_status('Unlock and return to the book to skip between chapters.')
                    return
                prepared = await self.read_chapter(seek.index, current)
                if not current() or not self.can_read():
                    return
                chapter = prepared[1]
                seek.accept(speech_word_starts(chapter.text, chapter.breaks), prepared)
            index, offset, prepared = seek.landing
            if prepared is None:
                self.session.seek_word(self.session.words.index(offset))
                if not paused:
                    self.session.resume()
            else:
                await self._land(index, offset, prepared, current, paused=paused)
        except PermissionError:
            if current():
                self.set_status('Unlock and return to the book to skip between chapters.')
        except Exception:
            if current():
                if self.location()[0] != original:
                    self.session.stop()
                self.set_status('Could not open this chapter. Try reopening the book.')

    def advance(self):
        if self.closed or not self.continue_book:
            return False
        if self.playback is not None and not self.playback.can_start():
            return False
        if not self._moving():
            self.continuation_task = self._schedule(self._advance())
        return True

    async def _advance(self):
        session, generation = self.session, self.session.generation
        current = self._guard()
        try:
            index, count = self.location()
            for candidate in range(index + 1, count):
                if not current():
                    return
                if self.timer.duration and self.timer.remaining <= 0:
                    self._stop_at_boundary()
                    self.set_status('Timer finished · Play to start a new timer.')
                    return
                if not self.can_read():
                    self._stop_at_boundary()
                    return
                prepared = await self.read_chapter(candidate, current)
                if not current():
                    return
                if not self.can_read():
                    self._stop_at_boundary()
                    return
                chapter = prepared[1]
                words = speech_word_starts(chapter.text, chapter.breaks)
                if words:
                    if not await self._land(candidate, words[0], prepared, current):
                        if current():
                            message = self.status.text
                            self.session.stop()
                            self.set_status(message)
                    return
            else:
                if current():
                    self.session.stop()
                    self.set_status('Finished book.')
        except PermissionError:
            if current():
                self._stop_at_boundary()
        except Exception:
            if current():
                self.session.stop()
                self.set_status('Could not open the next chapter. Try reopening the book.')
        finally:
            if (not self.closed and self.session is session and session.generation == generation
                    and session.state == 'speaking' and not current()):
                self._stop_at_boundary()

    def _movement_done(self, task):
        if self.movement is not task:
            return
        self.movement = None
        self.publishing = False
        if (self.session.state not in ('speaking', 'paused')
                or (self.playback is not None and not self.playback.can_start())):
            self.pending_skips.clear()
            return
        while self.pending_skips and not self.closed:
            if self.seek_chapters(self.pending_skips.popleft()) is not None:
                break

    def _stop_at_boundary(self):
        self.session.stop()
        self.blocked = True
        self.set_status('Unlock and return to the book to continue.')

    async def _land(self, index, offset, prepared, current, *, paused=False):
        # After publication the old session must never resume against the new chapter.
        self.publishing = True
        shown = await self.show_chapter(self, index, offset, prepared, current)
        if not current():
            return False
        if not self.can_read():
            self.session.stop()
            self.blocked = self.location()[0] != index
            self.set_status('Unlock and return to the book to continue.')
            return False
        if not shown:
            if self.location()[0] == index:
                self.session.stop()
            self.set_status('Could not show this chapter. Try reopening the book.')
            return False
        if self.timer.duration and self.timer.remaining <= 0:
            paused = True
        result = await self.play_passage(prepared[1], offset, paused=paused, valid=lambda: current() and self.can_read())
        if not result and not self.closed and self.location()[0] == index:
            if not current():
                # Interruption and manual retirement already end their own sessions.
                if self.session.state in ('speaking', 'paused'):
                    self.session.stop()
                return False
            if not self.can_read():
                self.set_status('Unlock and return to the book to continue.')
            message = self.status.text
            self.session.stop()
            self.set_status(message)
        return result

    def dispose(self):
        self._cancel_movement()
        super().dispose()
        self.location = self.read_chapter = self.show_chapter = self.can_read = None
