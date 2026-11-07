"""Native Android EPUB restart and LocalCrypt checkpoint acceptance."""

import asyncio
import base64
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import traceback
from zipfile import ZipFile

from commonUtils.testing.stages import TestStage
from services.documents.mobile_storage import open_provider_document
from .fixtures import make_books
from .unified_progress_probe import (
    BUNDLE, PASSWORD, RESULT, UnifiedProgressProbe, load_aes_localcrypt_package, solid_page, write_result,
)
from .video_probe import until

TEST_STAGE = TestStage.REGRESSION
LOCAL = 'Fixture.epub'
PRIVATE_COMIC = 'Secret comic.cbz'
PRIVATE_EPUB = 'Secret passage.epub'


class AndroidProgressProbe(UnifiedProgressProbe):
    async def protected_provider(self, initial):
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
                raise AssertionError('Wrong password unlocked the credential package')
        self.cloud_client.request('import', password=PASSWORD, **values)
        assert any(not record.get('saved') and record.get('document_cache_id')
                   for record in self.cloud_client.package_records), 'Synthetic ZIP did not establish password authority'
        provider = encrypted_storage(self.private_root / 'unified-progress-crypt', self.cloud_client, 'Secret')
        if initial:
            for name, fixture in ((PRIVATE_COMIC, 'Fixture.cbz'), (PRIVATE_EPUB, LOCAL)):
                provider.create_file(name, BytesIO((self.shelf / fixture).read_bytes()))
        return provider

    async def protected_comic(self, provider, initial):
        assert await open_provider_document(self, provider, PRIVATE_COMIC)
        owner = self.private_sessions.active
        before, digest = await self.comic_page(owner)
        if initial:
            assert before == 0, before
            await owner.move_private_page(1)
            page, changed = await self.comic_page(owner)
            assert page == 1 and digest != changed, (page, changed)
            await self.wait_for_checkpoint(owner, 'page', 1)
        else:
            assert before == 1, before
        member = owner.crypt_reader.pages[1]
        await self.close_reader(owner)
        return self.check_ciphertext(PRIVATE_COMIC, page=1, resource=member)

    async def protected_epub(self, provider, initial):
        assert await open_provider_document(self, provider, PRIVATE_EPUB)
        owner = self.private_sessions.active
        diagnostics = {}
        try:
            await until(lambda: getattr(owner, 'provider_epub_view', None) is not None and not owner.cloud_busy)
            panel = owner.provider_epub_view
            await until(lambda: panel.webview._chapter_bridge.ready and panel.position_ready)
            native = panel.webview._impl.native
            diagnostics.update(
                attached=bool(native.isAttachedToWindow()), shown=bool(native.isShown()),
                width=int(native.getWidth()), height=int(native.getHeight()),
                visible=owner._provider_progress.visible(),
            )
            assert diagnostics['attached'] and diagnostics['shown'] and diagnostics['visible'], diagnostics
            target, _ = panel.chapter.find('Progress marker 072.', 0)
            if initial:
                panel.seek(target)
                await until(lambda: panel.offset == target)
            location = await self.epub_location(owner)
            assert location['anchor'] == target, location
            if initial:
                await self.wait_for_checkpoint(owner, 'offset', target)
        except Exception as error:
            panel = getattr(owner, 'provider_epub_view', None)
            diagnostics.update(
                mounted=panel in owner.crypt_content.children,
                bridge_ready=bool(panel and panel.webview._chapter_bridge.ready),
                position_ready=bool(getattr(panel, 'position_ready', False)),
                replaced=bool(panel is not None and 'native' in locals() and panel.webview._impl.native is not native),
                suspended=bool(getattr(owner, 'page_suspended', False)),
                reader_visible=self.visible_reader() == owner.session.id,
                encryption_mode=owner._provider_progress.state.mode,
            )
            raise AssertionError(diagnostics) from error
        await self.close_reader(owner)
        return self.check_ciphertext(PRIVATE_EPUB, offset=target)

    def check_ciphertext(self, name, **expected):
        positions = self.private_root / 'ReaderPositions'
        for path in positions.rglob('*.json'):
            assert name.encode() not in path.read_bytes(), path.name
        for encrypted in positions.glob('*.zip'):
            assert len(encrypted.stem) == 64
            ciphertext = encrypted.read_bytes()
            assert name.encode() not in ciphertext
            with ZipFile(encrypted) as archive:
                record, = archive.infolist()
                assert record.flag_bits & 1 and record.compress_type == 99
                assert b'\x01\x99\x07\x00\x02\x00AE\x03' in record.extra
            with encrypted.open('rb') as stream:
                response = self.cloud_client.request('file_archive', fd=stream.fileno(), password=PASSWORD,
                                                     member=record.filename)
            checkpoint = json.loads(base64.b64decode(response['data']))
            if checkpoint['kind'] != Path(name).suffix:
                continue
            assert all(checkpoint['state'].get(key) == value for key, value in expected.items())
            with encrypted.open('rb') as stream:
                try:
                    self.cloud_client.request('file_archive', fd=stream.fileno(), password='wrong-password',
                                              member=record.filename)
                except (OSError, ValueError, RuntimeError):
                    pass
                else:
                    raise AssertionError('Wrong password could read LocalCrypt checkpoint')
            assert encrypted.read_bytes() == ciphertext
            return dict(encrypted=True, wrong_password_rejected=True, locator_verified=True,
                        ciphertext_sha256=sha256(ciphertext).hexdigest())
        raise AssertionError('Missing encrypted checkpoint for ' + Path(name).suffix)

    async def comic_page(self, owner):
        def mounted():
            spread = getattr(owner, 'provider_spread', None)
            return (spread is not None and spread in owner.crypt_content.children
                    and spread.canvas.image is not None and spread.canvas.layout.content_width > 0)

        await until(lambda: mounted() and not owner.cloud_busy)
        assert self.visible_reader() == owner.session.id
        return owner._provider_displayed_index, sha256(owner.provider_spread.canvas.image.data).hexdigest()

    async def wait_for_checkpoint(self, owner, field, target):
        progress = owner._provider_progress
        assert progress.state.mode == 'encrypted', progress.state.mode
        try:
            await until(lambda: (progress.last_location or {}).get(field) == target
                        and progress.state.write_status == 'saved' and progress.pending is None, timeout=12)
        except AssertionError as error:
            raise AssertionError(dict(
                mode=progress.state.mode, load=progress.state.load_status, write=progress.state.write_status,
                displayed_page=owner._provider_displayed_index,
                accepted_target=(progress.last_location or {}).get(field) == target,
                visible=progress.visible(), pending=progress.pending is not None,
                error=str(progress.state.write_error or ''),
            )) from error

    async def probe(self):
        cache = Path(self.paths.cache)
        before = cache / 'android-unified-progress-checkpoint.json'
        previous = json.loads(before.read_text()) if before.exists() else None
        initial = previous is None
        result = dict(success=False, phase='checkpoint' if initial else 'restarted', pid=os.getpid(), cases={})
        try:
            await until(lambda: not getattr(self, '_startup_in_progress', False), timeout=60)
            self.preferences.save(restore_last_document='false', clear_unmodified_documents_on_restart='false',
                                  comic_layout='single')
            if initial:
                self.shelf.mkdir(parents=True, exist_ok=True)
                make_books(self.shelf, chapter_text=''.join(
                    f'<p>Progress marker {i:03}. Three 😀 sentences mark this unique passage.</p>'
                    for i in range(240)))
                with ZipFile(self.shelf / 'Fixture.cbz', 'w') as archive:
                    archive.writestr('001.png', solid_page(170, 24, 22))
                    archive.writestr('002.png', solid_page(35, 171, 63))
            else:
                assert previous['pid'] != os.getpid()
            provider = await self.protected_provider(initial)
            for name, check in ((PRIVATE_COMIC, self.protected_comic), (PRIVATE_EPUB, self.protected_epub)):
                try:
                    async with asyncio.timeout(85):
                        result['cases'][name] = await check(provider, initial)
                except Exception:
                    result['cases'][name] = dict(error=traceback.format_exc())
                    owner = self.private_sessions.active
                    if owner is not None:
                        await self.close_reader(owner)
            try:
                async with asyncio.timeout(60):
                    if initial:
                        await self.book_case(LOCAL, None)
                        result['cases'][LOCAL] = await self.leave_epub_at_checkpoint()
                    else:
                        prior = previous['cases'][LOCAL]
                        assert 'error' not in prior, 'Initial process did not establish a local checkpoint'
                        result['cases'][LOCAL] = await self.book_case(LOCAL, prior)
            except Exception:
                result['cases'][LOCAL] = dict(error=traceback.format_exc())
            result['success'] = initial or all(
                'error' not in case for phase in (previous['cases'], result['cases']) for case in phase.values()
            )
            if not result['success']:
                result['error'] = 'A native Android restart or ciphertext assertion failed. See the per-case evidence.'
            if initial:
                write_result(before, result)
        except Exception:
            result['error'] = traceback.format_exc()
        write_result(cache / RESULT, result)


def main():
    return AndroidProgressProbe('Unified Progress QA', BUNDLE)
