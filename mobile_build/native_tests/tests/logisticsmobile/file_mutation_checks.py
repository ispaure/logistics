"""Native editor/destination callbacks with actual local or encrypted storage."""
import asyncio
from pathlib import Path
from uuid import uuid4

from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies
from features.rclone.localcrypt.mobile.resources import encrypted_copies
from mobile.file_operations import FileOperationRequest


async def exercise_file_mutations(app, provider=None, *, folder=False):
    from io import BytesIO
    if provider is None:
        root = app.private_root / ('mutation-fixture-' + uuid4().hex)
        root.mkdir()
        provider = LocalFiles(root)
    name = 'Move draft ' + uuid4().hex + '.txt'
    source = 'Source folder ' + uuid4().hex if folder else name
    if folder:
        provider.mkdir(source)
        provider.mkdir(source + '/Nested')
    key = source + '/Nested/' + name if folder else name
    provider.create_file(key, BytesIO(b'Original native bytes\r\n'))
    destination = 'Moved ' + uuid4().hex
    provider.mkdir(destination)
    copies = encrypted_copies(provider) if provider.private else LocalTextCopies(provider)
    assert await app.open_crypt(copies=copies, key=key, edit=True), app.cloud_status.value
    owner = app.private_sessions.active
    widget, session = owner.crypt_text, owner.session
    widget.value = 'Unsaved native draft\n'
    await app.show_files()
    picker = app.editor_picker()
    await picker.show_destination(source, FileOperationRequest('move', provider, source))
    label = 'Native mutation destination'
    picker.editor_storage_roots[label] = provider
    picker.save_as_storage.items = list(picker.editor_storage_roots)
    picker.save_as_storage.value = label
    await picker._storage_refresh
    await picker.browser_editor_location((label, destination))
    assert picker.picker_primary.enabled, picker.save_as_status.value
    await picker.confirm_editor_file()
    target = destination + '/' + (source + '/Nested/' + name if folder else name)
    assert owner.crypt_reader.key == target, picker.save_as_status.value
    assert owner.session is session and owner.crypt_text is widget
    assert owner.crypt_text.value == 'Unsaved native draft\n'
    assert owner.private_dirty()
    await owner.save_crypt()
    assert not owner.private_dirty(), owner.crypt_title.text
    reader = await asyncio.to_thread(copies.open, target)
    assert reader.data == b'Unsaved native draft\r\n'
    try:
        provider.entry(source)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError('Save recreated the moved source')
    if provider.private:
        assert b'Unsaved native draft' not in provider._physical(target).read_bytes()
    assert app.private_sessions.close(session.id)
    print('LOGISTICS_DOCUMENT_MUTATION=' + ('encrypted' if provider.private else 'local')
          + ('-folder' if folder else '-file') + ':passed', flush=True)
    if not folder:
        await exercise_file_mutations(app, provider, folder=True)


