"""Disposable Android sleep/trim/wake acceptance using only synthetic documents."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from commonUtils.runtime.resources.documents import LocalDocuments
from commonUtils.runtime.resources.local import LocalFiles
from features.pdf.mobile.copies import PDFCopies
from features.text_editor.resources import LocalTextCopies
from services.session_auth import ResumePassword
from mobile.app import LogisticsMobile
from .fixtures import make_books, capture_window, png_page

BUNDLE = 'io.github.ispaure.logisticsreaderresumeqa'
PASSWORD = 'synthetic-resume-password'


class ReaderResumeProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('resume-fixtures-' + uuid4().hex)
        self.trim_count = self.pause_count = self.wake_count = 0
        super().startup()

    def release_disposable_resources(self):
        super().release_disposable_resources()
        self.trim_count += 1

    def on_running(self):
        if not getattr(self, '_resume_probe_started', False):
            self._resume_probe_started = True
            self.loop.create_task(self.check())

    async def wait_until(self, predicate, message, timeout=15):
        try:
            async with asyncio.timeout(timeout):
                while not predicate():
                    await asyncio.sleep(.1)
        except TimeoutError as error:
            raise AssertionError(message) from error

    def publish(self):
        self.result_path.write_text(json.dumps(self.result, indent=2) + '\n')

    async def sleep_cycle(self, name, restored, *, protected=False):
        privacy = self.screen_privacy
        before = self.pause_count, self.wake_count, self.trim_count
        destination = self.native_host.state.destination
        routes = tuple(route for route, _, _ in self.routes.screens[destination])
        active = self.workspace.active
        await asyncio.sleep(.4)
        await capture_window(self, self.evidence / (name + '-before.png'))
        self.result.update(phase='await_sleep', case=name, sequence=self.result['sequence'] + 1)
        self.publish()
        await self.wait_until(lambda: self.pause_count > before[0] and self.wake_count > before[1]
                              and self.trim_count > before[2], 'OS sleep/wake/trim callbacks were not delivered', 30)
        if protected:
            await self.wait_until(lambda: self.main_window.content is privacy.lock_view, 'Session password lock missing')
            privacy.lock_password.value = PASSWORD
            await privacy.unlock()
        await self.wait_until(restored, 'Reader did not recover its visible content after sleep')
        assert self.workspace.active == active, 'Wake changed the active document'
        assert self.native_host.state.destination == destination, 'Wake changed the destination'
        assert tuple(route for route, _, _ in self.routes.screens[destination]) == routes, 'Wake changed the route stack'
        await asyncio.sleep(.4)
        await capture_window(self, self.evidence / (name + '-after.png'))
        self.result['cases'].append(dict(name=name, paused=self.pause_count - before[0],
            resumed=self.wake_count - before[1], trimmed=self.trim_count - before[2], same_route=True))
        if name.startswith('library-'):
            # Exercise the real memory subscription's queued dispatch after wake,
            # independently of Android's suppression of duplicate trim levels.
            owner = self.readers.active
            await self.wait_until(lambda: not owner.book_busy, 'Reader remained busy after wake')
            previous_reader, previous_trim = owner.book_reader, self.trim_count
            self.memory_pressure.release()
            await self.wait_until(lambda: self.trim_count > previous_trim, 'Queued trim was not dispatched')
            await self.wait_until(lambda: restored() and owner.book_reader is not previous_reader,
                                  'Post-resume queued trim left the visible reader blank')
            self.result['cases'][-1]['queued_trim_after_resume'] = True


    async def check(self):
        self.evidence = Path(self.paths.cache) / 'reader-resume-evidence'
        self.evidence.mkdir(exist_ok=True)
        self.result_path = Path(self.paths.cache) / 'reader-resume-result.json'
        self.result = dict(success=False, phase='starting', sequence=0, cases=[])
        try:
            await self.wait_until(lambda: not getattr(self, '_startup_in_progress', False), 'Startup stalled', 30)
            privacy = self.screen_privacy
            conceal, reveal = privacy.conceal, privacy.reveal
            def paused():
                conceal()
                self.pause_count += 1
            def resumed():
                reveal()
                self.wake_count += 1
            privacy.conceal, privacy.reveal = paused, resumed
            # The old sampler overflowed Android's int for a one-pixel target.
            from features.comics.mobile.composite import compose_spread
            tiny = compose_spread([png_page()])
            assert tiny._impl.native.getWidth() == tiny._impl.native.getHeight() == 1
            self.result['one_pixel_native_decode'] = True
            fixtures = self.private_root / 'Fixtures'
            fixtures.mkdir()
            epub, comic = make_books(fixtures)
            # Use ordinary portrait pages rather than the shared 1x1 icon fixture.
            import struct
            import zlib
            from zipfile import ZipFile
            def chunk(kind, data):
                return (struct.pack('>I', len(data)) + kind + data
                        + struct.pack('>I', zlib.crc32(kind + data)))
            page = (b'\x89PNG\r\n\x1a\n'
                    + chunk(b'IHDR', struct.pack('>IIBBBBB', 32, 48, 8, 6, 0, 0, 0))
                    + chunk(b'IDAT', zlib.compress((b'\x00' + b'\xff\x00\x00\xff' * 32) * 48))
                    + chunk(b'IEND', b''))
            with ZipFile(comic, 'w') as archive:
                archive.writestr('page1.png', page)
                archive.writestr('page2.png', page)
            for source, immersive in ((comic, True), (comic, False), (epub, True)):
                record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), source)
                assert await self.open_book(record['id'])
                owner = self.readers.active
                await owner.move_book_page(1)
                owner.set_reading_mode(immersive)
                if record['kind'] == 'epub':
                    await self.wait_until(lambda: owner.epub_view._chapter_bridge.ready, 'EPUB chapter did not load')
                name = 'library-' + record['kind'] + ('-reading' if immersive else '-controls')
                def ready():
                    if owner.book_reader is None or owner.book_busy or owner.book_record['position'] != 1:
                        return False
                    if owner.reader_immersive != immersive or not owner.book_content.children:
                        return False
                    if record['kind'] == 'epub':
                        return owner.epub_view._chapter_bridge.ready
                    view = owner.book_content.children[0]
                    return getattr(view, 'canvas', view).image is not None
                await self.sleep_cycle(name, ready)
                await self.wait_until(lambda: self.close_session(owner.session.id), 'Reader close did not settle')
            # Ordinary file-backed documents use the provider session path too.
            for suffix, content in (('txt', 'Synthetic retained text'), ('md', '# Synthetic retained Markdown')):
                path = fixtures / ('Resume.' + suffix)
                path.write_text(content)
                copies = LocalTextCopies(LocalFiles(fixtures))
                assert await self.open_crypt(copies=copies, key=path.name)
                owner = self.private_sessions.active
                if suffix == 'txt':
                    owner.crypt_text.value = 'Synthetic unsaved text survives sleep'
                    expected = owner.crypt_text.value
                    ready = lambda: owner.crypt_text.value == expected
                else:
                    ready = lambda: owner.crypt_preview is not None and owner.crypt_preview in owner.crypt_content.children
                await self.sleep_cycle('local-' + suffix, ready)
                await self.wait_until(lambda: self.close_session(owner.session.id, choice='discard'), 'Editor close did not settle')
            from pypdf import PdfWriter
            path = fixtures / 'Resume.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=400)
            writer.add_blank_page(width=300, height=400)
            writer.write(path)
            copies = PDFCopies(LocalFiles(fixtures))
            assert await self.open_crypt(copies=copies, key=path.name)
            owner = self.private_sessions.active
            await owner.move_private_page(1)
            page = owner.crypt_page.value
            await self.sleep_cycle('local-pdf', lambda: owner.crypt_image.image is not None
                                   and owner.crypt_page.value == page)
            await self.wait_until(lambda: self.close_session(owner.session.id), 'PDF close did not settle')
            # A separate synthetic gate exercises the already supported session-only path.
            from services.documents.readers import PrivateReader
            from commonUtils.runtime.resources.archives import LocalArchiveSource
            class ComicCopies:
                root = fixtures
                encrypted = False
                offline = True
                def open(self, key, **kwargs):
                    return PrivateReader(str(comic), source=LocalArchiveSource(comic))
            assert await self.open_crypt(copies=ComicCopies(), key=comic.name,
                                         privacy_gate=ResumePassword(PASSWORD)), self.cloud_status.value
            owner = self.private_sessions.active
            await owner.move_private_page(1)
            page = owner.crypt_page.value
            await self.sleep_cycle('session-only-comic', lambda: not getattr(owner, 'page_suspended', False)
                and owner.crypt_content.children and owner.crypt_page.value == page, protected=True)
            self.result.update(success=True, phase='complete')
        except BaseException:
            self.result.update(success=False, phase='complete', error=traceback.format_exc())
            owner = getattr(getattr(self, 'readers', None), 'active', None)
            if owner is not None:
                task = getattr(owner, '_resume_book_task', None)
                self.result['diagnostics'] = dict(
                    active=self.workspace.active, visible=self.visible_reader(),
                    owner_session=getattr(getattr(owner, 'session', None), 'id', None),
                    decoder=getattr(owner, 'book_reader', None) is not None,
                    busy=getattr(owner, 'book_busy', None),
                    suspended=getattr(owner, '_reader_suspended', None),
                    immersive=getattr(owner, 'reader_immersive', None),
                    saved_mode=getattr(owner, '_suspended_reading_mode', None),
                    status=getattr(getattr(owner, 'book_status', None), 'text', None),
                    task_done=task.done() if task is not None else None,
                    task_error=str(task.exception()) if task is not None and task.done() and not task.cancelled() else None,
                    pauses=self.pause_count, wakes=self.wake_count, trims=self.trim_count)

        self.publish()
        print('READER_RESUME=' + json.dumps(self.result), flush=True)


def main():
    return ReaderResumeProbe('Reader Resume QA', BUNDLE)
