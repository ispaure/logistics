"""Archive management through the app's native File Browser and picker."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

from commonUtils.testing.stages import TestStage
from services.documents.locations import collection_path

TEST_STAGE = TestStage.REGRESSION


async def exercise_archives(app):
    from mobile.archive_ui import reopen_archive
    from mobile.favourites import catalog, reopen
    from mobile.archive_operations import ArchiveItem
    from mobile.recent_documents import RecentDocuments

    folder = 'GeneratedArchiveCheck'
    root = collection_path(app.private_root) / folder
    root.mkdir(parents=True)
    (root / 'One.txt').write_bytes(b'one')
    (root / 'Two.bin').write_bytes(b'\0two')
    (root / 'Three.txt').write_bytes(b'three')
    try:
        # Cold File Browser reads can proceed while the initial connection
        # restore is busy. Selection and picker commands use the idle guard.
        for _ in range(240):
            if not app.cloud_busy:
                break
            await asyncio.sleep(.05)
        assert not app.cloud_busy, 'Initial storage restore did not settle'
        await app.show_files(location=('Local files', folder))
        assert app.file_path == folder, app.file_status.value
        app.begin_file_selection()
        assert app.file_browser.on_check_entry is not None, ('Selection unavailable', app.cloud_busy)
        for row in app.file_rows.values():
            if row['name'] in ('One.txt', 'Two.bin'):
                app.check_file_entry(SimpleNamespace(identity=row['path'], payload=row))
        assert len(app.file_checked) == 2, (list(app.file_rows), list(app.file_checked))
        await app.create_file_archive()
        picker = app.editor_picker()
        assert picker.visible(), (app.native_host.state.destination, app.cloud_busy,
                                  picker.operation.mode, app.native_host.state.routes['files'])
        assert picker.save_as_storage.value == 'Source location'
        assert picker.picker_folder.value == folder
        picker.save_as_name.value = 'Bundle'
        await picker.confirm_editor_file()
        path = root / 'Bundle.zip'
        assert path.is_file(), picker.save_as_status.value
        row = next(row for row in app.file_rows.values() if row['name'] == path.name)
        commands = dict(app.file_item_commands(context=(app.file_provider, 'Local files', row)))
        assert 'Open' in commands
        assert await commands['Manage archive…']()
        manager = app._archives
        assert manager.visible(), app.native_host.state.destination
        manager.select('One.txt')
        with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
            await manager.remove()
        await manager.add()
        picker.save_as_name.value = 'Three.txt'
        await picker.confirm_editor_file()
        with ZipFile(path) as archive:
            assert set(archive.namelist()) == {'Three.txt', 'Two.bin'}
            assert archive.read('Two.bin') == b'\0two'
        manager.close()
        recent = next(session for session in app.recent_documents.sessions() if session.kind == 'archive')
        assert await reopen_archive(app, recent.source)
        assert 'Three.txt' in {member.name for member in manager.members}
        await manager.favourite()
        favourite = next(row for row in catalog(app).entries() if row['opener'].get('kind') == 'archive')
        await manager.extract()
        picker.save_as_name.value = 'Extracted'
        await picker.confirm_editor_file()
        result = root / 'Extracted'
        assert sorted(item.name for item in result.iterdir()) == ['Three.txt', 'Two.bin']
        assert (result / 'Three.txt').read_bytes() == b'three'
        assert (result / 'Two.bin').read_bytes() == b'\0two'
        await manager.extract()
        picker.save_as_name.value = 'Extracted'
        await picker.confirm_editor_file()
        assert 'already exists' in picker.save_as_status.value
        picker.cancel_text_destination()
        await asyncio.sleep(.15)
        manager.close()
        app.set_feature_enabled('archives', False, refresh=False)
        assert 'Manage archive…' not in dict(app.file_item_commands(
            context=(app.file_provider, 'Local files', row)))
        assert not await reopen_archive(app, recent.source)
        app.set_feature_enabled('archives', True, refresh=False)
        path.unlink()
        assert recent.resource == RecentDocuments.reference_id(recent.source, 'archive')
        with patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog:
            assert not await reopen(app, favourite)
            assert dialog.await_count == 1
        assert not any(item.kind == 'archive' for item, _ in app.recent_items())
        invalid = root / 'Invalid.zip'
        with ZipFile(invalid, 'w') as archive:
            archive.writestr('../outside.txt', b'synthetic')
        item = ArchiveItem(app.file_provider, folder + '/Invalid.zip')
        with patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog:
            assert not await manager.open(item)
            assert dialog.await_count == 1
        assert not (root.parent / 'outside.txt').exists()
    finally:
        app.set_feature_enabled('archives', True, refresh=False)
        app.show_home()
        shutil.rmtree(root)