async def exercise_destination_edges(app):
    """Native callback acceptance for recoverable Save As errors and switching."""
    import json
    from .rotation_checks import rotate, assert_visible_controls
    from .fixtures import capture_window
    root = app.private_root / ('destination-edges-' + uuid4().hex)
    root.mkdir()
    first, second = root / 'First', root / 'Second'
    first.mkdir()
    second.mkdir()
    (second / 'Existing.md').write_bytes(b'Keep existing')
    picker = app.editor_picker()
    data = b'# Native edge-case draft\n'
    await picker.show_text_destination('Original.md', data)
    picker.editor_storage_roots.update({'Edge first': LocalFiles(first), 'Edge second': LocalFiles(second)})
    picker.save_as_storage.items = list(picker.editor_storage_roots)
    for label in ('Edge first', 'Edge second', 'Edge first', 'Edge second'):
        picker.save_as_storage.value = label
        await picker._storage_refresh
        assert picker.editor_picker_location == (label, '')
        assert not picker.picker_parent.enabled
    for name in ('bad.exe', '../escape'):
        picker.save_as_name.value = name
        await picker.confirm_editor_file()
        assert picker.save_as_status.value and picker.save_as_data == data
    from unittest.mock import patch
    original_dialog = app.main_window.dialog
    async def cancel_replace(dialog):
        task = asyncio.create_task(original_dialog(dialog))
        await asyncio.sleep(.3)
        native = dialog._impl.native
        if type(app._impl).__module__.startswith('toga_iOS.'):
            assert native.presentingViewController is not None
            native.dismissViewControllerAnimated(False, completion=None)
            dialog._impl.response(False)
        else:
            assert native.isShowing()
            native.getButton(-2).performClick()
        return await asyncio.wait_for(task, 5)
    picker.save_as_name.value = 'Existing.md'
    with patch.object(app.main_window, 'dialog', side_effect=cancel_replace):
        await picker.confirm_editor_file()
    assert picker.save_as_data == data
    assert (second / 'Existing.md').read_bytes() == b'Keep existing'
    picker.save_as_name.value = 'Recovered'
    picker.show_new_folder()
    picker.new_folder_name.value = '../escape'
    await picker.create_picker_folder()
    assert 'failed' in picker.save_as_status.value.lower()
    assert picker.save_as_data == data and picker.picker_folder.value == ''
    picker.new_folder_name.value = 'Nested résumé'
    await picker.create_picker_folder()
    assert picker.picker_folder.value == 'Nested résumé'
    geometry = []
    for orientation in ('portrait', 'landscape-left', 'portrait'):
        await rotate(app, orientation)
        picker.save_as_name.focus()
        if type(app._impl).__module__.startswith('toga_android.'):
            from java import jclass
            native = picker.save_as_name._impl.native
            native.requestFocus()
            manager = app._impl.native.getSystemService(jclass('android.content.Context').INPUT_METHOD_SERVICE)
            manager.showSoftInput(native, 1)
            # A fresh emulator may start its IME service asynchronously. Wait
            # for actual visibility instead of sampling during its animation.
            for _ in range(100):
                insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(native)
                if insets is not None and insets.isVisible(jclass('androidx.core.view.WindowInsetsCompat$Type').ime()):
                    break
                await asyncio.sleep(.05)
        await asyncio.sleep(.6)
        assert_visible_controls(app)
        sample = dict(orientation=orientation, width=app.main_window.size.width,
            height=app.main_window.size.height,
            keyboard_inset=getattr(app.native_host.adapter, 'keyboard_inset', None))
        if type(app._impl).__module__.startswith('toga_iOS.'):
            window = app.main_window._impl.native
            native = picker.save_as_name._impl.native
            rect = native.convertRect(native.bounds, toView=window)
            adapter = app.native_host.adapter
            sample['name_bounds'] = [float(rect.origin.x), float(rect.origin.y),
                float(rect.size.width), float(rect.size.height)]
            sample['keyboard_visible'] = bool(adapter.keyboard_visible)
            if adapter.keyboard_visible and adapter.keyboard_frame is not None:
                keyboard = window.convertRect(adapter.keyboard_frame, fromCoordinateSpace=window.screen.coordinateSpace)
                sample['keyboard_top'] = float(keyboard.origin.y)
                assert rect.origin.y + rect.size.height <= keyboard.origin.y + 1, sample
        else:
            from java import jarray, jint, jclass
            native = picker.save_as_name._impl.native
            point = jarray(jint)(2)
            native.getLocationOnScreen(point)
            insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(native)
            ime = jclass('androidx.core.view.WindowInsetsCompat$Type').ime()
            sample['name_bounds'] = [int(point[0]), int(point[1]), int(native.getWidth()), int(native.getHeight())]
            sample['keyboard_visible'] = bool(insets and insets.isVisible(ime))
            sample['fullscreen_ime'] = bool(manager.isFullscreenMode())
            assert not sample['fullscreen_ime'], sample
            if sample['keyboard_visible']:
                bounds = app._impl.native.getWindowManager().getCurrentWindowMetrics().getBounds()
                top = int(bounds.bottom) - int(insets.getInsets(ime).bottom)
                sample['keyboard_top'] = top
                assert native.isShown() and int(point[1]) + int(native.getHeight()) <= top + 1, sample
                action = picker.picker_primary._impl.native
                action.getLocationOnScreen(point)
                sample['save_bounds'] = [int(point[0]), int(point[1]), int(action.getWidth()), int(action.getHeight())]
                assert action.isShown() and int(point[1]) + int(action.getHeight()) <= top + 1, sample
                density = float(native.getResources().getDisplayMetrics().density)
                assert int(action.getHeight()) >= 44 * density, sample
        assert sample['keyboard_visible'], sample
        geometry.append(sample)
        await capture_window(app, Path(app.paths.cache) / ('destination-' + orientation + '.png'))
    before = (app.navigation_generation, picker._epoch, app.cloud_busy)
    await picker.confirm_editor_file()
    owner = app.private_sessions.active
    assert owner is not None, (picker.save_as_status.value, app.cloud_status.value,
        app.active_host, app.cloud_busy, picker.save_as_data, picker.editor_picker_location,
        (second / 'Nested résumé/Recovered.md').exists(), before,
        (app.navigation_generation, picker._epoch),
        (picker.save_as_storage.value, picker.picker_folder.value))
    assert owner.crypt_reader.name == 'Recovered.md', picker.save_as_status.value
    assert (second / 'Nested résumé/Recovered.md').read_bytes() == data
    assert not (first / 'Recovered.md').exists()
    assert app.private_sessions.close(owner.session.id)
    await app.show_editor_open()
    app.cancel_text_destination()
    assert app.editor_picker().origin is None
    (Path(app.paths.cache) / 'logistics-native-destination-edges.json').write_text(json.dumps(
        dict(success=True, scope='native callbacks, errors and geometry', geometry=geometry)))
    print('LOGISTICS_DESTINATION_EDGES=passed', flush=True)


