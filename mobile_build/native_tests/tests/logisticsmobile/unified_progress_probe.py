"""Displayed positions through the local reader routes and an OS process restart."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import asyncio
import base64
from dataclasses import asdict
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import traceback
from zipfile import ZipFile
import zlib

from mobile.app import LogisticsMobile
from mobile.document_sources import reopen_file
from services.documents.locations import collection_path
from services.documents.mobile_storage import open_provider_document
from . import start_native_check
from .epub_rotation_probe import MEASURE
from .fixtures import capture_window, make_books
from .video_probe import until

BUNDLE = 'io.github.ispaure.logisticsunifiedprogressqa'
RESULT = 'unified-progress-result.json'
PASSWORD = 'synthetic-session-password'
BOOKS = ('Fixture.epub', 'Fixture.cbz', 'Fixture.zip', 'Fixture.pdf')
LOCAL = (*BOOKS, 'Passages.txt', 'Passages.md', 'Sketch.rmdoc', 'Image.png', 'Film.mkv', 'External.mkv')
PROTECTED = ('Secret passage.epub', 'Secret film.mkv')
VIDEO_POSITION = 9000
TEXT_SCROLL = 640


def load_aes_localcrypt_package():
    return Path(__file__).with_name('unified-progress-credentials.b64').read_text().strip()


def write_result(path, result):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(path)


def solid_page(red, green, blue):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    row = b'\0' + bytes((red, green, blue)) * 120
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 120, 160, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(row * 160)) + chunk(b'IEND', b''))


def make_fixtures(shelf):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    from features.notebooks.notebook import Notebook

    shelf.mkdir(parents=True, exist_ok=True)
    passages = [f'Progress marker {i:03}. Three 😀 sentences mark this unique passage.' for i in range(240)]
    make_books(shelf, chapter_text=''.join(f'<p>{text}</p>' for text in passages))
    with ZipFile(shelf / 'Fixture.cbz', 'w') as archive:
        archive.writestr('001.png', solid_page(170, 24, 22))
        archive.writestr('002.png', solid_page(35, 171, 63))
        archive.writestr('003.png', solid_page(38, 61, 200))
    shutil.copyfile(shelf / 'Fixture.cbz', shelf / 'Fixture.zip')
    with PdfWriter() as writer:
        for color in ('1 0 0', '0 1 0', '0 0 1'):
            page = writer.add_blank_page(width=350, height=550)
            contents = DecodedStreamObject()
            contents.set_data(f'{color} rg 10 10 330 530 re f'.encode())
            page[NameObject('/Contents')] = writer._add_object(contents)
        writer.write(shelf / 'Fixture.pdf')
    (shelf / 'Passages.txt').write_text('\n\n'.join(passages), encoding='utf-8')
    (shelf / 'Passages.md').write_text('\n\n'.join('# ' + text for text in passages), encoding='utf-8')
    book = Notebook.new('Progress sketch')
    book.add_page()
    book.add_page()
    (shelf / 'Sketch.rmdoc').write_bytes(book.to_bytes())
    (shelf / 'Image.png').write_bytes(solid_page(35, 171, 63))
    fixture = Path(__file__).with_name('video-fixtures') / 'tracks.mkv'
    for title in ('Film.mkv', 'External.mkv'):
        shutil.copyfile(fixture, shelf / title)
    (shelf / 'External.fra.srt').write_text(
        '1\n00:00:00,500 --> 00:00:26,000\nSynthetic external captions\n', encoding='utf-8')


class UnifiedProgressProbe(LogisticsMobile):
    def on_running(self):
        start_native_check(self, type(self).probe)

    @property
    def shelf(self):
        return collection_path(self.private_root) / 'Progress Shelf'

    async def open_local(self, name, entry):
        path = self.shelf / name
        if entry == 'home':
            self.show_home()
            assert await reopen_file(self, {'type': 'local', 'path': str(path)}), name
        else:
            assert await self.show_files(location=('Local files', self.shelf.name))
            row = next(row for row in self.file_rows.values() if row['name'] == name)
            assert row['path'] == f'{self.shelf.name}/{name}', row
            self.browser_file_selected(row)
            assert await self.read_managed_file(), name

    async def close_reader(self, owner):
        session = owner.session.id
        self.request_reader_close(session)
        await until(lambda: session not in self.workspace.sessions)

    async def epub_location(self, owner, *, seek=None):
        # Bridge readiness announces script dispatch. WebKit may still be
        # bootstrapping about:blank, or a route change may replace the panel.
        panel = None
        sought_panel = None
        sample = {}
        try:
            async with asyncio.timeout(15):
                while True:
                    panel = getattr(owner, 'provider_epub_view', None)
                    if panel is None or owner.cloud_busy or getattr(owner, 'page_suspended', False):
                        await asyncio.sleep(.05)
                        continue
                    web = panel.webview
                    ready = await web.evaluate_javascript(
                        'Boolean(window.reader?.pagination && document.body?.textContent.includes("Progress marker 072."))')
                    if ready:
                        if seek is not None and panel is not sought_panel:
                            await web.evaluate_javascript(f'window.reader?.seek({seek})')
                            sought_panel = panel
                        measured = await web.evaluate_javascript('window.reader ? (' + MEASURE + ') : ""')
                        if measured:
                            sample = json.loads(measured)
                            if (sample['visible'] and (seek is None or sample['anchor'] == seek)
                                    and getattr(owner, 'provider_epub_view', None) is panel):
                                break
                    await asyncio.sleep(.05)
        except TimeoutError as error:
            raise AssertionError(('No visible EPUB anchor in the current native document', seek, sample)) from error
        assert self.visible_reader() == owner.session.id
        assert panel in owner.crypt_content.children
        return {key: sample[key] for key in ('anchor', 'index', 'visible')}

    async def capture_epub_display(self, owner, name, expected):
        cache = Path(self.paths.cache)
        request = cache / 'unified-progress-capture.json'
        completed = cache / (name + '.captured')
        completed.unlink(missing_ok=True)
        # Hold the exact displayed reader while CoreSimulator captures pixels
        # from the WebKit compositor, which app window capture can omit.
        write_result(request, {'name': name})
        try:
            await until(completed.is_file, timeout=45)
        except AssertionError as error:
            raise AssertionError(f'CoreSimulator did not acknowledge {name}') from error
        completed.unlink()
        measured = await self.epub_location(owner)
        assert measured['anchor'] == expected['anchor'], (name, expected, measured)
        return name + '.png'

    async def image_digest(self, owner):
        def canvas():
            if owner.cloud_busy:
                return None
            if owner.crypt_reader.kind == '.pdf':
                return owner.crypt_image if owner.crypt_image in owner.crypt_content.children else None
            spread = getattr(owner, 'provider_spread', None)
            if getattr(owner.crypt_reader, 'image_document', False):
                return owner.crypt_image if owner.crypt_image in owner.crypt_content.children else None
            return spread.canvas if spread in owner.crypt_content.children else None

        await until(lambda: canvas() is not None and canvas().image is not None
                    and canvas().layout.content_width > 0 and canvas().layout.content_height > 0)
        picture = canvas()._impl.picture
        await until(lambda: picture.window is not None and picture.image is not None)
        assert self.visible_reader() == owner.session.id
        assert picture.image.ptr.value == canvas().image._impl.native.ptr.value
        return sha256(canvas().image.data).hexdigest()

    async def book_case(self, name, previous, *, provider=None):
        entry = 'local' if previous is None else 'home'
        if provider is None:
            if previous is not None and name == 'Fixture.epub':
                self.show_home()
                recent, = [session for session, _ in self.recent_items()
                           if session.title == name and session.provider == 'file-reference']
                await self.recent_opener(recent)()
            else:
                await self.open_local(name, entry)
        else:
            assert await open_provider_document(self, provider, name)
        owner = self.private_sessions.active
        epub = name.endswith('.epub')
        if previous is None:
            if epub:
                before = await self.epub_location(owner)
                assert before['anchor'] == 0, before
                offset = owner.provider_epub_view.chapter.find('Progress marker 072.', 0)[0]
                expected = await self.epub_location(owner, seek=offset)
                assert expected['index'] > before['index'], expected
            else:
                before = await self.image_digest(owner)
                await owner.move_private_page(1)
                expected = await self.image_digest(owner)
                assert before != expected, 'Native canvas did not replace the first page'
        else:
            expected = previous['location']
        captures = []
        if epub and previous is not None and provider is None and sys.platform == 'ios':
            home = await self.epub_location(owner)
            assert home['anchor'] == expected['anchor'], (name, expected, home)
            captures.append(await self.capture_epub_display(owner, 'progress-fixture-epub-home-after', home))
        if provider is None:
            await self.open_local(name, 'home' if entry == 'local' else 'local')
            assert self.private_sessions.active is owner, 'Home and Local created separate reader sessions'
        else:
            assert owner._provider_progress.state.mode == 'encrypted'
        measured = await (self.epub_location(owner) if epub else self.image_digest(owner))
        if epub:
            assert measured['anchor'] == expected['anchor'], (name, expected, measured)
        else:
            assert measured == expected, (name, expected, measured)
        phase = 'before' if previous is None else 'after'
        safe_name = name.lower().replace(' ', '-').replace('.', '-')
        screenshot = f'progress-{safe_name}-{phase}'
        if epub and sys.platform == 'ios':
            captures.append(await self.capture_epub_display(owner, screenshot, measured))
        else:
            await capture_window(self, Path(self.paths.cache) / (screenshot + '.png'))
        if name.endswith('.pdf'):
            if previous is None:
                await until(lambda: owner._provider_progress.surface_ready)
                owner.crypt_image.set_zoom(2)
            await until(lambda: abs(owner.crypt_image.zoom_scale - 2) < .05)
        await self.close_reader(owner)
        return dict(location=measured, captures=captures)

    async def standalone_image_case(self, name, previous):
        await self.open_local(name, 'local' if previous is None else 'home')
        owner = self.private_sessions.active
        digest = await self.image_digest(owner)
        if previous is None:
            await until(lambda: owner._provider_progress.surface_ready)
            owner.crypt_image.set_zoom(2.25)
        else:
            assert digest == previous['image']
        await until(lambda: abs(owner.crypt_image.zoom_scale - 2.25) < .05)
        await self.close_reader(owner)
        return {'image': digest, 'zoom': 2.25}

    async def text_case(self, name, previous):
        await self.open_local(name, 'local' if previous is None else 'home')
        owner = self.private_sessions.active
        progress = owner._provider_progress
        markdown = name.endswith('.md')
        if markdown:
            if previous is None and owner.crypt_markdown_mode != 'preview':
                owner.toggle_private_preview()
            await until(lambda: owner.crypt_preview is not None and not owner.cloud_busy)
            widget = owner.crypt_preview
            async with asyncio.timeout(10):
                while not await widget.evaluate_javascript(
                    "Boolean(document.body?.textContent.includes('Progress marker 072'))"):
                    await asyncio.sleep(.1)
        else:
            widget = owner.crypt_text
        assert widget in owner.crypt_content.children
        mode = 'preview' if markdown else 'source'
        if previous is None:
            await until(lambda: progress.surface_ready and progress.surface_value() == (widget, mode))
        if markdown:
            if previous is None:
                await widget.evaluate_javascript(f'window.scrollTo(0,{TEXT_SCROLL})')

            async def scroll():
                return float(await widget.evaluate_javascript('window.scrollY'))
        else:
            from rubicon.objc import CGPoint
            native = widget._impl.native
            await until(lambda: float(native.contentSize.height) > TEXT_SCROLL * 2)
            if previous is None:
                native.setContentOffset(CGPoint(0, TEXT_SCROLL), animated=False)

            async def scroll():
                return float(native.contentOffset.y)
        offset = 0
        try:
            async with asyncio.timeout(10):
                while True:
                    offset = await scroll()
                    if abs(offset - TEXT_SCROLL) < 30:
                        break
                    await asyncio.sleep(.1)
            if previous is None:
                await until(lambda: progress.last_location is not None
                            and progress.last_location.get('mode') == mode
                            and progress.last_location.get('scroll', [0, 0])[1] > 0
                            and progress.state.write_status == 'saved'
                            and progress.pending is None, timeout=6)
        except (TimeoutError, AssertionError) as error:
            raise AssertionError((name, 'mounted scroll', offset, 'load', progress.state.load_status,
                                  'ready', progress.surface_ready, 'location', progress.last_location)) from error
        assert not owner.private_dirty()
        await self.close_reader(owner)
        return {'offset': offset}

    async def notebook_case(self, previous):
        from features.notebooks.notebook import Notebook
        path = self.shelf / 'Sketch.rmdoc'
        source = path.read_bytes()
        await self.open_local(path.name, 'local' if previous is None else 'home')
        panel = self.notebook_panel
        async with asyncio.timeout(10):
            while not await panel.web.evaluate_javascript('typeof window.notebookUpdate === "function"'):
                await asyncio.sleep(.1)
        if previous is None:
            await panel.perform({'op': 'page', 'index': 1})
            target = Notebook.read(source).pages[1].id
            index = 1
        else:
            target, index = previous['page_id'], 0
        async with asyncio.timeout(10):
            while True:
                measured = await panel.web.evaluate_javascript(
                    'typeof state === "undefined" ? "" : JSON.stringify([state.page_id, state.index])')
                if measured and json.loads(measured) == [target, index]:
                    break
                await asyncio.sleep(.1)
        assert not panel.document.dirty
        await self.close_reader(panel)
        assert path.read_bytes() == source, 'Page navigation rewrote notebook content'
        if previous is None:
            book = Notebook.read(source)
            book.move_page(1, 0)
            path.write_bytes(book.to_bytes())
        return {'page_id': target, 'index': index}

    async def video_case(self, name, previous, *, provider=None):
        from mobile.screen_privacy import native_value
        from .video_probe import start_playback

        if provider is None:
            await self.open_local(name, 'local' if previous is None else 'home')
        else:
            assert await open_provider_document(self, provider, name)
        owner = self.video_player
        state = owner.progress.state
        evidence = self.video_evidence[name]

        def status():
            return dict(allowed=owner.allowed(), hidden=owner.hidden, restricted=owner.restricted,
                        mode=state.mode.value, load=state.load_status.value,
                        write=state.write_status.value if state.write_status else None)

        evidence['open'] = status()
        assert owner.restricted == (provider is not None)
        assert state.mode == ('encrypted' if provider else 'local'), evidence
        start_playback(owner)
        player = owner.native.native.player
        await until(lambda: len(player.audioTracks) >= 2 and len(player.textTracks) >= 1
                    and native_value(player, 'hasVideoOut'), timeout=35)
        external = name == 'External.mkv'
        expected_subtitle = -1 if provider else None if external else 0
        controller = owner.native.native
        if previous is None:
            audio_key = str(controller.trackKey(player.audioTracks[1]))
            subtitle_key = str(controller.trackKey(player.textTracks[0]))
            assert audio_key and audio_key != str(controller.trackKey(player.audioTracks[0]))
            options = asdict(owner.controls.settings)
            # Simulate an obsolete audio index beside a valid stable key.
            # The decoder should select the identified track even after a
            # different enumeration/order. This is the native menu payload.
            options.update(audio_track=0, audio_track_key=audio_key, subtitle_track=0,
                           subtitle_track_key=subtitle_key, subtitle_delay_ms=350,
                           audio_delay_ms=-175, subtitle_scale=1.25)
            if external:
                # The title's chosen sidecar wins over the language fallback.
                options['subtitle_language'] = 'eng'
            await owner.controls.command('settings', json.dumps(options))
            evidence['settings'] = status()
            assert owner.controls.settings.audio_track_key == audio_key, evidence
            await until(lambda: state.write_status == 'saved', timeout=6)
            evidence['settings'] = status()
            await until(lambda: native_value(player.textTracks[0], 'isSelected'))
            if expected_subtitle == -1:
                options.update(subtitle_track=-1, subtitle_track_key='')
                await owner.controls.command('settings', json.dumps(options))
                evidence['off'] = status()
                assert owner.controls.settings.subtitle_track == -1, evidence
                await until(lambda: state.write_status == 'saved', timeout=6)
                evidence['off'] = status()
            if external:
                await owner.controls.command('subtitleSelect', 'External.fra.srt')
                evidence['external'] = status()
                await until(lambda: state.write_status == 'saved', timeout=6)
            if name == 'Film.mkv':
                await until(lambda: native_value(player, 'isSeekable') and not native_value(controller, 'controlsLocked'))
                owner.native.seek(VIDEO_POSITION)
        else:
            audio_key, subtitle_key = previous['audio_key'], previous['embedded_subtitle_key']
            assert owner.controls.settings.audio_track_key == audio_key
            assert owner.controls.settings.audio_track == 0
        def decoder_clock():
            time = native_value(player, 'time')
            if time is None:
                return 0
            value = native_value(time, 'value')
            if value is None or isinstance(value, (int, float)):
                return int(value or 0)
            return int(native_value(value, 'longLongValue'))

        target = VIDEO_POSITION if previous is None else previous['position']
        try:
            await until(lambda: abs(decoder_clock() - target) < 1600
                        and abs(owner.progress.position - target) < 2400,
                        timeout=18 if previous is None else 5)
        except AssertionError as error:
            evidence['clock'] = dict(decoder=decoder_clock(), checkpoint=owner.progress.position,
                                     displayed=owner.native.position()[0], target=target,
                                     playing=bool(native_value(player, 'isPlaying')))
            raise AssertionError((name, 'decoder did not confirm the requested position', evidence)) from error
        position = decoder_clock()
        assert abs(position - target) < 2400, (name, target, position)
        assert abs(owner.progress.position - position) < 2400, (name, position, owner.progress.position)
        if not external:
            owner.native.pause()
            await until(lambda: not native_value(player, 'isPlaying'))
        await until(lambda: [str(controller.trackKey(track)) for track in player.audioTracks
                             if native_value(track, 'isSelected')] == [audio_key])
        def selected_captions():
            return [str(controller.trackKey(track)) for track in player.textTracks
                    if native_value(track, 'isSelected')]

        if external:
            assert Path(owner.controls.settings.subtitle_file).name == 'External.fra.srt'
            assert owner.controls.settings.subtitle_track is None
            try:
                await until(lambda: len(player.textTracks) >= 2 and len(selected_captions()) == 1
                            and selected_captions() != [subtitle_key])
            except AssertionError as error:
                selected = selected_captions()
                evidence['external_decoder'] = dict(
                    tracks=len(player.textTracks), selected=len(selected),
                    embedded_selected=subtitle_key in selected,
                    attachment_pending=bool(native_value(controller, 'pendingSubtitleURL')))
                raise AssertionError(('External subtitle was saved but was not selected by the decoder',
                                      evidence['external_decoder'])) from error
            owner.native.pause()
            await until(lambda: not native_value(player, 'isPlaying'))
        else:
            assert owner.controls.settings.subtitle_file == ''
            await until(lambda: selected_captions() == ([] if expected_subtitle == -1 else [subtitle_key]))
        assert int(native_value(player, 'currentVideoSubTitleDelay')) == 350000
        assert int(native_value(player, 'currentAudioPlaybackDelay')) == -175000
        assert abs(float(native_value(player, 'currentSubTitleFontScale')) - 1.25 * 20 / 22) < .06
        player = controller = None
        await owner.close()
        return dict(position=owner.progress.position, displayed=position,
                    audio_key=audio_key, embedded_subtitle_key=subtitle_key,
                    subtitle=expected_subtitle, external=external, subtitle_delay=350, audio_delay=-175, scale=1.25)

    async def leave_epub_at_checkpoint(self):
        # Exercise the continuous checkpoint before OS termination without
        # closing the reader or invoking a test-only persistence write.
        await self.open_local('Fixture.epub', 'local')
        owner = self.private_sessions.active
        await self.epub_location(owner)
        panel = owner.provider_epub_view
        target = panel.chapter.find('Progress marker 115.', 0)[0]
        location = await self.epub_location(owner, seek=target)
        progress = owner._provider_progress
        await until(lambda: progress.last_location is not None
                    and progress.last_location.get('offset') == target
                    and progress.state.write_status == 'saved'
                    and progress.pending is None)
        assert self.visible_reader() == owner.session.id
        return dict(location=location, left_open_for_termination=True)

    async def unlock_crypt(self, initial):
        from features.rclone.localcrypt.mobile.resources import encrypted_storage

        self.show_cloud(present=False)
        task = getattr(self, 'cloud_restore_task', None)
        if task is not None:
            await task
        values = dict(package=load_aes_localcrypt_package(), package_name='ProgressFixture.zip', session_only=True)
        if not initial:
            try:
                self.cloud_client.request('import', password='wrong-password', **values)
            except (OSError, ValueError, RuntimeError):
                pass
            else:
                raise AssertionError('Wrong credential password unlocked the fixture')
        self.cloud_client.request('import', password=PASSWORD, **values)
        assert any(not record.get('saved') and record.get('document_cache_id')
                   for record in self.cloud_client.package_records), 'Synthetic ZIP did not establish password authority'
        provider = encrypted_storage(self.private_root / 'unified-progress-crypt', self.cloud_client, 'Secret')
        if initial:
            for name, original in zip(PROTECTED, ('Fixture.epub', 'Film.mkv')):
                provider.create_file(name, BytesIO((self.shelf / original).read_bytes()))
        return provider

    def check_ciphertext(self):
        positions = self.private_root / 'ReaderPositions'
        seen = set()
        for path in positions.glob('*.zip'):
            assert len(path.stem) == 64
            with ZipFile(path) as archive:
                (record,) = archive.infolist()
                assert record.flag_bits & 1 and record.compress_type == 99
                assert b'\x01\x99\x07\x00\x02\x00AE\x03' in record.extra
            with path.open('rb') as stream:
                try:
                    self.cloud_client.request('file_archive', fd=stream.fileno(), password='wrong-password',
                                              member=record.filename)
                except (OSError, ValueError, RuntimeError):
                    pass
                else:
                    raise AssertionError('Wrong password could read a LocalCrypt checkpoint')
            with path.open('rb') as stream:
                result = self.cloud_client.request('file_archive', fd=stream.fileno(), password=PASSWORD,
                                                   member=record.filename)
            envelope = json.loads(base64.b64decode(result['data'], validate=True))
            seen.add(envelope['kind'])
        for path in positions.rglob('*'):
            if path.is_file():
                data = path.read_bytes()
                for marker in (b'Secret passage', b'Secret film', b'Progress marker 072.'):
                    assert marker not in data, path.name
        return seen

    async def probe(self):
        cache = Path(self.paths.cache)
        checkpoint = cache / 'unified-progress-checkpoint.json'
        previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
        cases = {}
        external_only = os.getenv('LOGISTICS_PROGRESS_CASE') == 'external-subtitle'
        titles = ('External.mkv',) if external_only else (*LOCAL, *PROTECTED)
        scope = 'external-subtitle' if external_only else 'full-matrix'
        self.video_evidence = {name: {} for name in titles if name.endswith('.mkv')}
        result = dict(success=False, phase='checkpoint' if previous is None else 'restarted',
                      pid=os.getpid(), scope=scope, cases=cases, video_evidence=self.video_evidence)
        try:
            await until(lambda: not getattr(self, '_startup_in_progress', False), timeout=40)
            self.preferences.save(restore_last_document='false', clear_unmodified_documents_on_restart='false',
                                  comic_layout='single')
            if previous is None:
                make_fixtures(self.shelf)
            else:
                assert previous['pid'] != os.getpid(), 'Expected an OS process restart'
                assert previous['scope'] == scope, 'Progress probe scope changed during restart'
            provider = None
            for name in titles:
                print(f'UNIFIED_PROGRESS {result["phase"]} {name}', flush=True)
                prior = previous['cases'].get(name) if previous else None
                if prior is not None and 'error' in prior:
                    cases[name] = dict(error='Initial process did not establish a valid position')
                    continue
                try:
                    # EPUB may hold two separate mounted routes for system
                    # compositor capture. Keep its I/O budget independent.
                    async with asyncio.timeout(140 if name.endswith('.epub') else 50):
                        if name in PROTECTED:
                            provider = provider or await self.unlock_crypt(previous is None)
                        if name.endswith('.mkv'):
                            location = await self.video_case(name, prior, provider=provider)
                        elif name.endswith(('.txt', '.md')):
                            location = await self.text_case(name, prior)
                        elif name.endswith('.rmdoc'):
                            location = await self.notebook_case(prior)
                        elif name.endswith('.png'):
                            location = await self.standalone_image_case(name, prior)
                        else:
                            location = await self.book_case(name, prior, provider=provider)
                    cases[name] = location
                except Exception:
                    cases[name] = dict(error=traceback.format_exc())
                    video = getattr(self, 'video_player', None)
                    if video is not None:
                        await video.close()
            if not external_only:
                try:
                    encrypted = self.check_ciphertext()
                    for kind in ('.epub', 'video'):
                        cases[f'LocalCrypt ciphertext {kind}'] = (dict(encrypted=True, wrong_password_rejected=True)
                            if kind in encrypted else dict(error=f'Missing encrypted checkpoint for {kind}'))
                except Exception:
                    cases['LocalCrypt ciphertext audit'] = dict(error=traceback.format_exc())
            if previous is None:
                if not external_only and 'error' not in cases['Fixture.epub']:
                    try:
                        cases['Fixture.epub'] = await self.leave_epub_at_checkpoint()
                    except Exception:
                        cases['Fixture.epub'] = dict(error=traceback.format_exc())
                write_result(checkpoint, result)
                # Continue to the second process even if individual cases
                # failed, so other format results survive.
                result['success'] = True
            else:
                result['success'] = all('error' not in case
                                        for phase in (previous['cases'], cases)
                                        for case in phase.values())
                if not result['success']:
                    result['error'] = 'One or more progress cases failed; see cases in the native reports.'
        except Exception:
            result['error'] = traceback.format_exc()
        write_result(cache / RESULT, result)


def main():
    return UnifiedProgressProbe('Unified Progress QA', BUNDLE)
