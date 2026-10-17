"""Isolated reader validation on native Android/iOS; synthetic data only.

This is a targeted probe entry point, separate from the release CASES contract.
Use a separate app ID and copy its result from the app cache after each phase.
"""
import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import struct
import sys
import traceback
from uuid import uuid4
from zipfile import ZipFile
import zlib

from commonUtils.runtime.document_access import LocalDocuments
from logisticsmobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticsreaderprobe'


def book_bytes(*, private=False):
    archive = BytesIO()
    with ZipFile(archive, 'w') as output:
        output.writestr('mimetype', 'application/epub+zip')
        output.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        output.writestr('OPS/book.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>Reader validation</dc:title>'
            '<dc:language>en</dc:language><dc:creator>Metadata Author</dc:creator><dc:subject>DistinctiveTag</dc:subject></metadata><manifest>'
            '<item id="one" href="one.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="two" href="two.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            '</manifest><spine><itemref idref="one"/><itemref idref="two"/></spine></package>')
        output.writestr('OPS/nav.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
            '<body><nav epub:type="toc"><ol><li><a href="one.xhtml">First chapter</a><ol>'
            '<li><a href="one.xhtml#p35">Nested passage</a></li></ol></li>'
            '<li><a href="two.xhtml#second">Second chapter</a></li></ol></nav></body></html>')
        for name in ('one', 'two'):
            body = '<h1 id="second">😀 Straße ' + name + '</h1>'
            if private:
                body += '<p>' + private + '</p>'
            body += ''.join(f'<p id="p{i}">Paragraph {i}. ' + 'Readable text ' * 30 + '</p>' for i in range(70))
            body += '<a href="two.xhtml#second">Next internal chapter</a><a href="https://example.invalid/">External</a>'
            output.writestr('OPS/' + name + '.xhtml', '<html><body>' + body + '</body></html>')
    return archive.getvalue()


def image_bytes(color, width=100, height=200):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress((b'\x00' + color * width) * height)) + chunk(b'IEND', b''))


class ProbeClient:
    generation = 0
    def crypt_remotes(self): return []
    def cancel(self): pass


class ReaderProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'reader-validation-v4'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def until(self, predicate, message='Reader condition timed out'):
        for _ in range(150):
            if predicate():
                return
            await asyncio.sleep(.1)
        raise AssertionError(message)

    async def settled(self, owner):
        await self.until(lambda: not owner.book_busy)
        task = getattr(owner, '_epub_location_task', None)
        if task is not None:
            await task

    async def ready(self, owner):
        await self.until(lambda: owner.epub_view._chapter_bridge.ready, owner.book_status.text)
        await asyncio.sleep(.6)
        installed = await owner.epub_view.evaluate_javascript('Boolean(window.reader && window.reader.seek)')
        base = await owner.epub_view.evaluate_javascript('document.baseURI.slice(0,80)')
        assert installed, f'Trusted reader bridge not installed; base={base!r}'
        await self.settled(owner)

    async def rotate(self, landscape):
        if sys.platform == 'ios':
            from rubicon.objc import ObjCClass
            preferences = ObjCClass('UIWindowSceneGeometryPreferencesIOS').alloc().initWithInterfaceOrientations(8 if landscape else 2)
            self.main_window._impl.native.windowScene.requestGeometryUpdateWithPreferences(preferences, errorHandler=None)
        else:
            self._impl.native.setRequestedOrientation(0 if landscape else 1)
        await asyncio.sleep(1)

    async def composite_zoom(self, spread, output, prefix):
        assert len(spread.canvases) == 1
        canvas = spread.canvas
        assert 0 < canvas.image.width <= 8192 and canvas.image.width * canvas.image.height <= 16_000_000, canvas.image.size
        canvas.image.save(output / (prefix + '-composite.png'))
        canvas.set_zoom(2)
        await asyncio.sleep(.3)
        assert abs(spread.zoom_scale - 2) < .05
        native = canvas._impl.native
        if sys.platform == 'ios':
            from rubicon.objc import CGPoint
            before = float(native.contentOffset.x)
            maximum = float(native.contentSize.width - native.bounds.size.width)
            target = min(maximum, before + 60) if before + 30 < maximum else max(0, before - 60)
            native.setContentOffset(CGPoint(target, native.contentOffset.y), animated=False)
            await asyncio.sleep(.2)
            assert abs(float(native.contentOffset.x) - before) > 10
        else:
            from java import jarray, jfloat
            from android.view import MotionEvent
            from android.os import SystemClock
            matrix = jarray(jfloat)(9)
            native.getImageMatrix().getValues(matrix)
            before = float(matrix[2])
            now = SystemClock.uptimeMillis()
            x, y = native.getWidth() / 2, native.getHeight() / 2
            for action, dx, elapsed in [(0, 0, 0), (2, 60, 100), (1, 60, 200)]:
                event = MotionEvent.obtain(now, now + elapsed, action, x + dx, y, 0)
                native.onTouchEvent(event)
                event.recycle()
            native.getImageMatrix().getValues(matrix)
            assert abs(float(matrix[2]) - before) > 10
        from .fixtures import capture_window
        await capture_window(self, output / (prefix + '-zoom-pan.png'))

    async def probe(self):
        output = self.private_root / 'evidence'
        output.mkdir(exist_ok=True)
        marker = output / 'restart.json'
        cases = []
        result = dict(success=False, target='ios' if sys.platform == 'ios' else 'android',
                      sys_platform=sys.platform, backend=type(self._impl).__module__, cases=cases,
                      scope='Targeted native reader probe, synthetic files and separate app ID; not full release evidence.')
        try:
            from importlib.resources import files
            result['source'] = json.loads(files('logisticsmobile').joinpath('source.json').read_text())
            if marker.exists():
                state = json.loads(marker.read_text())
                await self.open_book(state['id'])
                owner = self.readers.active
                await self.ready(owner)
                assert owner.book_record['location'] == state['location'], (owner.book_record['location'], state['location'])
                assert owner.epub_offset == state['location']['offset']
                result.update(state.get('details', {}))
                cases.extend(state['cases'])
                cases.append('process_restart_precise_resume')
                result['success'] = True
                marker.unlink()
            else:
                fixtures = self.private_root / ('fixtures-' + uuid4().hex)
                fixtures.mkdir()
                source = fixtures / 'Book.epub'
                source.write_bytes(book_bytes())
                self.show_library()
                store = self.reader_manager().catalog.library_store
                record = store.import_book(LocalDocuments(), source)
                await self.open_book(record['id'])
                owner = self.readers.active
                await self.ready(owner)
                cases.append('native_epub_bridge')
                assert any(entry.fragment == 'p35' for entry in owner.contents_choices.values())
                owner._epub_target = 'p35'
                await owner.move_book_page(0)
                await self.ready(owner)
                target = owner.epub_text.anchors['p35']
                assert owner.epub_offset == target
                cases.append('nested_contents_exact_anchor')
                await owner.epub_view.evaluate_javascript('window.reader.turn(1)')
                await asyncio.sleep(.4)
                await self.settled(owner)
                assert owner.epub_offset > target
                cases.append('screen_turn_persists_location')
                owner.show_epub_search()
                owner.epub_query.value = 'STRASSE'
                await owner.find_epub_next()
                await asyncio.sleep(.3)
                selected = await owner.epub_view.evaluate_javascript('getSelection().toString()')
                assert selected == 'Straße', repr(selected)
                await self.settled(owner)
                cases.append('unicode_search_highlight')
                expected = owner.epub_offset
                owner.show_reader_appearance()
                owner.reader_font.value, owner.reader_margin.value = '20', '24'
                await owner.apply_reader_appearance()
                await self.ready(owner)
                assert owner.epub_offset == expected, (expected, owner.epub_offset)
                cases.append('appearance_preserves_anchor')
                owner.show_reader_appearance()
                owner.reader_appearance.family_choice.value = 'serif'
                owner.reader_appearance.spacing_choice.value = '200'
                owner.reader_appearance.width_choice.value = '480'
                owner.reader_theme.value = 'sepia'
                await owner.apply_reader_appearance()
                await self.ready(owner)
                assert owner.epub_offset == expected
                metrics = await owner.epub_view.evaluate_javascript('JSON.stringify([getComputedStyle(document.body).fontFamily,getComputedStyle(document.body).lineHeight,getComputedStyle(document.body).maxWidth,getComputedStyle(document.body).backgroundColor])')
                result['typography_metrics'] = json.loads(metrics)
                from .fixtures import capture_window
                owner.library_view.refresh()
                await asyncio.sleep(.6)
                result['reader_layout'] = dict(frame=owner.library_view.layout.width, content=owner.book_content.layout.width,
                    body=self.native_host.bodies['documents'].layout.width, host=self.native_host.diagnostics())
                assert owner.library_view.layout.width >= self.main_window.size.width - 32, result['reader_layout']
                await asyncio.sleep(.6)
                await capture_window(self, output / 'typography.png')
                assert json.loads(metrics) == ['serif', '40px', '480px', 'rgb(244, 236, 216)'], metrics
                cases.append('native_typography_and_precise_anchor')
                owner.show_read_aloud()
                speech = owner.speech_panel
                await speech.ready_task
                result['speech_engine'] = dict(ready=speech.engine.ready, voices=len(speech.engine.voices), error=speech.engine.error)
                assert speech.engine.ready, result['speech_engine']
                await asyncio.sleep(.3)
                await capture_window(self, output / 'speech-controls.png')
                await owner.epub_view.evaluate_javascript('window.reader.seek(0, 18)')
                speech.speed_choice.value = '1.25'
                await speech.play()
                assert speech.session.state == 'speaking', speech.status.text
                assert speech.session.ranges[0][1] == 0 and speech.session.ranges[-1][2] == 18, speech.session.ranges
                speech.pause()
                assert speech.session.state == 'paused'
                speech.pause()
                assert speech.session.state == 'speaking'
                speech.session.stop()
                # A short real native utterance must complete via the platform callback.
                await owner.epub_view.evaluate_javascript('window.reader.seek(0, 9)')
                await speech.play()
                result['speech_selection'] = dict(speed=float(speech.speed_choice.value), count=len(speech.session.ranges), start=speech.session.ranges[0][1], end=speech.session.ranges[-1][2])
                assert speech.session.ranges[-1][2] == 9, result['speech_selection']
                await self.until(lambda: speech.session.state == 'stopped', 'Native speech completion callback did not arrive')
                assert 'Finished' in speech.status.text, speech.status.text
                owner.close_read_aloud()
                assert speech.closed and speech.engine.closed and not speech.session.ranges
                cases.append('native_speech_selection_pause_resume_completion_cleanup')
                expected = owner.epub_offset
                await self.rotate(True)
                await self.settled(owner)
                assert abs(owner.epub_offset - expected) < 80, (expected, owner.epub_offset)
                await self.rotate(False)
                await self.settled(owner)
                assert owner.epub_view.layout.content_width <= self.main_window.size.width + 2, (owner.epub_view.layout.content_width, self.main_window.size.width)
                cases.append('epub_rotation_preserves_passage')
                epoch, reader = owner.book_epoch, owner.book_reader
                owner.epub_link(reader, epoch, 0, 'two.xhtml#second')
                await asyncio.sleep(.4)
                await self.ready(owner)
                assert owner.book_record['position'] == 1
                assert owner.epub_view._chapter_bridge.navigation(None, 'https://example.invalid/') is False
                cases.append('internal_link_and_external_rejection')
                await owner.toggle_bookmark()
                assert owner.book_record['epub_bookmarks']
                owner.release_book_reader()
                await owner.open_book(record['id'])
                await self.ready(owner)
                cases.append('bookmark_reopen')
                self.cloud_client = ProbeClient()
                self.show_cloud(present=False)
                from services.documents.readers import PrivateReader
                sentinel = 'private-' + uuid4().hex
                class Copies:
                    root = self.private_root / 'ProbeProvider'
                    encrypted = False
                    offline = True
                    def open(inner, key, **kwargs):
                        return PrivateReader('Private probe.epub', book_bytes(private=sentinel))
                assert await self.open_crypt(copies=Copies(), key='private'), self.cloud_status.value
                private_owner = self.private_sessions.active
                panel = private_owner.provider_epub_view
                assert panel.webview.private_configured
                bridge = panel.webview._chapter_bridge
                await self.until(lambda: bridge.ready)
                await asyncio.sleep(.6)
                assert await panel.webview.evaluate_javascript('Boolean(window.reader)')
                if sys.platform == 'ios':
                    assert not bool(panel.webview._impl.native.configuration.websiteDataStore.isPersistent())
                else:
                    settings = panel.webview._impl.settings
                    assert not settings.getDomStorageEnabled()
                    assert settings.getCacheMode() == 2  # LOAD_NO_CACHE
                panel.query.value = 'STRASSE'
                panel.find()
                await asyncio.sleep(.3)
                assert await panel.webview.evaluate_javascript('getSelection().toString()') == 'Straße'
                panel.turn(1)
                await asyncio.sleep(.4)
                assert panel.offset > 0
                expected_private = panel.offset
                private_owner.show_provider_layout()
                private_owner.provider_font.value = '24'
                await private_owner.apply_provider_layout()
                panel = private_owner.provider_epub_view
                await self.until(lambda: panel.webview._chapter_bridge.ready)
                await asyncio.sleep(.6)
                assert panel.offset == expected_private, (panel.offset, expected_private)
                private_owner.show_provider_read_aloud()
                private_speech = panel.speech_panel
                await private_speech.ready_task
                assert private_speech.engine.ready
                await panel.webview.evaluate_javascript(f'window.reader.seek({expected_private}, {expected_private + 18})')
                await private_speech.play()
                assert private_speech.session.state == 'speaking'
                self.private_sessions.suspend()
                assert private_speech.closed and private_speech.engine.closed and not private_speech.session.ranges
                cases.append('private_speech_suspend_cleanup')
                assert panel.disposed and panel.webview.private_closed
                private_owner.resume_crypt()
                await self.until(lambda: hasattr(private_owner, 'provider_epub_view') and not private_owner.cloud_busy)
                panel = private_owner.provider_epub_view
                await self.until(lambda: panel.webview._chapter_bridge.ready)
                await asyncio.sleep(.6)
                assert abs(panel.offset - expected_private) < 80
                private_owner.toggle_private_bookmark()
                assert private_owner.epub_session_bookmarks
                assert self.private_sessions.close(private_owner.session.id, discard=True)
                assert panel.disposed and panel.webview.private_closed and panel.book is None
                for cache_root in {Path(os.path.commonpath([self.paths.cache, self.paths.data]))}:
                    for path in cache_root.rglob('*'):
                        if path.is_file():
                            assert sentinel.encode() not in path.read_bytes(), str(path)
                cases.append('provider_search_bookmark_and_memory_cleanup')
                comic = fixtures / 'Comic.cbz'
                with ZipFile(comic, 'w') as archive:
                    for number in range(6):
                        color = b'\xff\x00\x00\xff' if number % 2 == 0 else b'\x00\x00\xff\xff'
                        archive.writestr(f'page{number}.png', image_bytes(color, 200 if number == 3 else 100, 100 if number == 3 else 200))
                    archive.writestr('page6.png', b'bad page')
                    archive.writestr('page7.png', image_bytes(b'\xff\x00\x00\xff')[:33])
                    archive.writestr('ComicInfo.xml', '<ComicInfo><Manga>YesAndRightToLeft</Manga><Pages>'
                        '<Page Image="2" DoublePage="True"/></Pages></ComicInfo>')
                comic_record = store.import_book(LocalDocuments(), comic)
                self.preferences.save(comic_layout='double')
                await self.open_book(comic_record['id'])
                owner = self.readers.active
                assert owner.comic_navigation.visible == (0,1), owner.book_status.text
                await owner.next_book_page()
                assert owner.comic_navigation.visible == (2,)
                await owner.next_book_page()
                assert owner.comic_navigation.visible == (3,)
                await owner.next_book_page()
                assert owner.comic_navigation.visible == (4,5)
                before = owner.book_content.children[0]
                await owner.next_book_page()
                assert owner.book_record['position'] == 4 and owner.book_content.children[0] is before
                await owner.previous_book_page()
                assert owner.book_record['position'] == 3
                cases.append('manga_spreads_doublepage_landscape_failed_read')
                await owner.move_book_page(0)
                from .fixtures import capture_window
                await asyncio.sleep(.3)
                spread = owner.book_content.children[0]
                assert len(spread.canvases) == 1
                assert 20 < spread.canvas.layout.content_width <= self.main_window.size.width
                await capture_window(self, output / 'comic-spread.png')
                await self.composite_zoom(spread, output, 'imported')
                spread.turn(1)
                spread.canvas.page(1)
                await asyncio.sleep(.3)
                assert owner.book_record['position'] == 0
                cases.append('composite_zoom_pan_and_paging_guard')
                await self.rotate(True)
                await asyncio.sleep(.6)
                assert owner.book_content.children[0] is spread and spread.zoom_scale > 1.9
                spread.fit_page()
                await self.until(lambda: owner.book_content.children[0] is not spread)
                assert spread.canvas.image is None
                await self.rotate(False)
                await asyncio.sleep(.6)
                cases.append('zoomed_rotation_defers_layout_until_fit')
                owner.set_reading_mode(False)
                owner.fit_comic_page()
                owner.set_reading_mode(True)
                cases.append('comic_controls_fit_and_immersive_reentry')
                self.preferences.save(comic_layout='auto')
                await owner.move_book_page(0)
                await self.rotate(True)
                await asyncio.sleep(.6)
                from features.comics.reading import visible_pages
                expected_pages = visible_pages(0, owner.comic_navigation.sizes, owner.comic_viewport(), 'auto')
                assert owner.comic_navigation.visible == expected_pages, (owner.comic_navigation.visible, expected_pages, owner.comic_viewport())
                await self.rotate(False)
                await asyncio.sleep(.6)
                expected_pages = visible_pages(0, owner.comic_navigation.sizes, owner.comic_viewport(), 'auto')
                assert owner.comic_navigation.visible == expected_pages, (owner.comic_navigation.visible, expected_pages, owner.comic_viewport())
                cases.append('comic_auto_rotation')
                class ComicCopies:
                    root = self.private_root / 'ProbeComics'
                    encrypted = False
                    offline = True
                    def open(inner, key, **kwargs):
                        return PrivateReader('Private comic.cbz', comic.read_bytes())
                assert await self.open_crypt(copies=ComicCopies(), key='comic')
                comic_owner = self.private_sessions.active
                await self.rotate(True)
                await asyncio.sleep(.7)
                nav = comic_owner.crypt_reader.comic_navigation
                viewport = comic_owner.private_comic_viewport()
                assert nav.visible == visible_pages(0, nav.sizes, viewport, 'auto'), (nav.visible, viewport)
                await self.rotate(False)
                await asyncio.sleep(.7)
                viewport = comic_owner.private_comic_viewport()
                assert nav.visible == visible_pages(0, nav.sizes, viewport, 'auto'), (nav.visible, viewport)
                cases.append('provider_comic_auto_rotation')
                self.preferences.save(comic_layout='double')
                await comic_owner.read_crypt_page()
                private_spread = comic_owner.provider_spread
                await self.composite_zoom(private_spread, output, 'provider')
                await comic_owner.move_private_page(7)
                assert comic_owner.provider_spread is private_spread and private_spread.zoom_scale > 1.9
                assert comic_owner.crypt_reader.comic_navigation.visible == (0, 1)
                cases.append('provider_failed_decode_retains_zoomed_spread')
                self.private_sessions.suspend()
                assert private_spread.canvas.image is None
                comic_owner.resume_crypt()
                await self.until(lambda: hasattr(comic_owner, 'provider_spread') and not comic_owner.cloud_busy)
                private_spread = comic_owner.provider_spread
                assert private_spread.zoom_scale == 1
                assert self.private_sessions.close(comic_owner.session.id, discard=True)
                assert private_spread.canvas.image is None
                cases.append('provider_composite_zoom_suspend_and_close')
                catalog = self.reader_manager().catalog
                catalog.show_library(present=False)
                catalog.refresh_library()
                await catalog.metadata_task
                catalog.library_search.value = 'metadata author distinctivetag'
                catalog.filter_library()
                assert any(button.text == 'Book.epub' for button in catalog.library_row_buttons)
                cases.append('imported_metadata_search_and_suggestions')
                batch_root = self.private_root / 'LocalFiles/FolderBatch'
                (batch_root / 'nested').mkdir(parents=True, exist_ok=True)
                for path in [batch_root / 'one.cbz', batch_root / 'nested/two.cbz']:
                    path.write_bytes(comic.read_bytes())
                await self.show_files(local_root=True)
                self.file_location.value = 'FolderBatch'
                await self.browse_files()
                self.file_selection.value = 'Select an item…'
                await self.edit_local_comic_folder()
                batch = self.local_comic_batch_view
                batch.refresh()
                await asyncio.sleep(.6)
                result['batch_layout'] = dict(view=batch.layout.width, content=batch.content.layout.width,
                    switch=batch.metadata_switches['Title'].layout.width, host=self.native_host.diagnostics())
                assert batch.content.layout.width <= self.main_window.size.width, result['batch_layout']
                assert len(self.local_comic_batch.entries) == 2
                await asyncio.sleep(.3)
                await asyncio.sleep(.6)
                await capture_window(self, output / 'library-batch.png')
                batch.metadata_inputs['Title'].value = 'Native recursive edit'
                batch.metadata_switches['Title'].value = True
                await batch.metadata_apply(None)
                assert '2 saved; 0 failed' in batch.metadata_status.text, batch.metadata_status.text
                from features.comics.library import ComicDocument
                for path in [batch_root / 'one.cbz', batch_root / 'nested/two.cbz']:
                    assert ComicDocument(path).info.get_field('Title') == 'Native recursive edit'
                    with ZipFile(path) as edited, ZipFile(comic) as original:
                        for name in original.namelist():
                            if name != 'ComicInfo.xml':
                                assert original.read(name) == edited.read(name)
                cases.append('local_recursive_metadata_batch_native_publication')
                await self.open_book(record['id'])
                owner = self.readers.active
                await self.ready(owner)
                target = owner.epub_text.anchors['p35']
                owner.epub_view._chapter_bridge.seek(target)
                owner.epub_event(owner.book_reader, owner.book_epoch, owner.book_record['position'], 'position', target)
                await self.settled(owner)
                marker.write_text(json.dumps(dict(id=record['id'], location=owner.book_record['location'], cases=cases, details={key: result[key] for key in ('speech_engine', 'speech_selection', 'typography_metrics') if key in result})))
                result['awaiting_restart'] = True
                result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
            traceback.print_exc()
        (output / 'result.json').write_text(json.dumps(result, indent=2))
        print('READER_PROBE_RESULT=' + json.dumps(result), flush=True)
        print('READER_PROBE_PATH=' + str(output), flush=True)
        await asyncio.sleep(.2)
        os._exit(0 if result['success'] else 1)


def main():
    return ReaderProbe('Logistics Reader Probe', BUNDLE)
