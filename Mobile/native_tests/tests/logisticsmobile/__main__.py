"""Exercise the actual native app in Briefcase test mode on an emulator/simulator."""
import asyncio
import base64
import json
import os
from pathlib import Path
import traceback
from uuid import uuid4

from commonUtils.runtime.platform import get_os, OS
from commonUtils.runtime.document_access import LocalDocuments
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.preferences import Preferences
from . import CASES, start_native_check
from .fixtures import make_books


async def wait_for_text(view, expected, *, absent=None):
    last = None
    async def loaded():
        nonlocal last
        while True:
            value = await view.evaluate_javascript('document.body ? document.body.textContent : ""')
            last = str(value)
            if expected in str(value) and (absent is None or absent not in str(value)):
                return
            await asyncio.sleep(.1)
    # Toga Android can re-enter its cooperative loop from native callbacks;
    # asyncio's current-task timeout context is not reliable at that boundary.
    # wait() uses a loop timer without requiring a current-task context.
    task = asyncio.create_task(loaded())
    done, _ = await asyncio.wait([task], timeout=30)
    if not done:
        task.cancel()
        raise RuntimeError(f'WebView did not render {expected!r}; last value={last!r}, url={view.url!r}') from None
    await task


async def exercise(app):
    class Progress(list):
        def append(self, case):
            super().append(case)
            print('LOGISTICS_NATIVE_CASE=' + case, flush=True)
    passed = Progress()
    try:
        assert get_os() in {OS.ANDROID, OS.IOS}
        backend = type(app._impl).__module__
        assert backend.startswith('toga_android.' if get_os() is OS.ANDROID else 'toga_iOS.')
        if get_os() is OS.IOS:
            from .ios_storage_probe import exercise_ios_storage
            exercise_ios_storage(app)
            from .navigation_checks import assert_cold_iphone_tab_labels
            await asyncio.sleep(.3)
            assert_cold_iphone_tab_labels(app)
        # Scene activation may restore a destination after startup. Exercise
        # Home explicitly once the native app is running.
        app.show_home()
        assert app.body.children[0].content.children[0].text == 'Your workspace'
        assert app.native_host.state.destination == 'home'
        assert [tab.text for tab in app.navigation.content] == ['Home', 'Folder Hub', 'Documents', 'Chat', 'Settings']
        passed.append('native_hub')
        from .navigation_checks import exercise_navigation
        navigation_proof = await exercise_navigation(app)
        passed.append('native_navigation_foundation')
        app.show_documents()
        app.editor.value = 'Draft survives actual Back'
        import toga
        app.show_view(toga.Label('Route detail'), route='route-check', title='Route detail')
        assert app.native_host.state.routes['documents'] == ['editor', 'route-check']
        if get_os() is OS.IOS:
            navigation = app.adaptive.secondary if app.adaptive.split is not None else app.native_host.adapter.navigation[2]
            # UIKit can ignore a pop requested during the preceding push.
            await asyncio.sleep(.05)
            for _ in range(60):
                if navigation.transitionCoordinator is None:
                    break
                await asyncio.sleep(.05)
            navigation.popViewControllerAnimated(False)
        else:
            app._impl.native.getOnBackPressedDispatcher().onBackPressed()
        for _ in range(60):
            if app.native_host.state.routes['documents'] == ['editor']:
                break
            await asyncio.sleep(.05)
        assert app.native_host.state.routes['documents'] == ['editor'], app.native_host.state.routes['documents']
        assert app.body.children[0] is app.document_view
        assert app.editor.value == 'Draft survives actual Back'
        passed.append('native_route_back')
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
        a, a_editor = app.current.id, app.editor
        app.editor.value = '# Native preview\nA draft\n'
        app.new_document()
        b, b_session = app.current.id, app.editor_view.session.id
        app.name.value = 'Other.md'
        app.editor.value = 'B draft\n'
        assert app.editor is not a_editor
        app.show_locations()
        app.show_settings()
        app.open_document(a)
        app.show_documents()
        assert app.editor is a_editor
        assert app.editor.value == '# Native preview\nA draft\n'
        from logisticsmobile.workspace import Workspace
        restored = Workspace(app.private_root)
        assert len(restored.sessions) == 2
        assert app.store.open(b).text == 'B draft\n'
        app.request_close_session(b_session)
        assert app.close_session(b_session, choice='cancel') is False
        assert b_session in app.workspace.sessions
        app.cancel_close_session(b_session)
        assert app.current.id == b
        app.open_document(a)
        assert app.close_session(b_session, choice='keep')
        assert app.current.id == a
        assert app.store.open(b).text == 'B draft\n'
        app.open_document(b)
        b_session = app.editor_view.session.id
        app.store.path(b, '.data').write_bytes(b'External saved bytes\n')
        assert app.close_session(b_session, choice='save') is False
        assert app.editor.value == 'B draft\n'
        assert app.close_session(b_session, choice='discard')
        assert app.store.open(b).text == 'External saved bytes\n'
        app.open_document(a)
        app.show_documents()
        app.editor.value = '# Native preview\n'
        missing = app.workspace.open('managed-text', 'f' * 32, 'text')
        app.session_opener(missing.id)()
        assert app.body.children[0].children[0].text == 'Document unavailable'
        assert app.current.id == a
        assert app.close_session(missing.id)
        assert missing.id not in app.workspace.sessions
        app.show_documents()
        passed.append('native_text_workspace')
        app.show_preview()
        await wait_for_text(app.preview, 'Native preview')
        original_preview = app.preview
        a_session = app.editor_view.session.id
        app.new_document()
        app.editor.value = '# Different preview owner\n'
        app.show_documents()
        app.session_opener(a_session)()
        assert app.current.id == a
        assert app.editor_view.session.view['markdown_mode'] == 'preview'
        await wait_for_text(app.preview, 'Native preview', absent='Different preview owner')
        app.show_documents()
        app.show_preview()
        assert app.preview is original_preview
        await wait_for_text(app.preview, 'Native preview')
        passed.append('native_markdown_preview')
        fixtures = app.private_root / 'fixtures'
        fixtures.mkdir()
        epub, comic = make_books(fixtures)
        app.show_library()
        record = await asyncio.to_thread(app.reader_manager().catalog.library_store.import_book, LocalDocuments(), epub)
        app.refresh_library()
        await app.open_book(record['id'])
        assert app.reader_manager().active.book_reader is not None, app.reader_manager().active.book_status.text
        await wait_for_text(app.reader_manager().active.book_content.children[0], 'Native EPUB first')
        original_reader = app.reader_manager().active.book_content.children[0]
        from .reader_checks import wait_for_reader
        deadline = asyncio.get_running_loop().time() + 15
        while not await original_reader.evaluate_javascript('Boolean(window.reader)'):
            assert asyncio.get_running_loop().time() < deadline, 'EPUB navigation bridge did not initialize'
            await asyncio.sleep(.05)
        await wait_for_reader(app.reader_manager().active)
        await app.next_book_page()
        assert app.reader_manager().active.book_content.children[0] is original_reader
        await wait_for_text(app.reader_manager().active.book_content.children[0], 'Native EPUB second')
        passed.append('native_epub_reader')
        await app.toggle_bookmark()
        assert app.reader_manager().catalog.library_store.open(record['id'])[0]['epub_bookmarks'] == [
            dict(path=app.reader_manager().active.book_reader.spine[1], offset=app.reader_manager().active.epub_offset)]
        passed.append('native_bookmarks')
        record = await asyncio.to_thread(app.reader_manager().catalog.library_store.import_book, LocalDocuments(), comic)
        background_comic = record['id']
        app.refresh_library()
        await app.open_book(record['id'])
        assert app.reader_manager().active.book_reader is not None, app.reader_manager().active.book_status.text
        assert app.reader_manager().active.book_reader.pages == ['page2.png', 'page10.png']
        assert app.reader_manager().active.book_content.children[0].image.width == 1
        await app.next_book_page()
        assert app.reader_manager().active.book_record['position'] == 1
        from .reader_checks import exercise_reader
        await exercise_reader(app, passed)
        # Exercise a real archive larger than the former ordinary-library cap.
        from zipfile import ZipFile
        large = fixtures / 'large-ordinary.cbz'
        def make_large():
            with ZipFile(comic) as original, ZipFile(large, 'w') as archive:
                archive.writestr('page2.png', original.read('page2.png'))
                archive.writestr('page10.png', original.read('page10.png'))
                with archive.open('unrelated.bin', 'w') as output:
                    for _ in range(257):
                        output.write(b'x' * 1024 * 1024)
        await asyncio.to_thread(make_large)
        record = await asyncio.to_thread(app.reader_manager().catalog.library_store.import_book, LocalDocuments(), large)
        app.refresh_library()
        await app.open_book(record['id'])
        assert app.reader_manager().active.book_reader is not None, app.reader_manager().active.book_status.text
        assert app.reader_manager().catalog.library_store.path(record['id'], '.cbz').stat().st_size > 256 * 1024 * 1024
        assert app.reader_manager().active.book_content.children[0].image.width == 1
        await app.next_book_page()
        assert app.reader_manager().active.book_record['position'] == 1 and app.reader_manager().active.book_content.children[0].image.width == 1
        large.unlink()
        protected_fixture = json.loads(Path(__file__).with_name('comic_fixture.json').read_text())
        from commonUtils.archives.zip_access import ArchivePasswordError
        from logisticsmobile.library import LibraryStore
        for codec in ('aes', 'legacy'):
            protected_comic = fixtures / (codec + '-standalone.cbz')
            original = base64.b64decode(protected_fixture[codec])
            protected_comic.write_bytes(original)
            protected_record = await asyncio.to_thread(app.reader_manager().catalog.library_store.import_book, LocalDocuments(), protected_comic)
            app.refresh_library()
            await app.open_book(protected_record['id'])
            assert app.reader_manager().active.book_reader is None and app.reader_manager().active.book_pending_key == protected_record['id'], app.reader_manager().active.book_status.text
            assert app.reader_manager().active.book_unlock_panel in app.reader_manager().active.library_view.children
            app.reader_manager().active.book_password.value = 'wrong password'
            await app.unlock_book()
            assert app.reader_manager().active.book_reader is None and app.reader_manager().active.book_pending_key == protected_record['id'], app.reader_manager().active.book_status.text
            assert app.reader_manager().active.book_password.value == '' and 'Try again' in app.reader_manager().active.book_status.text
            app.reader_manager().active.book_password.value = protected_fixture['password']
            await app.unlock_book()
            assert app.reader_manager().active.book_reader is not None, app.reader_manager().active.book_status.text
            assert app.reader_manager().active.book_reader.right_to_left and app.reader_manager().active.book_reader.pages == ['page2.png', 'page10.png']
            assert app.reader_manager().active.book_content.children[0].image.width == 1
            assert app.reader_manager().active.book_password.value == '' and app.reader_manager().active.book_unlock_panel not in app.reader_manager().active.library_view.children
            await app.next_book_page()
            await app.toggle_bookmark()
            assert app.reader_manager().active.book_record['position'] == 1 and app.reader_manager().active.book_record['bookmarks'] == [1]
            raw_source = app.reader_manager().active.book_reader.document.source
            app.lock_book()
            assert app.reader_manager().active.book_reader is None and not app.reader_manager().active.book_content.children
            assert raw_source.password is None and not raw_source.cache
            assert app.reader_manager().catalog.library_store.path(protected_record['id'], '.cbz').read_bytes() == original
            assert protected_fixture['password'].encode() not in app.reader_manager().catalog.library_store.path(protected_record['id'], '.json').read_bytes()
            reopened_store = LibraryStore(app.reader_manager().catalog.library_store.root)
            try:
                reopened_store.open(protected_record['id'])
            except ArchivePasswordError:
                pass
            else:
                raise AssertionError('Standalone comic password persisted across reader restart.')
            assert protected_comic.read_bytes() == original
        # Password detection must not grab keyboard focus after leaving reading.
        from threading import Event
        from unittest.mock import patch
        started, release = Event(), Event()
        original_open = app.reader_manager().catalog.library_store.open
        def delayed_password(*args, **kwargs):
            started.set()
            if not release.wait(10):
                raise RuntimeError('Native password fixture was not released')
            return original_open(*args, **kwargs)
        with patch.object(app.reader_manager().catalog.library_store, 'open', side_effect=delayed_password):
            task = asyncio.create_task(app.open_book(protected_record['id']))
            try:
                for _ in range(200):
                    if started.is_set():
                        break
                    await asyncio.sleep(.01)
                assert started.is_set()
                owner = app.readers.active
                with patch.object(owner.book_password, 'focus') as focus:
                    app.show_settings()
                    body = app.body
                    release.set()
                    await task
                    focus.assert_not_called()
                    assert app.native_host.state.destination == 'settings' and app.body is body
                    assert owner.book_pending_key == protected_record['id']
                app.cancel_book_unlock()
            finally:
                release.set()
                await task
        passed.append('native_comic_reader')
        from .scene_checks import exercise_scenes
        await exercise_scenes(app)
        passed.append('native_independent_windows')
        from logisticsmobile.chat_fixture import fixture_server
        with fixture_server() as (url, started, release, requests):
            app.show_chat()
            app.chat_url.value = url
            app.chat_key.value = 'synthetic-native-key'
            await app.refresh_chat_models()
            assert app.chat_model.value == 'fixture-model', app.chat_status.value
            app.chat_prompt.value = 'Native chat fixture'
            await app.send_chat()
            assert app.chat_current['messages'][-1]['status'] == 'complete', app.chat_status.value
            assert app.chat_current['messages'][-1]['content'] == 'Native fixture reply'
            await wait_for_text(app.chat_transcript, 'Native fixture reply')
            assert await app.chat_transcript.evaluate_javascript(
                'document.querySelectorAll("article.user").length >= 1 && '
                'document.querySelectorAll("article.assistant").length >= 1 && '
                'document.documentElement.scrollWidth <= innerWidth')
            assert app.chat_send.text == 'Send' and app.chat_send.enabled
            assert not app.chat_status_box.children
            assert 'synthetic-native-key' not in app.chat_store.path(app.chat_current['id']).read_text()
            assert 'synthetic-native-key' not in (app.chat_store.root / 'profile.json').read_text()
        passed.append('native_lm_chat')
        from features.rclone.mobile.cloud import CloudClient
        from .fixtures import AES_CREDENTIALS
        from unittest.mock import AsyncMock, patch
        app.cloud_client = CloudClient()
        app.show_cloud()
        if hasattr(app, 'cloud_restore_task'):
            await app.cloud_restore_task
        await app.probe_cloud()
        assert 'offline read check passed' in app.cloud_status.value, app.cloud_status.value
        credentials = fixtures / 'credentials.zip'
        credentials.write_bytes(base64.b64decode(AES_CREDENTIALS))
        assert app.cloud_import.text == 'Load remotes' and not app.cloud_import.enabled
        with patch('logisticsmobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), credentials))):
            await app.choose_cloud_package()
            assert app.cloud_import.enabled and 'credentials.zip' in app.cloud_selected_zip.text
            app.cloud_password.value = 'synthetic-fixture-password'
            await app.import_cloud_package()
        assert app.cloud_password.value == ''
        assert app.cloud_pending_zip is None and 'Browse folder' in app.cloud_import_message.text.replace('\n', ' ')
        assert app.cloud_remote.value == 'Fixture' and len(app.cloud_remote.items) == 1, app.cloud_status.value
        await app.browse_cloud()
        row = next(row for row in app.cloud_rows.values() if row['path'] == 'logistics-native-check')
        assert await app.browser_cloud_folder(row)
        row = next(row for row in app.cloud_rows.values() if row['path'].endswith('fixture.txt'))
        assert await app.open_remote_document(row), app.cloud_status.value
        owner = app.provider_sessions().active
        assert owner is not None and owner.crypt_text.readonly
        assert owner.crypt_text.value == 'Native rclone fixture\n'
        assert app.provider_sessions().close(owner.session.id, discard=True)
        assert not hasattr(app, 'download_cloud') and not hasattr(app, 'choose_cloud_copy')
        assert not app.downloads.items()
        passed.append('native_remote_preview_only')
        from .files_checks import exercise_files
        await exercise_files(app, passed)
        from .mirror_checks import exercise_mirrors
        await exercise_mirrors(app, background_comic)
        passed.append('native_background_local_pull_push')
        app.show_cloud()
        await app.clear_cloud()
        assert not list(app.cloud_remote.items)
        assert not app.downloads.items()
        passed.append('native_rclone_files')
        from features.rclone.mobile.credential_vault import ProtectedVault
        vault = ProtectedVault.for_app(app)
        app.cloud_client.vault = vault
        app.cloud_remember.value = True
        app.cloud_password.value = 'synthetic-fixture-password'
        with patch('logisticsmobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), credentials))):
            await app.import_cloud_package()
        assert vault.ciphertext.is_file(), app.cloud_status.value
        encrypted = vault.ciphertext.read_bytes()
        assert b'Fixture' not in encrypted and b'credentials.zip' not in encrypted
        assert b'synthetic-fixture-password' not in vault.record.read_bytes()
        app.cloud_client.request('clear')  # Shutdown/detach without erasing saved keys.
        app.cloud_client = CloudClient(vault=ProtectedVault.for_app(app))
        await app.restore_cloud()
        assert app.cloud_remote.value == 'Fixture', app.cloud_status.value
        assert 'credentials.zip' in app.cloud_package.text
        # A session-only unlock must leave the saved ciphertext untouched.
        app.cloud_remember.value = False
        app.cloud_password.value = 'synthetic-fixture-password'
        with patch('logisticsmobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), credentials))):
            await app.import_cloud_package()
        assert vault.ciphertext.read_bytes() == encrypted
        cache = app.retained_packages()
        matches = cache.matching('Fixture')
        assert len(matches) == 1, app.cloud_import_message.text
        retained_key = matches[0][0]
        await app.lock_cloud()
        locked_choice = app.folder_choices().get('Fixture', {})
        assert all(copy['source'] != 'Remote' for copy in locked_choice.get('copies', ()))
        app.show_cloud_connections()
        assert app.native_host.state.destination == 'settings'
        app.cloud_retained_buttons[retained_key].on_press()
        assert app.routes.screens['settings'][-1][0] == 'unlock-credential'
        app.credential_unlock_password.value = 'incorrect-fixture-password'
        await app.credential_unlock_button.on_press()
        assert not app.loaded_remote_names()
        assert app.credential_unlock_password.value == ''
        app.credential_unlock_password.value = 'synthetic-fixture-password'
        await app.credential_unlock_button.on_press()
        assert app.loaded_remote_names() == ['Fixture'], app.credential_unlock_status.text
        assert any(copy['source'] == 'Remote' for copy in app.folder_choices()['Fixture']['copies'])
        assert cache.path(retained_key).is_file()
        assert vault.ciphertext.read_bytes() == encrypted
        # Key loss must not regenerate a key or overwrite the saved ciphertext.
        app.cloud_client.request('clear')
        vault.keys.delete(vault.metadata()['id'])
        app.cloud_client = CloudClient(vault=ProtectedVault.for_app(app))
        await app.restore_cloud()
        assert 'unavailable' in app.cloud_status.value, app.cloud_status.value
        assert vault.ciphertext.read_bytes() == encrypted
        await app.clear_cloud()
        assert not vault.ciphertext.exists() and not vault.record.exists(), app.cloud_status.value
        assert vault.unlock() is None
        passed.append('native_secure_credentials')
        passed.append('native_credential_visibility')
        from .localcrypt_checks import exercise_localcrypt
        await exercise_localcrypt(app, passed)
        from .ui_review import exercise_ui_review
        ui_review = await exercise_ui_review(app)
        from .browser_back_checks import exercise_browser_back
        ui_review.update(await exercise_browser_back(app))
        success = set(passed) == set(CASES)
        error = ''
    except Exception:
        success = False
        traceback.print_exc()
        error = traceback.format_exc().splitlines()[-1][:600]
    import logisticsmobile
    source = json.loads(Path(logisticsmobile.__file__).with_name('source.json').read_text())
    report = dict(schema=1, suite='logistics-native-ui', target='android' if get_os() is OS.ANDROID else 'ios',
                  backend=type(app._impl).__module__, cases=passed, expected_cases=list(CASES),
                  success=success, error=error, source=source, native_picker_tested=False)
    report['navigation'] = locals().get('navigation_proof')
    report['ui_review'] = locals().get('ui_review')
    report['independent_windows_tested'] = app.scene_manager.supported
    report['original_scene_close_tested'] = getattr(app, 'original_scene_close_tested', False)
    report['scene_environment_limit'] = getattr(app, 'scene_environment_limit', '')
    # iOS's OS logger truncates long single-line messages. Emit independently
    # bounded chunks; the host verifier rejects missing/duplicate chunks.
    # Keep a complete result outside Apple's asynchronous/truncating log stream.
    # This runs only in the disposable test-mode app; normal launches never write it.
    result_path = Path(app.paths.cache) / 'logistics-native-ui-result.json'
    temporary_result = result_path.with_suffix('.tmp')
    temporary_result.write_text(json.dumps(report, sort_keys=True))
    temporary_result.replace(result_path)
    encoded = base64.b64encode(json.dumps(report, sort_keys=True).encode()).decode()
    chunks = [encoded[index:index + 450] for index in range(0, len(encoded), 450)]
    for index, chunk in enumerate(chunks):
        print('LOGISTICS_NATIVE_UI_CHUNK=' + json.dumps(dict(index=index, count=len(chunks), encoding='base64', data=chunk)), flush=True)
        # The Apple system logger drains asynchronously even after Python's
        # stream flush. Do not exit with the final chunks still queued.
        await asyncio.sleep(.02)
    print(f'>>>>>>>>>> EXIT {0 if success else 1} <<<<<<<<<<', flush=True)
    await asyncio.sleep(.25)
    # This is a disposable test-mode app, never the normal app entry point.
    os._exit(0 if success else 1)


class NativeCheckApp(LogisticsMobile):
    def startup(self):
        print('LOGISTICS_NATIVE_STARTUP', flush=True)
        self.navigation_hold = os.environ.get('LOGISTICS_NAVIGATION_HOLD') == '1'
        self.workspace_hold = os.environ.get('LOGISTICS_WORKSPACE_HOLD') == '1'
        self.storage_root = Path(self.paths.cache) / ('workspace-navigation-probe' if self.workspace_hold else 'navigation-foundation-probe' if self.navigation_hold
                                                     else 'native-check-' + uuid4().hex)
        try:
            super().startup()
        except Exception:
            # Preserve chained backend errors before the native launcher wraps them.
            traceback.print_exc()
            raise
        self.show_documents()
        self.show_home()

    def on_running(self):
        if self.workspace_hold:
            from .workspace_hold import hold_workspace
            start_native_check(self, hold_workspace)
        elif self.navigation_hold:
            from .navigation_hold import hold_navigation
            start_native_check(self, hold_navigation)
        else:
            start_native_check(self, exercise)



NativeCheckApp('Logistics Mobile', 'io.github.ispaure.logisticsmobile').main_loop()
