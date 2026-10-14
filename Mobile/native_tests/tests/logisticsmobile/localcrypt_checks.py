"""Real native widgets + compiled crypt bridge, using desktop-made ciphertext."""
import asyncio
import base64
import json
import os
from pathlib import Path


async def exercise_localcrypt(app, passed):
    fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
    app.show_cloud()
    if getattr(app, 'cloud_restore_task', None):
        await app.cloud_restore_task
    assert not app.cloud_busy
    app.cloud_client.request('import', package=fixture['package'], password='', package_name='Synthetic.zip', session_only=True)
    app.crypt_copies.client = app.cloud_client
    for item in fixture['copies'].values():
        folder = app.crypt_copies.root / item['key']
        folder.mkdir()
        (folder / 'data').write_bytes(base64.b64decode(item['ciphertext']))
        (folder / 'record.json').write_text(json.dumps(item['record']))
    await app.refresh_crypt()
    assert len(app.crypt_labels) == len(fixture['copies']), app.cloud_status.value

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
        return (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None)

    for name in ('note.md', 'text.txt'):
        await open_copy(name)
        assert app.provider_sessions().active.crypt_text.value
        app.close_crypt()
    for name, password in (('plain.cbz', ''), ('encrypted.cbz', 'synthetic-archive-password')):
        await open_copy(name, password)
        assert app.provider_sessions().active.crypt_image.image.width == 24
        from .reader_checks import assert_comic_centered
        owner = app.private_sessions.active
        owner.toggle_private_bookmark()
        assert owner.crypt_bookmarks == {0}
        for _ in range(2):
            app.show_settings()
            await asyncio.sleep(.1)
            owner.resume_crypt()
            owner.crypt_image.toggle_controls()
            await asyncio.sleep(.1)
            owner.crypt_image.toggle_controls()
            await assert_comic_centered(owner.crypt_image, fullscreen=True)
            assert owner.crypt_bookmarks == {0}
        owner.toggle_private_bookmark()
        assert owner.crypt_bookmarks == set()
        app.close_crypt()
        assert not owner.crypt_bookmarks
    for name, password in (('book.epub', ''), ('protected.epub', 'synthetic-archive-password')):
        await open_copy(name, password)
        assert 'First chapter' in app.provider_sessions().active.crypt_text.value
        app.provider_sessions().active.crypt_page.value = (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).labels[1]
        await app.read_crypt_page()
        assert 'Second chapter' in app.provider_sessions().active.crypt_text.value
        owner = app.private_sessions.active
        owner.toggle_private_bookmark()
        assert owner.crypt_bookmarks == {1}
        app.save_workspace()
        manifest = (app.private_root / 'workspace.json').read_text()
        assert 'crypt_bookmarks' not in manifest and owner.session.id not in manifest
        app.close_crypt()
    passed.append('native_localcrypt_reading')

    await open_copy('note.md')
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
    app.request_close_session(first.session.id)
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
    from unittest.mock import patch
    started, release = Event(), Event()
    original_open = app.crypt_copies.open
    def delayed_open(*args, **kwargs):
        started.set()
        if not release.wait(10):
            raise RuntimeError('Native provider fixture was not released')
        return original_open(*args, **kwargs)
    app.new_document()
    app.show_documents()
    writer = app.editor_view
    app.show_cloud()
    key = fixture['copies']['note.md']['key']
    with patch.object(app.crypt_copies, 'open', side_effect=delayed_open):
        task = asyncio.create_task(app.open_crypt(copies=app.crypt_copies, key=key))
        try:
            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(.01)
            assert started.is_set()
            app.show_documents()
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
            app.close_crypt()
        finally:
            release.set()
            await task
    passed.append('native_private_workspace')

    for name in ('note.md', 'text.txt'):
        reader = await open_copy(name)
        app.provider_sessions().active.crypt_text.value = '# Native LocalCrypt edited sentinel\n'
        app.close_crypt()
        assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None) is reader and app.private_dirty()
        await app.save_crypt()
        assert 'Saved encrypted' in app.provider_sessions().active.crypt_title.text, app.provider_sessions().active.crypt_title.text
        app.close_crypt()
        updated = await open_copy(name)
        assert updated.text == '# Native LocalCrypt edited sentinel\n'
        if name == 'text.txt':
            assert updated.data == b'\xef\xbb\xbf# Native LocalCrypt edited sentinel\r\n'
        app.close_crypt()
    passed.append('native_localcrypt_text_editing')

    for name, password in (('plain.cbz', ''), ('encrypted.cbz', 'synthetic-archive-password'),
                           ('book.epub', ''), ('protected.epub', 'synthetic-archive-password')):
        reader = await open_copy(name, password)
        before_page = reader.page(0)
        app.edit_crypt_metadata()
        key = 'title' if name.endswith('.epub') else 'Title'
        assert key in app.provider_sessions().active.crypt_metadata_fields
        app.provider_sessions().active.crypt_metadata_fields[key].value = 'Native LocalCrypt metadata sentinel'
        app.close_crypt()
        assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None) is reader and app.private_dirty()
        app.edit_crypt_metadata()
        await app.save_crypt_metadata()
        assert app.provider_sessions().active.crypt_metadata_status.text == 'Metadata saved encrypted locally.', app.provider_sessions().active.crypt_metadata_status.text
        assert not app.private_dirty()
        app.close_crypt()
        updated = await open_copy(name, password)
        value = updated.book.values('title')[0] if updated.book else updated.comic.info.get_field('Title')
        assert value == 'Native LocalCrypt metadata sentinel'
        assert updated.page(0) == before_page
        app.close_crypt()
        if password:
            app.crypt_password.value = 'wrong'
            await app.open_crypt()
            assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None) is None, 'Metadata save removed inner ZIP password'
            assert 'password' in app.cloud_status.value.lower()
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
    app.cloud_client.request('import', package=fixture['package'], password='', package_name='Synthetic.zip', session_only=True)
    await app._load_crypt_remote_names()
    # A loaded remote alone is no longer a local storage location. Seed an
    # actual encrypted fixture folder before exercising destination mutations.
    from logisticsmobile.file_resources import CryptFiles
    remote = fixture['copies']['note.md']['record']['remote']
    provider = CryptFiles(app.private_root / 'LocalCryptFolders', app.cloud_client, remote)
    provider.mkdir('fixture-seed')
    await app.show_files()
    local = app.private_root / 'LocalFiles'
    (local / 'source').mkdir()
    (local / 'source/empty').mkdir()
    (local / 'source/note.md').write_bytes(b'# Native folder transfer')
    await app.browse_files()
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
    app.file_storage.value = crypt_label
    await app.browse_files()
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
    app.file_location.value = 'destination/moved'
    await app.browse_files()
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
    app.close_crypt()
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
    app.close_crypt()
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
    app.close_crypt()
    app.show_view(app.files_view)
    app.file_location.value = ''
    await app.browse_files()
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
    app.cloud_client.request('import', package=fixture['package'], password='', package_name='Synthetic.zip', session_only=True)
    await app._load_crypt_remote_names()
    await app.show_files()
    from zipfile import ZipFile
    from logisticsmobile.file_resources import ManagedCopies
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
    app.file_storage.value = crypt_label
    await app.browse_files()
    browser = app.file_browser
    assert browser.entries and browser.mode == 'List'
    browser.show_tiles()
    assert browser.mode == 'Tiles' and browser.buttons
    entry = next(entry for entry in browser.entries if entry.label == 'large-browser.cbz')
    await browser.buttons[entry.identity].on_press()
    await asyncio.gather(*tuple(browser.tasks))
    assert app.selected_file()[1] == 'large-browser.cbz'
    assert any('Title: Large native browser sentinel' == child.text for child in browser.info.children if hasattr(child, 'text'))
    assert browser.icons[(entry.identity, entry.revision)].startswith(b'\x89PNG')
    browser.show_list()
    assert browser.mode == 'List'
    browser.sort.value = 'Name Z–A'
    assert browser.entries[0].container
    browser.search_button.on_press()
    assert browser.search_panel in browser.widget.children
    browser.search.value = 'nested-search'
    await asyncio.gather(*tuple(browser.tasks))
    assert [item.label for item in browser.entries] == ['navigation/nested-search.md']
    await browser.buttons[browser.entries[0].identity].on_press()
    assert app.selected_file()[1] == 'navigation/nested-search.md'
    browser.search.value = 'LARGE-BROWSER'
    assert [item.label for item in browser.entries] == ['large-browser.cbz']
    browser.search.value = 'nothing-matches'
    assert browser.entries == []
    try:
        app.selected_file()
    except ValueError:
        pass
    else:
        raise AssertionError('Hidden filtered selection remained actionable')
    browser.close_search_button.on_press()
    assert browser.search.value == '' and browser.search_panel in browser.widget.children
    folder = next(item for item in browser.entries if item.label == 'navigation')
    await browser.buttons[folder.identity].on_press()
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
    await editor.buttons[folder.identity].on_press()
    assert app.picker_folder.value == 'navigation'
    await editor.back_button.on_press()
    assert app.picker_folder.value == ''
    await editor.back_button.on_press()
    assert app.save_as_storage.value == 'Local files'
    from .mirror_checks import exercise_crypt_mirror
    await exercise_crypt_mirror(app, fixture)
    passed.append('native_localcrypt_folder_pull_push')
    await app.clear_cloud()
    assert not browser.icons and not browser.info.children and not browser.entries
    passed.append('native_localcrypt_file_management')
