"""Real native widgets + compiled crypt bridge, using desktop-made ciphertext."""
import asyncio
import base64
import json
import os
from pathlib import Path


async def exercise_localcrypt(app, passed):
    def canvas(owner):
        spread = getattr(owner, 'provider_spread', None)
        return spread.canvases[0] if spread is not None else owner.crypt_image
    async def book_text(expected):
        view = app.provider_sessions().active.provider_epub_view
        if not hasattr(view, 'webview'):
            assert expected in view.text.value
            return
        last = ''
        for _ in range(200):
            last = await view.webview.evaluate_javascript('document.body ? document.body.textContent : ""')
            if expected in str(last):
                return
            await asyncio.sleep(.1)
        raise AssertionError(f'Private EPUB did not render {expected!r}: {last!r}')
    fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
    app.show_cloud()
    if getattr(app, 'cloud_restore_task', None):
        await app.cloud_restore_task
    assert not app.cloud_busy
    app.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
    app.crypt_copies.client = app.cloud_client
    for item in fixture['copies'].values():
        folder = app.crypt_copies.root / item['key']
        folder.mkdir()
        (folder / 'data').write_bytes(base64.b64decode(item['ciphertext']))
        (folder / 'record.json').write_text(json.dumps(item['record']))
    await app.refresh_crypt()
    assert len(app.crypt_labels) == len(fixture['copies']), app.cloud_status.value

    async def close_copy():
        from unittest.mock import AsyncMock, patch
        owner = app.provider_sessions().active
        # These cases test private-session lifetime, not native dialog taps.
        # Complete Cancel explicitly instead of leaving a modal over later cases.
        with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value='cancel')) as decision:
            app.close_crypt()
            pending = getattr(owner, '_exit_task', None)
            if pending is not None:
                await asyncio.wait_for(asyncio.shield(pending), 60)
            pending = getattr(app, '_document_close_tasks', {}).get(owner.session.id)
            if pending is not None:
                await asyncio.wait_for(asyncio.shield(pending), 60)
                decision.assert_awaited_once()
        # UIKit restores retained folder rows after a reader pop. Finish that
        # navigation before starting another listing on the same browser.
        pending = app.routes.folders.task
        if pending is not None and not pending.done():
            await asyncio.wait_for(asyncio.shield(pending), 60)

    async def open_copy(name, password=''):
        key = fixture['copies'][name]['key']
        app.crypt_selector.value = next(label for label, value in app.crypt_labels.items() if value == key)
        app.crypt_password.value = password
        await app.open_crypt()
        assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None) is not None, app.cloud_status.value
        assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).name == name
        assert app.crypt_password.value == ''
        # Allow native layout/image decoding to complete on its own event loop.
        await asyncio.sleep(.1)
        # Native layout can trigger a real page reload after open returns.
        # Metadata and close actions are disabled until that operation ends.
        deadline = asyncio.get_running_loop().time() + 60
        owner = app.provider_sessions().active
        while owner.cloud_busy:
            assert asyncio.get_running_loop().time() < deadline, ('Private reader reload did not settle', name)
            await asyncio.sleep(.05)
        return (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None)

    # A fresh iOS picker must select a newly inserted private location before
    # opening its CBZ; the old backend displayed that label but still read row 0.
    from tempfile import TemporaryDirectory
    from features.rclone.localcrypt.mobile.resources import CryptFiles
    with TemporaryDirectory(dir=app.private_root) as directory:
        provider = CryptFiles(Path(directory), app.cloud_client, 'Secret')
        provider._physical('plain.cbz').write_bytes(base64.b64decode(fixture['copies']['plain.cbz']['ciphertext']))
        drawer = app.adaptive.browser('documents')
        assert await drawer.show_main_browser('LocalCrypt: Native check', provider=provider)
        assert drawer.storage.value == 'LocalCrypt: Native check'
        assert drawer.provider is provider
        assert await drawer.open_file({'path': 'plain.cbz'}), drawer.status.text
        owner = app.private_sessions.active
        assert owner is not None and owner.crypt_reader.name == 'plain.cbz'
        assert canvas(owner).image.width == 24
        await close_copy()
        # Read collection configuration through the same encrypted provider.
        from io import BytesIO
        provider.create_file('remoteConfig.ini', BytesIO(b'[LogisticsZIP]\narchive_password=synthetic-archive-password\n'))
        provider._physical('encrypted.cbz').write_bytes(base64.b64decode(fixture['copies']['encrypted.cbz']['ciphertext']))
        assert await drawer.show_main_browser('LocalCrypt: Native check', provider=provider)
        assert await drawer.open_file({'path': 'encrypted.cbz'}), 'Configured fixture did not open'
        owner = app.private_sessions.active
        assert owner is not None and canvas(owner).image.width == 24
        await close_copy()

        from .obsidian_checks import exercise_obsidian
        await exercise_obsidian(app, provider)
        passed.append('native_obsidian_vault')

    for name in ('note.md', 'text.txt'):
        await open_copy(name)
        assert app.provider_sessions().active.crypt_text.value
        await close_copy()
    for name, password in (('plain.cbz', ''), ('encrypted.cbz', 'synthetic-archive-password')):
        await open_copy(name, password)
        assert canvas(app.provider_sessions().active).image.width == 24
        from .reader_checks import assert_comic_centered
        owner = app.private_sessions.active
        assert owner.crypt_bookmark_button not in owner.crypt_tools_view.content.children
        assert owner.crypt_bookmark_selector not in owner.crypt_tools_view.content.children
        for _ in range(2):
            app.show_settings()
            await asyncio.sleep(.1)
            owner.resume_crypt()
            canvas(owner).toggle_controls()
            await asyncio.sleep(.1)
            canvas(owner).toggle_controls()
            await assert_comic_centered(lambda: canvas(owner), fullscreen=True)
            assert not owner.crypt_bookmarks
        await close_copy()
        assert not owner.crypt_bookmarks
    for name, password in (('book.epub', ''), ('protected.epub', 'synthetic-archive-password')):
        await open_copy(name, password)
        await book_text('First chapter')
        app.provider_sessions().active.crypt_page.value = (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).labels[1]
        await app.read_crypt_page()
        await book_text('Second chapter')
        owner = app.private_sessions.active
        owner.toggle_private_bookmark()
        assert owner.epub_session_bookmarks == {(1, owner.provider_epub_view.offset)}
        app.save_workspace()
        manifest = (app.private_root / 'workspace.json').read_text()
        assert 'crypt_bookmarks' not in manifest and 'epub_session_bookmarks' not in manifest and owner.session.id not in manifest
        await close_copy()
    passed.append('native_localcrypt_reading')

    await open_copy('note.md')
    privacy = app.screen_privacy
    privacy.conceal()
    if privacy.backend.startswith('toga_iOS.'):
        assert privacy.shield is not None
        parent = privacy.shield.superview()
        native_window = app.main_window._impl.native
        assert parent is not None and parent.ptr.value == native_window.ptr.value, f'Snapshot shield parent {parent!r}; window {native_window!r}'
        from .fixtures import capture_window
        await capture_window(app, app.private_root / 'localcrypt-privacy-shield.png')
    privacy.reveal()
    if privacy.backend.startswith('toga_iOS.'):
        assert privacy.shield is None
    assert app.main_window.content is privacy.lock_view
    privacy.lock_password.value = 'wrong-password'
    await privacy.unlock()
    assert app.main_window.content is privacy.lock_view
    privacy.lock_password.value = 'synthetic-session-password'
    await privacy.unlock()
    assert app.main_window.content is not privacy.lock_view
    assert app.provider_sessions().active.crypt_reader.name == 'note.md'
    passed.append('native_localcrypt_resume_password_lock')
    passed.append('native_localcrypt_snapshot_shield')
    first = app.private_sessions.active
    first.crypt_text.value = 'First native memory-only draft'
    await open_copy('text.txt')
    second = app.private_sessions.active
    second.crypt_text.value = 'Second native memory-only draft'
    await app.show_files()
    app.show_settings()
    await open_copy('note.md')
    assert app.private_sessions.active is first
    assert app.provider_sessions().active.crypt_text.value == 'First native memory-only draft'
    assert second.crypt_text.value == 'Second native memory-only draft'
    assert len(app.private_sessions.controllers) == 2
    app.memory_pressure.release()
    await asyncio.sleep(.1)
    assert first.crypt_text.value == 'First native memory-only draft'
    assert second.crypt_text.value == 'Second native memory-only draft'
    from unittest.mock import AsyncMock, patch
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value='cancel')) as decision:
        app.request_close_session(first.session.id)
        await app._document_close_tasks[first.session.id]
        decision.assert_awaited_once()
    assert not app.close_session(first.session.id, choice='cancel')
    first.resume_crypt()
    await app.clear_cloud()
    assert len(app.private_sessions.controllers) == 2
    assert first.crypt_text.value == 'First native memory-only draft'
    app.save_workspace()
    manifest = (app.private_root / 'workspace.json').read_text()
    assert 'provider-session' not in manifest and 'native memory-only draft' not in manifest
    token = app.workspace.token(second.session.id)
    assert app.clear_private_reader(discard=True)
    assert not app.workspace.accepts(token)
    assert first.crypt_text.value == second.crypt_text.value == ''
    assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None) is None
    # A real ciphertext open can complete after the user starts writing again.
    # Keep the loaded provider session available without changing that selection.
    from threading import Event
    started, release = Event(), Event()
    original_open = app.crypt_copies.open
    def delayed_open(*args, **kwargs):
        started.set()
        if not release.wait(10):
            raise RuntimeError('Native provider fixture was not released')
        return original_open(*args, **kwargs)
    app.new_document()
    app.show_documents(destination='documents')
    writer = app.editor_view
    app.show_cloud()
    key = fixture['copies']['note.md']['key']
    with patch.object(app.crypt_copies, 'open', side_effect=delayed_open):
        task = asyncio.create_task(app.open_crypt(copies=app.crypt_copies, key=key))
        try:
            deadline = asyncio.get_running_loop().time() + 30
            while asyncio.get_running_loop().time() < deadline:
                if started.is_set() or task.done():
                    break
                await asyncio.sleep(.01)
            assert started.is_set(), ('Private-opening worker did not start',
                task.result() if task.done() else 'pending', app.cloud_busy, app.cloud_status.value)
            app.show_documents(destination='documents')
            app.editor.value = 'Native ordinary draft during private opening'
            body = app.body
            release.set()
            assert await task
            assert app.native_host.state.destination == 'documents'
            assert app.body is body and app.editor_view is writer
            assert app.workspace.active == writer.session.id
            assert app.editor.value == 'Native ordinary draft during private opening'
            loaded = next(owner for owner in app.private_sessions.controllers.values()
                          if owner.session.title == 'note.md')
            assert loaded.crypt_reader.text
            assert app.private_sessions.activate(loaded.session.id)
            assert app.provider_sessions().active.crypt_text.value == loaded.crypt_reader.text
            await close_copy()
        finally:
            release.set()
            await task
    passed.append('native_private_workspace')

    for name in ('note.md', 'text.txt'):
        reader = await open_copy(name)
        app.provider_sessions().active.crypt_text.value = '# Native LocalCrypt edited sentinel\n'
        await close_copy()
        assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None) is reader and app.private_dirty()
        await app.save_crypt()
        assert 'Saved encrypted' in app.provider_sessions().active.crypt_title.text, app.provider_sessions().active.crypt_title.text
        await close_copy()
        updated = await open_copy(name)
        assert updated.text == '# Native LocalCrypt edited sentinel\n'
        if name == 'text.txt':
            assert updated.data == b'\xef\xbb\xbf# Native LocalCrypt edited sentinel\r\n'
        await close_copy()
    passed.append('native_localcrypt_text_editing')

    for name, password in (('plain.cbz', ''), ('encrypted.cbz', 'synthetic-archive-password'),
                           ('book.epub', ''), ('protected.epub', 'synthetic-archive-password')):
        print('LOGISTICS_NATIVE_METADATA=' + name + ':open', flush=True)
        reader = await open_copy(name, password)
        before_page = reader.page(0)
        app.edit_crypt_metadata()
        key = 'title' if name.endswith('.epub') else 'Title'
        assert key in app.provider_sessions().active.crypt_metadata_fields
        app.provider_sessions().active.crypt_metadata_fields[key].value = 'Native LocalCrypt metadata sentinel'
        await close_copy()
        assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None) is reader and app.private_dirty()
        app.edit_crypt_metadata()
        # Re-presenting the retained metadata screen can schedule a native
        # reader reload. The real Save button is disabled until that work ends.
        await asyncio.sleep(.1)
        owner = app.provider_sessions().active
        await asyncio.wait_for(owner.operation_idle.wait(), 60)
        print('LOGISTICS_NATIVE_METADATA=' + name + ':save', flush=True)
        await app.save_crypt_metadata()
        assert app.provider_sessions().active.crypt_metadata_status.text == 'Metadata saved encrypted locally.', app.provider_sessions().active.crypt_metadata_status.text
        assert not app.private_dirty()
        await close_copy()
        updated = await open_copy(name, password)
        value = updated.book.values('title')[0] if updated.book else updated.comic.info.get_field('Title')
        assert value == 'Native LocalCrypt metadata sentinel'
        assert updated.page(0) == before_page
        await close_copy()
        if password:
            import toga
            from commonUtils.runtime.platform import get_os, OS
            app.crypt_password.value = 'wrong'
            original_dialog = app.main_window.dialog
            acknowledged = []
            async def acknowledge_password_error(dialog):
                assert isinstance(dialog, toga.InfoDialog), 'Unexpected native password-error dialog'
                task = asyncio.create_task(original_dialog(dialog))
                try:
                    await asyncio.sleep(.2)
                    native = dialog._impl.native
                    if get_os() is OS.IOS:
                        assert str(native.title) == 'Could not open document'
                        message = str(native.message)
                        assert native.presentingViewController is not None
                        native.dismissViewControllerAnimated(False, completion=None)
                        dialog._impl.response(None)
                    else:
                        from java import jclass
                        assert native.isShowing()
                        message = str(native.findViewById(jclass('android.R$id').message).getText())
                        native.getButton(-1).performClick()
                    assert 'password' in message.lower(), message
                    acknowledged.append(message)
                    return await asyncio.wait_for(task, 5)
                finally:
                    if not task.done():
                        task.cancel()
            print('LOGISTICS_NATIVE_METADATA=' + name + ':wrong-password', flush=True)
            with patch.object(app.main_window, 'dialog', side_effect=acknowledge_password_error):
                await asyncio.wait_for(app.open_crypt(), 30)
            assert len(acknowledged) == 1, 'Wrong password did not show its native error'
            assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None) is None, 'Metadata save removed inner ZIP password'
            assert 'password' in app.cloud_status.value.lower()
        print('LOGISTICS_NATIVE_METADATA=' + name + ':complete', flush=True)
    passed.append('native_localcrypt_metadata')

    reader = await open_copy('note.md')
    original = (app.crypt_copies.root / reader.key / 'data').read_bytes()
    app.provider_sessions().active.crypt_text.value = 'unsaved private edit'
    # A concurrent file change must fail without publishing over the original.
    # Exercise the native error UI with a normal draft; oversized inputs belong
    # in core tests, not in a platform text widget's layout engine.
    target = app.crypt_copies.root / reader.key / 'data'
    stamp = target.stat()
    os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000_000))
    await app.save_crypt()
    assert app.private_dirty() and 'failed' in app.provider_sessions().active.crypt_title.text.lower()
    assert (app.crypt_copies.root / reader.key / 'data').read_bytes() == original
    app.discard_crypt()
    await app.clear_cloud()
    await app.refresh_crypt()
    assert all('Locked copy' in label for label in app.crypt_labels)
    for file in app.crypt_copies.root.rglob('*'):
        if file.is_file():
            content = file.read_bytes()
            assert b'Native LocalCrypt edited sentinel' not in content
            assert b'Native LocalCrypt metadata sentinel' not in content
    passed.append('native_localcrypt_failure_and_lock')

    # Exercise actual native folder controls and the shared move engine.
    app.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
    await app._load_crypt_remote_names()
    # A loaded remote alone is no longer a local storage location. Seed an
    # actual encrypted fixture folder before exercising destination mutations.
    from features.rclone.localcrypt.mobile.resources import CryptFiles
    remote = fixture['copies']['note.md']['record']['remote']
    provider = CryptFiles(app.private_root / 'LocalCryptFolders', app.cloud_client, remote)
    provider.mkdir('fixture-seed')
    await app.show_files()
    from features.rclone.mobile.storage_location import collection_path
    local = collection_path(app.private_root)
    (local / 'source').mkdir()
    (local / 'source/empty').mkdir()
    (local / 'source/note.md').write_bytes(b'# Native folder transfer')
    assert await app.browser_file_location(('Local files', '')), app.file_status.value
    def select(path):
        matches = [label for label, row in app.file_rows.items() if row['path'] == path]
        assert matches, f'{path}: {app.file_status.value}; entries={list(app.file_rows)}'
        app.file_selection.value = matches[0]
    select('source')
    crypt_label = next(label for label in app.file_roots if label.startswith('LocalCrypt:'))
    app.file_destination.value = crypt_label
    app.file_target.value = 'imported'
    await app.move_file()
    assert not (local / 'source').exists(), app.file_status.value
    # Await navigation before selecting rows; on_change listings are asynchronous.
    assert await app.browser_file_location((crypt_label, '')), app.file_status.value
    select('imported')
    app.file_name.value = 'renamed'
    await app.rename_file()
    select('renamed')
    app.file_name.value = 'destination'
    await app.new_file_folder()
    select('renamed')
    app.file_destination.value = crypt_label
    app.file_target.value = 'destination/moved'
    await app.move_file()
    assert 'failed' not in app.file_status.value.lower(), app.file_status.value
    assert await app.browser_file_location((crypt_label, 'destination/moved')), app.file_status.value
    select('destination/moved/note.md')
    await app.read_managed_file()
    assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).text == '# Native folder transfer'
    app.provider_sessions().active.crypt_text.value = '# Edited after native move'
    await app.save_crypt()
    assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).text == '# Edited after native move', app.provider_sessions().active.crypt_title.text
    await app.show_crypt_save_as()
    app.save_as_storage.value = crypt_label
    app.save_as_name.value = 'saved-as.md'
    await app.save_text_destination()
    assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).key == 'saved-as.md', app.save_as_status.value
    await app.show_crypt_save_as()
    app.save_as_name.value = 'local-copy.md'
    app.save_as_storage.value = 'Local files'
    await app.save_text_destination()
    assert (local / 'local-copy.md').read_bytes() == b'# Edited after native move', app.save_as_status.value
    app.provider_sessions().active.crypt_text.value = '# Local save after Save As'
    await app.save_crypt()
    assert (local / 'local-copy.md').read_bytes() == b'# Local save after Save As'
    await app.show_crypt_save_as()
    app.save_as_storage.value = crypt_label
    app.save_as_name.value = 'saved-as.md'
    await app.save_text_destination()
    assert 'failed' in app.save_as_status.value.lower()
    assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).key == 'local-copy.md'
    app.cancel_text_destination()
    await close_copy()
    # The unified editor chooser uses the same decoded directory model as files.
    await app.show_editor_open()
    app.save_as_storage.value = crypt_label
    app.picker_folder.value = 'destination/moved'
    await app.refresh_editor_browser()
    app.picker_entries.value = next(label for label, row in app.editor_picker_rows.items() if row['name'] == 'note.md')
    await app.select_editor_item()
    await app.confirm_editor_file()
    assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).key == 'destination/moved/note.md', app.cloud_status.value
    assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).text == '# Edited after native move'
    await close_copy()
    # Ordinary draft -> encrypted editor must scrub recovery and hidden widgets.
    app.new_document()
    app.editor.value = 'private handoff native sentinel'
    source = app.current
    await app.show_document_save_as()
    app.save_as_storage.value = crypt_label
    app.save_as_name.value = 'private-handoff.txt'
    await app.save_text_destination()
    assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).text == 'private handoff native sentinel', app.save_as_status.value
    assert app.provider_sessions().active.crypt_view in app.body.children, 'Saved editor must actually be visible'
    assert app.editor.value == source.snapshot.text
    assert 'private handoff native sentinel' not in app.store.path(source.id, '.json').read_text()
    await close_copy()
    assert await app.show_files(location=(crypt_label, '')), app.file_status.value
    select('destination')
    app.file_destination.value = 'Local files'
    app.file_target.value = 'exported'
    await app.move_file()
    assert (local / 'exported/moved/note.md').read_bytes() == b'# Edited after native move'
    assert (local / 'exported/moved/empty').is_dir()
    from commonUtils.runtime.local_files import LocalFiles
    from commonUtils.runtime.resource_mutations import delete_resource
    await asyncio.to_thread(delete_resource, LocalFiles(local), 'exported')
    assert not (local / 'exported').exists()
    await app.clear_cloud()
    # Shared native presentation and a file exceeding the former 32 MiB cap.
    app.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
    await app._load_crypt_remote_names()
    await app.show_files()
    from zipfile import ZipFile
    from features.rclone.localcrypt.mobile.resources import ManagedCopies
    from commonUtils.runtime.resource_mutations import move_resource
    from commonUtils.runtime.local_files import LocalFiles
    plain_copy = app.crypt_copies.open(fixture['copies']['plain.cbz']['key'])
    image = plain_copy.page(0)[1]
    big = local / 'large-browser.cbz'
    with ZipFile(big, 'w') as archive:
        archive.writestr('page.png', image)
        with archive.open('payload.bin', 'w') as payload:
            for _ in range(40):
                payload.write(b'x' * 1024 * 1024)
    provider = app.file_provider_for(crypt_label)
    provider.mkdir('navigation')
    from io import BytesIO
    provider.create_file('navigation/nested-search.md', BytesIO(b'nested search'))
    await asyncio.to_thread(move_resource, LocalFiles(local), big.name, provider, big.name)
    assert not big.exists()
    copies = ManagedCopies(provider)
    reader = await asyncio.to_thread(copies.open, 'large-browser.cbz')
    assert reader.streaming and reader.page(0)[1] == image
    updated = await asyncio.to_thread(copies.save_metadata, reader, {'Title': 'Large native browser sentinel'})
    assert updated.comic.info.get_field('Title') == 'Large native browser sentinel'
    await app.show_files()
    assert await app.browser_file_location((crypt_label, '')), app.file_status.value
    browser = app.file_browser
    assert browser.entries and browser.mode == 'List'
    browser.show_tiles()
    assert browser.mode == 'Tiles' and browser.buttons
    entry = next(entry for entry in browser.entries if entry.label == 'large-browser.cbz')
    # Contextual selection requests metadata; a file tap deliberately skips it.
    await browser.select(entry)
    await asyncio.gather(*tuple(browser.tasks))
    assert app.selected_file()[1] == 'large-browser.cbz'
    assert any('Title: Large native browser sentinel' == child.text for child in browser.info.children if hasattr(child, 'text'))
    assert browser.thumbnail is None and not browser.icons
    # Folder browsing must not decrypt covers automatically. Exercise the
    # large-file native thumbnail API as an explicit preview request instead.
    from logisticsmobile.browser_preview import callbacks
    thumbnail, _ = callbacks(provider, app.cloud_client)
    preview = await asyncio.to_thread(thumbnail, entry.payload, (160, 160), lambda: False)
    assert preview.startswith(b'\x89PNG')
    assert not browser.icons
    await browser.activate_entry(entry)
    assert app.private_sessions.active.crypt_reader.name == 'large-browser.cbz'
    await app.show_files()
    assert app.file_browser is browser
    browser.show_list()
    assert browser.mode == 'List'
    browser.sort.value = 'Name Z–A'
    assert browser.entries[0].container
    browser.search_button.on_press()
    assert browser.search_open
    header = browser.location_bar
    assert browser.search_panel.parent is getattr(header, 'native_actions', header)
    browser.search.value = 'nested-search'
    while browser.tasks:
        await asyncio.gather(*tuple(browser.tasks))
    assert [item.label for item in browser.entries] == ['navigation/nested-search.md']
    await browser.activate_entry(browser.entries[0])
    assert app.selected_file()[1] == 'navigation/nested-search.md'
    await app.show_files()
    browser.search.value = 'LARGE-BROWSER'
    while browser.tasks:
        await asyncio.gather(*tuple(browser.tasks))
    assert [item.label for item in browser.entries] == ['large-browser.cbz']
    browser.search.value = 'nothing-matches'
    while browser.tasks:
        await asyncio.gather(*tuple(browser.tasks))
    assert browser.entries == []
    try:
        app.selected_file()
    except ValueError:
        pass
    else:
        raise AssertionError('Hidden filtered selection remained actionable')
    browser.close_search_button.on_press()
    while browser.tasks:
        await asyncio.gather(*tuple(browser.tasks))
    assert browser.search.value == '' and not browser.search_open
    assert browser.search_panel.parent is None
    folder = next(item for item in browser.entries if item.label == 'navigation')
    await browser.activate_entry(folder)
    assert app.file_path == 'navigation' and browser.back_button.enabled
    await browser.back_button.on_press()
    assert app.file_path == '' and app.file_storage.value == crypt_label
    await browser.back_button.on_press()
    assert app.file_storage.value == 'Local files'
    assert not browser.back_button.enabled
    # The editor picker uses the same shared folder gestures and history.
    await app.show_editor_open()
    editor = app.editor_browser
    app.save_as_storage.value = crypt_label
    await app.refresh_editor_browser()
    folder = next(item for item in editor.entries if item.label == 'navigation')
    await editor.activate_entry(folder)
    assert app.picker_folder.value == 'navigation'
    await editor.back_button.on_press()
    assert app.picker_folder.value == ''
    await editor.back_button.on_press()
    assert app.save_as_storage.value == 'Local files'
    from .mirror_checks import exercise_crypt_mirror
    await exercise_crypt_mirror(app, fixture)
    passed.append('native_localcrypt_read_during_download')
    passed.append('native_localcrypt_folder_pull_push')
    from .review_checks import exercise_reviews
    await exercise_reviews(app)
    passed.append('native_shared_transfer_reviews')
    await app.clear_cloud()
    assert not browser.icons and not browser.info.children and not browser.entries
    passed.append('native_localcrypt_file_management')