async def exercise_cross_storage(app, encrypted):
    """Move a live draft into encryption and back through native confirmation."""
    from io import BytesIO
    from unittest.mock import patch
    root = app.private_root / ('cross-storage-' + uuid4().hex)
    root.mkdir()
    local = LocalFiles(root)
    name = 'Cross ' + uuid4().hex + '.txt'
    local.create_file(name, BytesIO(b'Cross-storage original'))
    assert await app.open_crypt(copies=LocalTextCopies(local), key=name, edit=True)
    owner = app.private_sessions.active
    widget, session = owner.crypt_text, owner.session
    widget.value = 'First unsaved cross-storage draft'

    async def destination(source, target):
        picker = app.editor_picker()
        await picker.show_destination(name, FileOperationRequest('move', source, name))
        picker.editor_storage_roots['Cross destination'] = target
        picker.save_as_storage.items = list(picker.editor_storage_roots)
        picker.save_as_storage.value = 'Cross destination'
        await picker._storage_refresh
        return picker

    picker = await destination(local, encrypted)
    await picker.confirm_editor_file()
    assert owner._crypt_reader_store.provider.private, picker.save_as_status.value
    assert owner.session is session and owner.crypt_text is widget
    assert widget.value == 'First unsaved cross-storage draft'
    await owner.save_crypt()
    assert encrypted_copies(encrypted).open(name).data == b'First unsaved cross-storage draft'
    assert b'cross-storage draft' not in encrypted._physical(name).read_bytes()
    gate = owner.privacy_gate
    widget.value = 'Second unsaved cross-storage draft'
    picker = await destination(encrypted, local)
    original_dialog = app.main_window.dialog
    async def accept(dialog):
        import toga
        assert isinstance(dialog, toga.ConfirmDialog)
        task = asyncio.create_task(original_dialog(dialog))
        await asyncio.sleep(.3)
        native = dialog._impl.native
        if type(app._impl).__module__.startswith('toga_iOS.'):
            native.dismissViewControllerAnimated(False, completion=None)
            dialog._impl.response(True)
        else:
            native.getButton(-1).performClick()
        return await asyncio.wait_for(task, 5)
    with patch.object(app.main_window, 'dialog', side_effect=accept):
        await picker.confirm_editor_file()
    assert not owner._crypt_reader_store.provider.private, picker.save_as_status.value
    assert owner.privacy_gate is gate
    assert owner.session is session and owner.crypt_text is widget
    assert widget.value == 'Second unsaved cross-storage draft'
    assert (root / name).read_bytes() == b'First unsaved cross-storage draft'
    await owner.save_crypt()
    assert (root / name).read_bytes() == b'Second unsaved cross-storage draft'
    assert app.private_sessions.close(session.id)
    print('LOGISTICS_DOCUMENT_MUTATION=cross-storage-private-draft:passed', flush=True)


async def exercise_system_picker_cancellation(app):
    """Present actual system Open/Export sheets and verify their cancel results."""
    import json
    from mobile.pickers import pick_document, export_document
    for mode in ('open', 'export'):
        task = asyncio.create_task(pick_document(app) if mode == 'open' else
            export_document(app, 'Cancelled export.txt', b'Cancelled export fixture'))
        if type(app._impl).__module__.startswith('toga_iOS.'):
            from commonUtils.ui.native.documents import _ios_pickers
            for _ in range(100):
                pending = _ios_pickers.get(app.main_window.id)
                if pending is not None and pending[2].presentingViewController is not None:
                    break
                await asyncio.sleep(.05)
            else:
                raise AssertionError('The native document picker did not present')
            _, delegate, picker = pending
            await asyncio.sleep(.3)
            picker.dismissViewControllerAnimated(False, completion=None)
            delegate.documentPickerWasCancelled_(picker)
        else:
            # The owning host driver sends Back only while DocumentsUI is
            # foreground on this disposable emulator, including IME dismissal.
            await asyncio.sleep(.5)
            (Path(app.paths.cache) / 'system-picker-phase.json').write_text(json.dumps(
                dict(mode=mode, nonce=uuid4().hex, phase='presented')))
        result = await asyncio.wait_for(task, 30)
        assert result is None if mode == 'open' else result is False
        if type(app._impl).__module__.startswith('toga_android.'):
            (Path(app.paths.cache) / 'system-picker-phase.json').write_text(json.dumps(dict(phase='complete')))
        print('LOGISTICS_SYSTEM_PICKER=' + mode + '-cancel:passed', flush=True)
