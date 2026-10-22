"""Synthetic iOS EPUB reload recovery and retained Documents-list chrome."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from commonUtils.runtime.document_access import LocalDocuments
from mobile.app import LogisticsMobile
from tests.logisticsmobile.fixtures import make_books, capture_window


class ReaderReopenProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('reader-reopen-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_probe_started', False):
            self._probe_started = True
            self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'reader-reopen-evidence'
        output.mkdir(exist_ok=True)
        result = dict(success=False)
        try:
            await asyncio.sleep(.5)
            epub, _ = make_books(self.private_root)
            store = self.reader_manager().catalog.library_store
            record = store.import_book(LocalDocuments(), epub)
            self.show_documents_hub()
            assert await self.open_book(record['id'])
            owner = self.readers.active

            async def chapter_ready():
                for _ in range(100):
                    text = await owner.epub_view.evaluate_javascript(
                        'window.reader ? document.body.innerText : ""')
                    if 'Native EPUB first' in str(text):
                        return
                    await asyncio.sleep(.05)
                raise AssertionError('EPUB chapter did not become readable')

            await chapter_ready()
            await owner.epub_view.evaluate_javascript('window.reader.seek(5)')
            owner.epub_event(owner.book_reader, owner.book_epoch, 0, 'position', 5)
            owner.request_position_flush()
            await owner._epub_location_task
            # Model a lost native document while its archive/session stays live.
            owner.epub_view.set_content('https://logistics.invalid/lost/', '<p>Blank replacement</p>')
            await asyncio.sleep(.4)
            assert await owner.epub_view.evaluate_javascript('typeof window.reader') == 'undefined'
            self.show_documents_hub()
            await asyncio.sleep(.4)
            assert not self.native_host.adapter.tabs_hidden(), 'Retained detail hides list tabs'
            result['retained_detail_list_tabs_visible'] = True
            await capture_window(self, output / 'documents-list.png')
            assert await self.open_book(record['id'])
            await chapter_ready()
            pagination = json.loads(await owner.epub_view.evaluate_javascript(
                'JSON.stringify(window.reader.pagination())'))
            assert pagination['anchor'] == 5, pagination
            assert len(self.workspace.sessions) == 1
            result['blank_document_recovered'] = True
            result['restored_anchor'] = pagination['anchor']
            assert self.native_host.adapter.tabs_hidden(), 'Reader destinations visible'
            await capture_window(self, output / 'reopened-epub.png')
            owner.library_view._reader_close_button._impl.native.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(.5)
            assert not self.native_host.adapter.tabs_hidden(), 'Close did not restore tabs'
            result['close_restores_tabs'] = True
            # Check the file-browser entry point too, using the same import.
            await self.show_files()
            assert await self.open_download(path=epub)
            owner = self.readers.active
            await chapter_ready()
            owner.library_view._reader_close_button._impl.native.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(.5)
            assert self.native_host.state.destination == 'files'
            assert not self.native_host.adapter.tabs_hidden()
            result['file_browser_open_close'] = True
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(result, indent=2))
        print('READER_REOPEN=' + json.dumps(result), flush=True)


def main():
    return ReaderReopenProbe('Reader Reopen QA', 'io.github.ispaure.logisticsreaderreopenqa')
