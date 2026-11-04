"""Disposable native acceptance for feedback 15–17, including slow and absent data."""
import asyncio
import json
from pathlib import Path
import struct
from threading import Event
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import zlib

import toga
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from commonUtils.ui.native.speech import NativeSpeech
from features.notes_library.notes_links import connections
from mobile.app import LogisticsMobile
from mobile.obsidian import open_vault
from . import start_native_check
from .fixtures import capture_window
from .rotation_checks import rotate

TEST_STAGE = TestStage.REGRESSION
RESULT = 'links-images-voices-result.json'


def fixture_png():
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    pixels = b''.join(b'\0' + b'\x27\xa5\xd8' * 96 for _ in range(48))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 96, 48, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


class LinksImagesVoicesProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('feedback-15-17-' + uuid4().hex)
        (Path(self.paths.cache) / 'feedback-progress.json').write_text(json.dumps(dict(stage='native-startup')))
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def until(self, condition, message, timeout=15):
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                raise AssertionError(message)
            await asyncio.sleep(.05)

    async def screenshot(self, name):
        await asyncio.sleep(.2)
        await capture_window(self, Path(self.paths.cache) / ('feedback-' + name + '.png'))

    async def tap(self, button):
        if type(self._impl).__module__.startswith('toga_iOS.'):
            button._impl.native.sendActionsForControlEvents(1 << 6)
        else:
            assert button._impl.native.performClick()
        await asyncio.sleep(.15)

    def record_stage(self, stage):
        self.report['stage'] = stage
        (Path(self.paths.cache) / 'feedback-progress.json').write_text(json.dumps(self.report, indent=2))

    async def links(self, root):
        (root / 'Home.md').write_text('# Home\n\n[Other](Other.md) [Missing](Missing.md)')
        (root / 'Other.md').write_text('[Home](Home.md)')
        owner = await open_vault(self, LocalFiles(root), '', 'documents')
        release, started = Event(), Event()
        task = None
        def slow(*args, **kwargs):
            started.set()
            if not release.wait(20):
                raise TimeoutError('Backlink fixture was not released')
            return connections(*args, **kwargs)
        try:
            assert await owner.open_note('Home.md')
            with patch('features.notes_library.notes_links.connections', side_effect=slow):
                task = self.loop.create_task(owner.show_links(toggle=False))
                await self.until(lambda: started.is_set() or task.done(), 'Backlink scan did not start')
                if task.done() and not started.is_set():
                    await task
                    raise AssertionError(dict(valid=owner.valid(), path=owner.path, side=owner.sidebar.side,
                        links=[getattr(row, 'text', type(row).__name__) for row in owner.link_rows.children]))
                assert owner.links_tab == 'outgoing'
                assert owner.links_scroll.content is owner.link_rows
                assert owner.link_rows.children[0].text == 'Outgoing links (1)'
                await self.screenshot('15-outgoing')
                await self.tap(owner.link_tab_buttons['incoming'])
                assert owner.links_scroll.content is owner.backlink_rows
                assert owner.backlink_rows.children[0].text == 'Finding backlinks…'
                await self.screenshot('15-loading')
                release.set()
                await task
            assert owner.backlink_rows.children[0].text == 'Backlinks (1)'
            await self.screenshot('15-backlinks')
            for pose in ('landscape-left', 'portrait'):
                await rotate(self, pose)
                await self.tap(owner.link_tab_buttons['outgoing'])
                assert owner.links_scroll.content is owner.link_rows
                assert owner.link_rows.children[0].text == 'Outgoing links (1)'
                await self.screenshot('15-' + pose)
                await self.tap(owner.link_tab_buttons['incoming'])
                assert owner.backlink_rows.children[0].text == 'Backlinks (1)'
            target = next(row for row in owner.backlink_rows.children if isinstance(row, toga.Button))
            await self.tap(target)
            await self.until(lambda: owner.path == 'Other.md', 'Backlink activation did not navigate')
            self.report['task15'] = dict(success=True, outgoing_before_backlinks=True,
                native_tab_events=True, link_navigation=True, rotations=['landscape-left', 'portrait'])
        finally:
            release.set()
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
            owner.dispose()

    async def images(self, root):
        (root / 'Texture.PNG').write_bytes(fixture_png())
        (root / 'Broken.png').write_bytes(b'Not an image')
        (root / 'Note.md').write_text('Plain text')
        await self.show_files(local_root=True)
        browser = self.file_browser
        provider = LocalFiles(root)
        self.file_provider, self.file_path = provider, ''
        self.populate_file_browser(provider.list(), location=('QA local', ''))
        await self.until(lambda: bool(browser.native_list.data), 'Native file rows missing')
        row = next(row for row in browser.native_list.data if row.entry.label == 'Texture.PNG')
        browser._row_visible(row)
        await self.until(lambda: row.thumbnail, 'Local image row did not receive a thumbnail')
        await self.screenshot('16-list')
        browser.mode = 'Tiles'
        browser.render()
        await self.until(lambda: any(key[0].name == 'Texture.PNG' for key in browser.icons), 'Tile thumbnail missing')
        await self.screenshot('16-tiles')
        entry = next(entry for entry in browser.entries if entry.label == 'Texture.PNG')
        await browser.select(entry)
        self.show_file_details()
        await self.until(lambda: any(isinstance(view, toga.ImageView) for view in browser.info.children),
                         'File information thumbnail missing')
        await self.screenshot('16-information')
        await rotate(self, 'landscape-left')
        await self.screenshot('16-landscape-left')
        await rotate(self, 'portrait')
        loader = browser.thumbnail
        await asyncio.gather(*tuple(browser.tasks), return_exceptions=True)
        image_row = provider.entry('Texture.PNG')
        with patch('commonUtils.filesystem.network.is_network_location', return_value=True), \
                patch.object(provider, 'open', side_effect=AssertionError('Network content was opened')):
            assert await asyncio.to_thread(loader, image_row, (160, 160), lambda: False) == b''
        assert await asyncio.to_thread(loader, provider.entry('Broken.png'), (160, 160), lambda: False) == b''
        virtual = SimpleNamespace(root=Path('/virtual/cloud'), relative=lambda path: str(path),
                                  open=lambda *args: (_ for _ in ()).throw(AssertionError('Cloud content was opened')))
        self.file_provider = virtual
        self.populate_file_browser([image_row], location=('QA cloud', ''))
        assert browser.thumbnail is None
        self.file_provider = provider
        self.populate_file_browser(provider.list(), location=('QA local', ''))
        self.report['task16'] = dict(success=True, native_row_thumbnail=True, tile_thumbnail=True,
            information_thumbnail=True, network_no_reads=True, cloud_no_loader=True, corrupt_fallback=True)

    async def voices(self):
        self.preferences.save(speech_voice='QA removed voice')
        self.show_settings()
        self.settings_navigation.choose('Read aloud')
        await asyncio.wait_for(asyncio.shield(self.speech_voice_load_task), 20)
        assert self.speech_voice_choice.value == 'System default'
        await self.screenshot('17-settings')
        self.settings_navigation.choose('Appearance')
        self.settings_navigation.choose('Read aloud')
        await asyncio.wait_for(asyncio.shield(self.speech_voice_load_task), 20)
        assert self.speech_voice_choice.value == 'System default'
        engine = NativeSpeech(self.loop)
        outcome = dict(automatic_load=True, refreshed_on_reopen=True, missing_saved_choice='System default')
        try:
            await self.until(lambda: engine.ready or bool(engine.error), 'Native speech discovery timed out', timeout=17)
            outcome.update(installed_voices=len(engine.voices), system_default=engine.default_voice,
                           native_engine_error=engine.error)
            if engine.ready:
                started, failed = Event(), Event()
                engine.started = lambda *args: started.set()
                engine.failed = lambda *args: failed.set()
                engine.speak('Disposable system voice fallback check.', 'QA removed voice', 1.0, 'qa-default')
                await self.until(lambda: started.is_set() or failed.is_set(), 'Native speech did not start', timeout=20)
                assert started.is_set() and not failed.is_set(), 'Native fallback playback failed'
                outcome['native_default_playback'] = True
            else:
                outcome['native_unavailable_feedback'] = True
        finally:
            engine.close()
        # A simulator may ship no offline voice data. Still exercise the retained
        # native controls and the missing-preference language fallback deterministically.
        from features.books.mobile.speech_view import ReadAloudPanel
        class InstalledFixture:
            ready, error, default_voice = True, '', 'en-US · QA system default'
            voices = {'en-US · QA system default': object()}
            voice_for_language = NativeSpeech.voice_for_language
            def __init__(self):
                self.calls = []
            def speak(self, *args):
                self.calls.append(args)
            def stop(self):
                pass
            def close(self):
                pass
        fixture = InstalledFixture()
        async def source():
            return SimpleNamespace(text='Ein deutsches Buch.', language='de'), 0, None
        panel = ReadAloudPanel(loop=self.loop, source=source, on_range=lambda *args: None,
                              close=lambda *args: None, engine=fixture, app=self)
        try:
            await panel.ready_task
            assert panel.missing_saved_voice
            await panel.play()
            assert fixture.calls[-1][1] == fixture.default_voice
            outcome['missing_saved_language_fallback'] = True
        finally:
            panel.dispose()
        self.report['task17'] = dict(success=True, **outcome)

    async def probe(self):
        self.report = dict(success=False, backend=type(self._impl).__module__)
        try:
            await asyncio.sleep(.5)
            root = self.private_root / 'FeedbackFixtures'
            root.mkdir(parents=True, exist_ok=True)
            self.record_stage('links')
            await self.links(root)
            self.record_stage('images')
            await self.images(root)
            self.record_stage('voices')
            await self.voices()
            self.report.update(success=True, stage='complete')
        except Exception:
            self.report['error'] = traceback.format_exc()
            try:
                await self.screenshot('failure')
            except Exception:
                pass
        finally:
            (Path(self.paths.cache) / RESULT).write_text(json.dumps(self.report, indent=2))


def main():
    return LinksImagesVoicesProbe('Links Images Voices QA', 'io.github.ispaure.logisticsnotebookqa')
