"""Experimental iPhone Duo cover output, gated by reader and process privacy."""
import asyncio
from functools import partial

BOOK_COVER = 'epub_outer_cover'
COMIC_COVER = 'comic_outer_cover'


def native_bridge(app):
    if not type(app._impl).__module__.startswith('toga_iOS.'):
        return None
    from rubicon.objc import ObjCClass
    try:
        bridge = ObjCClass('LogisticsReaderCoverDisplay')
    except NameError:
        return None
    return bridge if bridge.supported() else None


def cover_source(app):
    """Use an already open decoder, with no fallback to a protected source."""
    from services.access_policy import session_only
    key = app.visible_reader()
    if key is None:
        return None
    owner = getattr(getattr(app, 'readers', None), 'controllers', {}).get(key)
    if owner is not None and not owner.session.transient and owner.book_record is not None:
        reader = owner.book_reader
        if (reader is not None and owner.book_record['kind'] == 'epub'
                and app.preferences.values[BOOK_COVER] == 'true' and not session_only(reader.source)):
            return reader, partial(epub_cover, reader)
        document = getattr(reader, 'document', None)
        if (document is not None and not document.password and not session_only(document.source)
                and app.preferences.values[COMIC_COVER] == 'true'):
            return reader, partial(comic_cover, reader)
    owner = getattr(getattr(app, 'private_sessions', None), 'controllers', {}).get(key)
    if owner is None or owner.privacy_gate is not None or not getattr(owner, '_open_presented', False):
        return None
    from .files_ui import ordinary_local_copies
    copies = getattr(owner, '_crypt_reader_store', None)
    reader = owner.crypt_reader
    if (reader is None or not ordinary_local_copies(copies) or session_only(copies)
            or session_only(reader.source)):
        return None
    if reader.book is not None and app.preferences.values[BOOK_COVER] == 'true':
        return reader, partial(epub_cover, reader.book)
    if reader.kind in {'.cbz', '.zip'} and app.preferences.values[COMIC_COVER] == 'true':
        return reader, partial(provider_comic_cover, reader)
    return None


def epub_cover(book):
    path = book.cover_path()
    return book.read(path) if path else None


def comic_cover(reader):
    from features.images.validation import MAX_IMAGE
    with reader.document.open_archive() as archive:
        member = archive.getinfo(reader.pages[0])
        return archive.read(member) if member.file_size <= MAX_IMAGE else None


def provider_comic_cover(reader):
    return reader.page(0)[1]


class ReaderCoverDisplay:
    def __init__(self):
        self.native = None
        self.reader = None
        self.task = None

    def clear(self):
        if self.task is not None:
            self.task.cancel()
            self.task = None
        if self.native is not None:
            self.native.clearCover()
            self.native = None
        self.reader = None

    @staticmethod
    def candidate(app, allowed):
        if app is None or getattr(app, '_hinge_status', 0) not in (2, 3) or not allowed(app):
            return None
        privacy = app.screen_privacy
        if privacy.interrupted or privacy.captured or not getattr(app, 'scene_active', False):
            return None
        if all(app.preferences.values[key] != 'true' for key in (BOOK_COVER, COMIC_COVER)):
            return None
        return cover_source(app)

    def refresh(self, app, allowed):
        candidate = self.candidate(app, allowed)
        if candidate is None:
            self.clear()
            return
        reader, load = candidate
        if reader is self.reader:
            return
        self.clear()
        bridge = native_bridge(app)
        if bridge is not None:
            self.reader = reader
            self.task = app.loop.create_task(self.load(app, reader, load, allowed, bridge))

    async def load(self, app, reader, load, allowed, bridge):
        try:
            from features.images.validation import image_dimensions
            from features.images.mobile.decoding import decode_page
            data = await asyncio.to_thread(load)
            current = self.candidate(app, allowed)
            if not data or current is None or current[0] is not reader:
                return
            image = decode_page(data, image_dimensions(data), (1200, 1200), 'toga_iOS.')
            controller = app.main_window._impl.native.rootViewController
            if controller is not None:
                self.native = bridge.sharedDisplay()
                self.native.showCover(image._impl.native, fromController=controller)
        except Exception:
            # A missing or unreadable cover must never interfere with reading.
            return
        finally:
            if self.task is asyncio.current_task():
                self.task = None
