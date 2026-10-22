"""Synthetic native reader swaps, Folder Hub and shared chat lifecycle smoke."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import traceback
from mobile.app import LogisticsMobile


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'content-refactor-fixtures'
        super().startup()

    def on_running(self):
        if not getattr(self, '_content_probe_started', False):
            self._content_probe_started = True
            self.loop.create_task(self.check())

    async def folders(self):
        (self.private_root / 'LocalFiles' / 'Synthetic').mkdir(parents=True, exist_ok=True)
        self.show_locations()
        await asyncio.sleep(.5)
        assert 'Synthetic' in self.folder_buttons, list(self.folder_buttons)
        self.change_folder_source('rclone')
        self.change_folder_source('Local')
        assert 'Synthetic' in self.folder_buttons
        return dict(local_listing=True, source_swap=True)

    async def chat(self):
        from mobile.chat_fixture import fixture_server
        self.show_chat()
        with fixture_server() as (url, _, _, requests):
            self.chat_url.value, self.chat_model.value = url, 'fixture-model'
            self.chat_prompt.value = 'Synthetic native question'
            task = asyncio.create_task(self.chat_primary_action())
            await asyncio.sleep(.01)
            self.chat_prompt.value = 'Next unsent draft'
            await task
        assert self.chat_current['messages'][-1]['content'] == 'Native fixture reply'
        assert self.chat_prompt.value == 'Next unsent draft'
        assert self.chat_store.load(self.chat_current['id'])['draft'] == 'Next unsent draft'
        assert len(requests) == 1
        return dict(reply=True, draft_retained=True, requests=len(requests))

    async def reading(self):
        from tests.logisticsmobile.fixtures import make_books
        from commonUtils.runtime.resources.documents import LocalDocuments
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        from services.documents.readers import PrivateReader
        fixtures = self.private_root / 'synthetic-books'
        fixtures.mkdir(exist_ok=True)
        epub, comic = make_books(fixtures)
        store = self.reader_manager().catalog.library_store
        published = []
        for path in (epub, comic):
            record = await asyncio.to_thread(store.import_book, LocalDocuments(), path)
            await self.open_book(record['id'])
            owner = self.readers.active
            await asyncio.sleep(.3)
            assert len(owner.book_content.children) == 1
            assert owner.book_record['position'] == 0
            published.append(record['kind'])
            await owner.move_book_page(1)
            assert len(owner.book_content.children) == 1
        self.show_cloud(present=False)
        for path in (comic, epub):
            data = path.read_bytes()
            def open_copy(key, **kwargs):
                reader = PrivateReader(key, data)
                reader.key = key
                return reader
            files = LocalFiles(fixtures)
            copies = SimpleNamespace(root=fixtures, provider=files, encrypted=False, open=open_copy)
            assert await self.open_crypt(copies=copies, key=path.name), self.cloud_status.value
            owner = self.private_sessions.active
            await asyncio.sleep(.3)
            assert len(owner.crypt_content.children) == 1
            assert owner._provider_displayed_index == 0
            owner.crypt_page.value = owner.crypt_reader.labels[1]
            await owner.read_crypt_page()
            assert owner._provider_displayed_index == 1
            assert len(owner.crypt_content.children) == 1
        (fixtures / 'Synthetic.txt').write_text('Editable synthetic text')
        assert await self.open_crypt(copies=LocalTextCopies(LocalFiles(fixtures)), key='Synthetic.txt')
        owner = self.private_sessions.active
        assert owner.crypt_text.value == 'Editable synthetic text'
        assert owner.crypt_content.children[0] is owner.crypt_text
        return dict(library=published, provider=['comic', 'epub', 'text'], position=1)

    async def check(self):
        result = dict(success=False, backend=type(self._impl).__module__)
        for name in ('folders', 'chat', 'reading'):
            try:
                result[name] = await asyncio.wait_for(getattr(self, name)(), 45)
            except Exception:
                result[name] = dict(error=traceback.format_exc())
        result['success'] = all('error' not in result[name] for name in ('folders', 'chat', 'reading'))
        (Path(self.paths.cache) / 'refactor-content-result.json').write_text(json.dumps(result))


def main():
    return Probe('Content refactor QA', 'io.github.ispaure.logisticsrefactorqa')
