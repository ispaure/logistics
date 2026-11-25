"""List and file-menu access to the same checkpoints the native readers use."""

import asyncio
from collections import OrderedDict
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from functools import partial
from itertools import accumulate
from pathlib import Path
from threading import Lock
from typing import Callable
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from features.books.locations import MAX_OFFSET, TEXT_PROGRESS_METHOD, text_completion
from services.documents.completion import page_percent, video_percent

_READ_ERRORS = (OSError, ValueError, KeyError, RuntimeError, BadZipFile, ParseError)
_text_starts = OrderedDict()
_text_lock = Lock()


def _book_text_starts(book, state):
    from features.books.locations import ChapterText
    from features.books.mobile.content import chapter_html

    key = ((state.root, state.identity, state.revision, tuple(book.spine))
           if state.mode == 'local' else None)
    if key is not None:
        with _text_lock:
            if key in _text_starts:
                _text_starts.move_to_end(key)
                return _text_starts[key]
    # Typography and link routing only change markup, not the reader's text.
    lengths = (ChapterText(chapter_html(book, index)).length for index in range(len(book.spine)))
    starts = tuple(accumulate(lengths, initial=0))
    if key is not None:
        with _text_lock:
            _text_starts[key] = starts
            if len(_text_starts) > 16:
                _text_starts.popitem(last=False)
    return starts


def tracked_kind(path, kind=None):
    from features.video.formats import VIDEO_EXTENSIONS
    suffix = Path(path).suffix.lower()
    if suffix in VIDEO_EXTENSIONS or kind == 'video':
        return 'video'
    if suffix in {'.epub', '.cbz', '.pdf'}:
        return suffix
    if suffix == '.zip' and kind == 'comic':
        return '.zip'
    return None


@dataclass
class ReadingCompletion:
    state: object
    count: int
    names: tuple = ()
    book: object = None

    def percentage(self):
        saved = self.state.load()
        if self.state.load_status in {'locked', 'error', 'fenced'}:
            return None
        percent = saved.get('percent')
        if (type(percent) is int and 0 <= percent <= 100
                and (self.book is None or saved.get('percent_method') == TEXT_PROGRESS_METHOD)):
            return percent
        page = saved.get('page', 0)
        resource = saved.get('resource')
        if resource in self.names and (type(page) is not int or not 0 <= page < self.count
                                       or self.names[page] != resource):
            page = self.names.index(resource)
        if self.book is None:
            return page_percent(page, self.count)
        if type(page) is not int or not 0 <= page < self.count:
            return 0
        offset = saved.get('offset', 0)
        offset = offset if type(offset) is int else 0
        if not page and offset <= 0:
            return 0
        # The earlier chapter-based calculation could only produce 100 at the end.
        if page == self.count - 1 and (percent == 100 or offset == MAX_OFFSET):
            return 100
        return text_completion(_book_text_starts(self.book, self.state), page, offset)

    def mark(self, read):
        self.state.load()
        if self.state.load_status in {'locked', 'error', 'fenced'}:
            return self.state.load_status
        page = self.count - 1 if read else 0
        value = dict(page=page, percent=100 if read else 0)
        if self.names:
            value['resource'] = self.names[page]
            if self.book is not None:
                # The EPUB layout bounds the anchor to the final rendered page.
                value.update(offset=MAX_OFFSET if read else 0, percent_method=TEXT_PROGRESS_METHOD)
            else:
                value['half'] = int(read)
        return self.state.save(value)


@dataclass(frozen=True)
class VideoCompletion:
    video: object

    @property
    def state(self):
        return self.video.state

    def percentage(self):
        if self.state.load_status in {'locked', 'error', 'fenced'}:
            return None
        return video_percent(self.video.record())

    def mark(self, read):
        return self.video.mark(read)


@contextmanager
def item_progress(app, item, kind):
    with ExitStack() as stack:
        item.validate()
        if kind == 'video':
            from features.video.playback import VideoContent
            from services.documents.video_progress import VideoProgress
            from services.documents.video_state import MobileCipher
            video = VideoContent(item.provider, item.path)
            stack.callback(video.close)
            progress = VideoProgress(video, Path(app.private_root) / 'Video',
                                     remote_cipher=MobileCipher(app), app=app)
            stack.callback(progress.retire)
            progress.load()
            yield VideoCompletion(progress)
            return
        from services.documents.provider_documents import ProviderDocuments
        from .provider_progress import open_provider_progress
        copies = ProviderDocuments(item.provider)
        reader = copies.open(item.path)
        stack.callback(reader.source.close)
        progress = open_provider_progress(app, copies, reader, item.path, check=reader.source.check)
        stack.callback(progress.retire)
        names = reader.book.spine if reader.book is not None else getattr(reader, 'pages', ())
        yield ReadingCompletion(progress, len(reader.labels), tuple(names), reader.book)


@contextmanager
def reference_progress(app, source, kind):
    from .file_items import _resolve_reference
    item, close = _resolve_reference(app, source)
    try:
        with item_progress(app, item, kind) as progress:
            yield progress
    finally:
        close()


