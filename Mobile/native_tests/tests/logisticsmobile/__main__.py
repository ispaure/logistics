"""Exercise the actual native app in Briefcase test mode on an emulator/simulator."""
import asyncio
import json
import os
from pathlib import Path
import traceback
from uuid import uuid4

from commonUtils.runtime.platform import get_os, OS
from logisticsmobile.access import LocalDocuments
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.preferences import Preferences
from . import CASES
from .fixtures import make_books


async def wait_for_text(view, expected):
    async def loaded():
        while True:
            value = await view.evaluate_javascript('document.body ? document.body.textContent : ""')
            if expected in str(value):
                return
            await asyncio.sleep(.1)
    await asyncio.wait_for(loaded(), timeout=30)


async def exercise(app):
    passed = []
    try:
        assert get_os() in {OS.ANDROID, OS.IOS}
        backend = type(app._impl).__module__
        assert backend.startswith('toga_android.' if get_os() is OS.ANDROID else 'toga_iOS.')
        assert app.body.children[0].children[0].text == 'Logistics'
        passed.append('native_hub')
        app.show_settings()
        app.font_choice.value = '18'
        app.save_preferences()
        assert Preferences(app.private_root).values['font_size'] == '18'
        passed.append('native_preferences')
        app.show_documents()
        app.name.value = 'Native.md'
        app.editor.value = '# Native preview\n'
        app.save_document()
        assert app.store.open(app.current.id).text == '# Native preview\n'
        passed.append('native_documents')
        app.show_preview()
        await wait_for_text(app.preview, 'Native preview')
        passed.append('native_markdown_preview')
        fixtures = app.private_root / 'fixtures'
        fixtures.mkdir()
        epub, comic = make_books(fixtures)
        app.show_library()
        record = await asyncio.to_thread(app.library_store.import_book, LocalDocuments(), epub)
        app.refresh_library()
        await app.open_book(record['id'])
        assert app.book_reader is not None, app.book_status.text
        await wait_for_text(app.book_content.children[0], 'Native EPUB first')
        await app.next_book_page()
        await wait_for_text(app.book_content.children[0], 'Native EPUB second')
        passed.append('native_epub_reader')
        await app.toggle_bookmark()
        assert app.library_store.open(record['id'])[0]['bookmarks'] == [1]
        passed.append('native_bookmarks')
        record = await asyncio.to_thread(app.library_store.import_book, LocalDocuments(), comic)
        app.refresh_library()
        await app.open_book(record['id'])
        assert app.book_reader is not None, app.book_status.text
        assert app.book_reader.pages == ['page2.png', 'page10.png']
        assert app.book_content.children[0].image.width == 1
        await app.next_book_page()
        assert app.book_record['position'] == 1
        passed.append('native_comic_reader')
        success = set(passed) == set(CASES)
        error = ''
    except Exception:
        success = False
        error = traceback.format_exc()
    import logisticsmobile
    source = json.loads(Path(logisticsmobile.__file__).with_name('source.json').read_text())
    report = dict(schema=1, suite='logistics-native-ui', target='android' if get_os() is OS.ANDROID else 'ios',
                  backend=type(app._impl).__module__, cases=passed, expected_cases=list(CASES),
                  success=success, error=error, source=source, native_picker_tested=False)
    print('LOGISTICS_NATIVE_UI_RESULT=' + json.dumps(report, sort_keys=True), flush=True)
    print(f'>>>>>>>>>> EXIT {0 if success else 1} <<<<<<<<<<', flush=True)
    # This is a disposable test-mode app, never the normal app entry point.
    os._exit(0 if success else 1)


class NativeCheckApp(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('native-check-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(exercise(self))


NativeCheckApp('Logistics Mobile', 'io.github.ispaure.logisticsmobile').main_loop()
