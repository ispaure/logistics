"""Exercise reader return and native paging with disposable local and encrypted files."""

import asyncio
from io import BytesIO
from pathlib import Path
import traceback
from zipfile import ZipFile

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from commonUtils.ui.native.keyboard import native_value
from mobile.app import LogisticsMobile
from services.documents.mobile_storage import open_provider_document

from . import start_native_check
from .fixtures import capture_window, make_books
from .reader_flow_probe import pdf_bytes
from .unified_progress_probe import PASSWORD, load_aes_localcrypt_package, solid_page, write_result
from .web_checks import wait_for_text

TEST_STAGE = TestStage.REGRESSION
RESULT = 'reader-appearance-result.json'


async def until(condition):
    async with asyncio.timeout(20):
        while not condition():
            await asyncio.sleep(.1)


class ReaderAppearanceProbe(LogisticsMobile):
    def on_running(self):
        start_native_check(self, type(self).probe)

    async def back(self):
        if self.routes.apple:
            destination = self.native_host.state.destination
            navigation = self.native_host.adapter.navigation_for(destination)
            navigation.popViewControllerAnimated(False)
        else:
            from org.beeware.android import MainActivity
            MainActivity.singletonThis.getOnBackPressedDispatcher().onBackPressed()
        await asyncio.sleep(.3)

    async def press(self, button):
        if self.routes.apple:
            item = getattr(button, '_ios_action_item', None)
            if item is not None:
                assert item.isEnabled()
                item.target.performSelector(item.action, withObject=item)
            else:
                button._impl.native.sendActionsForControlEvents(64)
        else:
            assert button._impl.native.performClick()
        await asyncio.sleep(.2)

    async def swipe(self, canvas, direction):
        native = canvas._impl.native
        assert canvas.image is not None
        if self.routes.apple:
            assert native_value(native.window) is not None and canvas._impl.picture.image is not None
            swipe = next(item for item in canvas._impl.swipes
                         if int(item.direction) == (2 if direction > 0 else 1))
            assert swipe.view == native and swipe.isEnabled()
            native.pageSwipe(swipe)
        else:
            from android.os import SystemClock
            from android.view import MotionEvent
            assert native.isAttachedToWindow() and native.isShown() and native.getDrawable() is not None
            width, height = native.getWidth(), native.getHeight()
            start, end = (.75, .25) if direction > 0 else (.25, .75)
            down = SystemClock.uptimeMillis()
            for action, x in ((0, start), (2, .5), (1, end)):
                event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, x * width, .5 * height, 0)
                try:
                    assert native.dispatchTouchEvent(event)
                finally:
                    event.recycle()
                await asyncio.sleep(.04)

    async def turn_comic(self, owner, direction, index):
        await until(lambda: not owner.cloud_busy and owner._provider_progress.worker is None)
        await self.swipe(owner.provider_spread.canvas, direction)
        await until(lambda: not owner.cloud_busy and owner._provider_displayed_index == index)

    async def open_reader(self, provider, filename):
        assert await self.show_files(local_root=True)
        assert await open_provider_document(self, provider, filename)
        owner = self.private_sessions.active
        await until(lambda: self.visible_reader() == owner.session.id and not owner.cloud_busy)
        return owner

    async def close_reader(self, owner):
        assert self.request_reader_close(owner.session.id)
        await until(lambda: owner.session.id not in self.workspace.sessions)

    async def comic(self, provider, label):
        self.preferences.save(comic_layout='single', comic_split_wide='true')
        owner = await self.open_reader(provider, 'Fixture.cbz')
        await self.turn_comic(owner, 1, 1)
        for action in ('cancel', 'unchanged', 'changed', 'cancel'):
            await until(lambda: not owner.cloud_busy and owner._provider_progress.worker is None)
            owner.show_provider_layout()
            panel = owner.provider_appearance
            assert self.visible_reader() is None
            if action == 'cancel':
                panel.layout_choice.value = 'double'
                await self.back()
                assert self.preferences.values['comic_layout'] != 'double'
            else:
                if action == 'changed':
                    panel.split_wide.value = False
                await self.press(panel.content.children[-1])
            await until(lambda: self.visible_reader() == owner.session.id and not owner.cloud_busy)
            assert owner._provider_displayed_index == 1
            await self.turn_comic(owner, -1, 0)
            await self.turn_comic(owner, 1, 1)
        assert self.preferences.values['comic_split_wide'] == 'false'
        if label == 'localcrypt':
            owner.show_provider_layout()
            privacy = self.screen_privacy
            privacy.conceal()
            privacy.reveal()
            await until(lambda: self.main_window.content is privacy.lock_view and not privacy.inactive)
            self.private_sessions.suspend()  # Exercise the return after a hidden page was released.
            privacy.lock_password.value = 'invalid'
            await privacy.unlock()
            assert self.main_window.content is privacy.lock_view and owner.page_suspended
            privacy.lock_password.value = PASSWORD
            await privacy.unlock()
            await until(lambda: self.main_window.content is not privacy.lock_view)
            await self.back()
            await until(lambda: not owner.page_suspended and self.visible_reader() == owner.session.id)
            assert owner._provider_displayed_index == 1
            await self.turn_comic(owner, -1, 0)
            await self.turn_comic(owner, 1, 1)
        await self.close_reader(owner)
        owner = await self.open_reader(provider, 'Fixture.cbz')
        assert owner._provider_displayed_index == 1
        await capture_window(self, self.cache / f'appearance-{label}-comic.png')
        await self.turn_comic(owner, 1, 2)
        await self.turn_comic(owner, -1, 1)
        await self.close_reader(owner)

    async def epub(self, provider, label):
        owner = await self.open_reader(provider, 'Fixture.epub')
        await wait_for_text(owner.provider_epub_view.webview, 'Native EPUB first')
        await self.press(owner.next_page)
        await wait_for_text(owner.provider_epub_view.webview, 'Native EPUB second')
        for change in (False, True):
            assert owner.show_provider_layout()
            if change:
                page = self.routes.body('settings').children[-1].content
                page.epub_controls['reading_margin'].value = '24'
            await self.back()
            await until(lambda: self.visible_reader() == owner.session.id and not owner.cloud_busy)
            if getattr(owner, '_epub_resume_task', None) is not None:
                await owner._epub_resume_task
            await wait_for_text(owner.provider_epub_view.webview, 'Native EPUB second')
        await capture_window(self, self.cache / f'appearance-{label}-epub.png')
        await self.press(owner.previous_page)
        await wait_for_text(owner.provider_epub_view.webview, 'Native EPUB first')
        await self.press(owner.next_page)
        await wait_for_text(owner.provider_epub_view.webview, 'Native EPUB second')
        await self.close_reader(owner)

    async def wait_for_pdf(self, owner, index):
        scroll = owner.crypt_image.scroll
        async with asyncio.timeout(20):
            while True:
                visible = await scroll.js(f"""JSON.stringify(Boolean(window.pdf?.state().page === {index}
                    && document.querySelector('.sheet[data-page="{index}"] img')?.naturalWidth))""")
                if visible and owner._provider_displayed_index == index:
                    return
                await asyncio.sleep(.1)

    async def pdf(self, provider, label):
        owner = await self.open_reader(provider, 'Fixture.pdf')
        await self.wait_for_pdf(owner, 0)
        await self.press(owner.next_page)
        await self.wait_for_pdf(owner, 1)
        assert owner.show_provider_layout() is None  # PDF has no Appearance action.
        assert self.visible_reader() == owner.session.id
        # Exercise an actual secondary reader route above the PDF.
        owner.show_private_tools()
        assert self.visible_reader() is None
        await self.back()
        await until(lambda: self.visible_reader() == owner.session.id and not owner.page_suspended
                    and not owner.cloud_busy)
        await self.wait_for_pdf(owner, 1)
        await capture_window(self, self.cache / f'appearance-{label}-pdf.png')
        await self.press(owner.next_page)
        await self.wait_for_pdf(owner, 2)
        await self.press(owner.previous_page)
        await self.wait_for_pdf(owner, 1)
        await self.close_reader(owner)

    async def probe(self):
        self.cache = Path(self.paths.cache)
        result = dict(success=False, cases=[])
        try:
            await until(lambda: not getattr(self, '_startup_in_progress', False))
            from features.rclone.localcrypt.mobile.resources import encrypted_storage
            root = self.cache / 'appearance-fixtures'
            root.mkdir()
            _, comic = make_books(root)
            with ZipFile(comic, 'w') as archive:
                for index, color in enumerate(((170, 24, 22), (35, 171, 63), (38, 61, 200))):
                    archive.writestr(f'{index}.png', solid_page(*color))
            (root / 'Fixture.pdf').write_bytes(pdf_bytes())
            self.show_cloud(present=False)
            if task := getattr(self, 'cloud_restore_task', None):
                await task
            self.cloud_client.request('import', password=PASSWORD, package=load_aes_localcrypt_package(),
                                      package_name='AppearanceFixture.zip', session_only=True)
            assert any(not record.get('saved') and record.get('document_cache_id')
                       for record in self.cloud_client.package_records)
            encrypted = encrypted_storage(self.private_root / 'appearance-crypt', self.cloud_client, 'Secret')
            for path in root.iterdir():
                assert encrypted.create_file(path.name, BytesIO(path.read_bytes())) is not False
            for label, provider in (('local', LocalFiles(root)), ('localcrypt', encrypted)):
                for check in (self.comic, self.epub, self.pdf):
                    self.preferences.save(reading_margin='16')
                    result['running'] = f'{label}-{check.__name__}'
                    write_result(self.cache / 'reader-appearance-progress.json', result)
                    await check(provider, label)
                    result['cases'].append(result.pop('running'))
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        write_result(self.cache / RESULT, result)


def main():
    return ReaderAppearanceProbe('Reader Appearance QA', 'io.github.ispaure.logisticsstorageqa')