@contextmanager
def imported_progress(app, store, key):
    _, reader, state, _ = store.open_reading(key, app=app)
    try:
        book = reader if hasattr(reader, 'spine') else None
        names = tuple(book.spine if book is not None else reader.pages)
        yield ReadingCompletion(state, len(names), names, book)
    finally:
        state.retire()
        source = getattr(getattr(reader, 'document', None), 'source', None)
        if hasattr(source, 'close'):
            source.close()


@dataclass(frozen=True)
class CompletionTarget:
    kind: str
    open_progress: Callable

    def __call__(self):
        return self.open_progress()


def reference_target(app, source, kind=None):
    if source is None:
        return None
    if source['type'] == 'session' and source.get('provider') == 'library':
        store = app.reader_manager().catalog.library_store
        return CompletionTarget('library', partial(imported_progress, app, store, source['resource']))
    if source['type'] not in {'local', 'remote', 'crypt', 'download'}:
        return None
    name = source.get('path') or source.get('key') or ''
    if tracked := tracked_kind(name, kind):
        return CompletionTarget(tracked, partial(reference_progress, app, source, tracked))


def session_target(app, session):
    if session.provider == 'library':
        return reference_target(app, dict(type='session', provider='library', resource=session.resource))
    source = (getattr(session, 'source', None) or getattr(session, 'history_source', None)
              or getattr(session, 'cache_source', None))
    return reference_target(app, source, session.kind)


def percentage(target):
    try:
        with target() as progress:
            return progress.percentage()
    except _READ_ERRORS:
        return None


async def load_percentage(app, target, *, active):
    """Serialize background reads across visible surfaces, including cancelled owners."""
    from services.worker_retirement import drain_worker

    limit = getattr(app, '_document_completion_limit', None)
    if limit is None:
        limit = app._document_completion_limit = asyncio.Semaphore(1)
    async with limit:
        if not active():
            return None
        worker = asyncio.create_task(asyncio.to_thread(percentage, target))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            await drain_worker(worker)
            raise


def refresh_browsers(app):
    for browser in tuple(getattr(app, '_completion_browsers', ())):
        browser.refresh_completion()


def refresh_cards(app, kind):
    for media in tuple(getattr(app, '_completion_card_media', ())):
        media.refresh_completion(kind)


def _same_checkpoint(first, second):
    return (first is not None and second is not None and first.identity == second.identity
            and first.kind == second.kind and first.revision == second.revision)


async def _retire_readers(app, state):
    books = getattr(getattr(app, 'readers', None), 'controllers', {})
    files = getattr(getattr(app, 'private_sessions', None), 'controllers', {})
    for owners, attribute in ((books, '_book_progress'), (files, '_provider_progress')):
        for key, owner in tuple(owners.items()):
            progress = getattr(owner, attribute, None)
            if not _same_checkpoint(getattr(progress, 'state', None), state):
                continue
            await progress.flush()
            if not app.close_session(key):
                raise OSError('Close the document before updating its reading status.')
    video = getattr(app, 'video_player', None)
    if _same_checkpoint(getattr(getattr(video, 'progress', None), 'state', None), state):
        await video.close()


def mark_labels(target):
    if target.kind == 'video':
        return 'Mark as Watched', 'Mark as Unwatched'
    return 'Mark as Read', 'Mark as Unread'


async def mark(app, target, read):
    import toga
    from services.worker_retirement import drain_worker

    label = mark_labels(target)[0 if read else 1]
    stack = ExitStack()
    worker = asyncio.create_task(asyncio.to_thread(stack.enter_context, target()))
    try:
        progress = await asyncio.shield(worker)
        if not app.active_host:
            return False
        await _retire_readers(app, progress.state)
        worker = asyncio.create_task(asyncio.to_thread(progress.mark, read))
        status = await asyncio.shield(worker)
        if status not in {'saved', 'session-only'}:
            activity = 'Playback' if target.kind == 'video' else 'Reading'
            raise OSError(f'{activity} status could not be saved. Check file access and try again.')
    except asyncio.CancelledError:
        await drain_worker(worker)
        raise
    except _READ_ERRORS as error:
        if app.active_host:
            await app.main_window.dialog(toga.InfoDialog(label, str(error)))
        return False
    finally:
        await asyncio.to_thread(stack.close)
    if app.active_host:
        from .favourites import refresh
        from .haptics import feedback
        feedback(app.main_window, confirmed=True)
        refresh(app)
        refresh_browsers(app)
    return True


def commands(app, target):
    if target is None:
        return []
    complete, incomplete = mark_labels(target)
    return [(complete, partial(mark, app, target, True)),
            (incomplete, partial(mark, app, target, False))]


def file_target(app, provider, row):
    if provider is None or not row or row.get('directory') or not row.get('path') or row.get('cached'):
        return None
    kind = tracked_kind(row['path'], 'comic' if row.get('comic') else None)
    if kind is None:
        return None
    from services.documents.storage import FileItem
    item = FileItem(provider, row['path'], row.get('revision'))
    return CompletionTarget(kind, partial(item_progress, app, item, kind))


def file_commands(app, provider, row):
    return commands(app, file_target(app, provider, row))
