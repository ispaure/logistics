"""Synthetic, separate-bundle simulator probe; never opens user files/remotes."""
import asyncio
import json
import os
from pathlib import Path
import traceback
from logisticsmobile.app import LogisticsMobile
from commonUtils.runtime.document_access import LocalDocuments

OUTPUT = Path('/private/tmp/logistics-reader-probe')


class ReaderProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'reader-probe'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def wait(self, predicate):
        for _ in range(150):
            if predicate():
                return
            await asyncio.sleep(.1)
        raise RuntimeError('Native reader condition timed out')

    async def probe(self):
        passed = []
        try:
            OUTPUT.mkdir(exist_ok=True)
            source = Path(__file__).parents[2] / 'probe_fixture.epub'
            self.show_library()
            record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), source)
            await self.open_book(record['id'])
            owner = self.readers.active
            await self.wait(lambda: owner.epub_view._chapter_bridge.ready)
            await asyncio.sleep(.8)
            ready = await owner.epub_view.evaluate_javascript('Boolean(window.reader && window.reader.seek)')
            assert ready, 'Native WebView failed to install the trusted reading bridge'
            passed.append('native_epub_bridge')
            target = owner.epub_text.anchors['p35']
            await owner.epub_view.evaluate_javascript(f'window.reader.seek({target}); window.reader.turn(1)')
            await asyncio.sleep(.5)
            await self.wait(lambda: not owner.book_busy)
            task = getattr(owner, '_epub_location_task', None)
            if task:
                await task
            assert owner.book_record['location']['offset'] > target, str(owner.book_record)
            passed.append('native_screen_turn_persists_utf16_anchor')
            owner.show_epub_search()
            owner.epub_query.value = 'STRASSE'
            await owner.find_epub_next()
            await asyncio.sleep(.4)
            selection = await owner.epub_view.evaluate_javascript('getSelection().toString()')
            assert selection == 'Straße', repr(selection)
            passed.append('native_unicode_search_highlight')
            if getattr(owner, '_epub_location_task', None):
                await owner._epub_location_task
            await owner.toggle_bookmark()
            self.assert_bookmark(owner)
            expected = owner.epub_offset
            owner.release_book_reader()
            await owner.open_book(record['id'])
            await self.wait(lambda: owner.epub_view._chapter_bridge.ready)
            await asyncio.sleep(.5)
            assert owner.epub_offset == expected
            passed.append('native_precise_bookmark_and_reopen')
            owner.show_book_metadata()
            owner.book_metadata_fields['title'].value = 'Native edited title'
            await owner.save_book_metadata()
            assert owner.book_reader.title == 'Native edited title', owner.book_metadata_status.text
            passed.append('native_import_metadata_transaction')
            self.show_cloud(present=False)
            await self.wait(lambda: not self.cloud_busy)
            from logisticsmobile.localcrypt import PrivateReader
            class Copies:
                root = self.private_root / 'ProbeProvider'
                encrypted = False
                offline = True
                def open(inner, key, **kwargs):
                    return PrivateReader('Private probe.epub', source.read_bytes())
            copies = Copies()
            assert await self.open_crypt(copies=copies, key='private-book'), self.cloud_status.value
            private_owner = self.private_sessions.active
            panel = private_owner.provider_epub_view
            panel.query.value = 'STRASSE'
            panel.find()
            private_owner.toggle_private_bookmark()
            assert private_owner.epub_session_bookmarks
            assert self.private_sessions.close(private_owner.session.id, discard=True)
            assert panel.text.value == '' and panel.book is None
            passed.append('native_provider_search_bookmark_cleanup')
            self.preferences.save(comic_layout='double')
            comic = Path(__file__).parents[2] / 'probe_comic.cbz'
            record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), comic)
            await self.open_book(record['id'])
            owner = self.readers.active
            await asyncio.sleep(.5)
            assert owner.comic_navigation.visible == (0, 1), owner.book_status.text
            assert len(owner.book_content.children[0].canvases) == 2
            await owner.next_book_page()
            assert owner.book_record['position'] == 2
            await owner.previous_book_page()
            assert owner.book_record['position'] == 0
            passed.append('native_manga_spread_forward_backward')
            from tests.logisticsmobile.fixtures import capture_window
            await capture_window(self, OUTPUT / 'comic-spread.png')
            catalog = self.reader_manager().catalog
            second = catalog.library_store.import_book(LocalDocuments(), comic)
            self.reader_manager().show_catalog()
            catalog.refresh_library()
            catalog.imported_selected = {record['id'], second['id']}
            await catalog.edit_imported_comics()
            def metadata_form(widget):
                if hasattr(widget, 'metadata_inputs'):
                    return widget
                children = list(widget.children)
                content = getattr(widget, 'content', None)
                if content is not None and content not in children:
                    children.append(content)
                for child in children:
                    found = metadata_form(child)
                    if found is not None:
                        return found
                return None
            form = metadata_form(self.body)
            assert form is not None, catalog.book_status.text
            form.metadata_inputs['Publisher'].value = 'Native batch publisher'
            form.metadata_switches['Publisher'].value = True
            await form.metadata_apply(None)
            assert '2 saved' in form.metadata_status.text, form.metadata_status.text
            for item in (record, second):
                _, updated = catalog.library_store.open(item['id'])
                assert updated.document.info.get_field('Publisher') == 'Native batch publisher'
            passed.append('native_explicit_field_batch_metadata')
            result = dict(success=True, cases=passed, source=json.loads((Path(__file__).parents[2] / 'logisticsmobile/source.json').read_text()),
                scope='Targeted iOS simulator probe using existing native executable and current staged Python sources; separate bundle and synthetic storage.')
        except Exception:
            traceback.print_exc()
            result = dict(success=False, cases=passed, error=traceback.format_exc())
        (OUTPUT / 'result.json').write_text(json.dumps(result, indent=2))
        print('READER_PROBE=' + json.dumps(result), flush=True)
        await asyncio.sleep(.2)
        os._exit(0 if result['success'] else 1)

    @staticmethod
    def assert_bookmark(owner):
        assert owner.book_record['epub_bookmarks']


ReaderProbe('Logistics Reader Probe', 'io.github.ispaure.logisticsreaderprobe').main_loop()
