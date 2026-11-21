"""Root and nested LocalCrypt moves through the native workspace item menu."""
import asyncio
import json
from io import BytesIO
from contextlib import ExitStack
from pathlib import Path

from commonUtils.testing.stages import TestStage
from features.rclone.localcrypt.mobile.resources import CryptFiles
from .document_workspace_probe import DocumentWorkspaceProbe

TEST_STAGE = TestStage.REGRESSION


class WorkspaceMoveProbe(DocumentWorkspaceProbe):
    result_name = 'workspace-move-result.json'

    async def run_checks(self, app, report):
        await self.check_local_selection(app, report)
        app.show_cloud(present=False)
        if getattr(app, 'cloud_restore_task', None):
            await app.cloud_restore_task
        fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
        app.cloud_client.request('import', package=fixture['package'],
            password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
        provider = CryptFiles(app.private_root / 'MoveFixture', app.cloud_client, 'Secret')
        provider.mkdir('nested')
        provider.mkdir('destination')
        with ExitStack() as resources:
            resources.callback(provider.acquire())
            for source in ('root.md', 'nested/note.md'):
                data = ('# Move ' + source).encode()
                await asyncio.to_thread(provider.create_file, source, BytesIO(data))
                await app.show_files()
                label = 'LocalCrypt: Move fixture'
                app.file_roots[label] = provider.reopen()
                app.update_file_locations()
                assert await app.browser_file_location((label, source.rpartition('/')[0])), app.file_status.value
                browser = app.file_browser
                entry = next(entry for entry in browser.tree.entries.values()
                             if entry.payload and entry.payload.get('path') == source)
                await browser.select(entry)
                menu = browser.show_item_menu(app.file_item_commands())
                if type(app._impl).__module__.startswith('toga_android.'):
                    index = next(i for i, (title, _) in enumerate(menu.actions) if title == 'Move…')
                    native = menu.native.getListView()
                    assert native.performItemClick(native.getChildAt(index), index,
                                                   native.getItemIdAtPosition(index))
                    for _ in range(500):
                        action = app.editor_picker().operation.destination_action
                        if action is not None and action.path == source:
                            break
                        await asyncio.sleep(.01)
                    else:
                        raise AssertionError('Native Move selection did not open the destination picker')
                else:
                    menu.invoke(dict(menu.actions)['Move…'])
                    menu.dispose()
                await asyncio.wait_for(asyncio.gather(*tuple(browser.work.tasks)), 60)
                picker = app.editor_picker()
                assert picker.operation.destination_action.path == source
                picker.save_as_storage.value = label
                await picker._storage_refresh
                await picker.browser_editor_location((label, 'destination'))
                assert picker.picker_primary.enabled, picker.save_as_status.value
                await picker.confirm_editor_file()
                assert 'Move finished' in app.file_status.value, app.file_status.value
                from features.rclone.localcrypt.mobile.resources import encrypted_copies
                target = 'destination/' + source.rpartition('/')[2]
                reader = await asyncio.to_thread(encrypted_copies(provider).open, target)
                assert reader.data == data
                reader.source.close()
                assert not provider._physical(source).exists()
                assert data not in provider._physical(target).read_bytes()
                report['cases'].append('workspace_menu_move_' + source)
            await self.check_cross_provider_move(app, provider, report)

    async def check_local_selection(self, app, report):
        assert await app.show_files(location=('Local files', ''))
        root = app.file_provider.root
        (root / 'Destination').mkdir()
        for name in ('Move alpha.txt', 'Move beta.txt'):
            (root / name).write_text(name)
        assert await app.browse_files()
        browser = app.file_browser
        native = browser.native_list._impl.native
        android = type(app._impl).__module__.startswith('toga_android.')
        rows = [row for row in browser.native_list.data if row.title.startswith('Move ')]
        assert len(rows) == 2
        await asyncio.sleep(.3)
        if android:
            row = rows[0]
            child = native.getChildAt(row.index - native.getFirstVisiblePosition())
            assert native.getOnItemLongClickListener().onItemLongClick(native, child, row.index,
                                                                       native.getItemIdAtPosition(row.index))
            for _ in range(100):
                if getattr(browser, '_item_menu', None) is not None:
                    break
                await asyncio.sleep(.02)
            menu = browser._item_menu
            assert 'Move…' in dict(menu.actions)
            menu.dispose()
            report['cases'].append('android_native_long_press_exposes_move')
            from android.os import SystemClock
            from android.view import MotionEvent
            browser.dismiss_item_menu()
            start = SystemClock.uptimeMillis()
            x = float(native.getWidth()) / 2
            y = float(child.getBottom() + child.getTop()) / 2
            for action, delay, offset in ((MotionEvent.ACTION_DOWN, 0, 0),
                    (MotionEvent.ACTION_MOVE, 40, -30), (MotionEvent.ACTION_MOVE, 80, -70),
                    (MotionEvent.ACTION_UP, 120, -100)):
                event = MotionEvent.obtain(start, start + delay, action, x, max(1.0, y + offset), 0)
                native.dispatchTouchEvent(event)
                event.recycle()
            await asyncio.sleep(.25)
            assert browser._item_menu is None and app.file_path == ''
            assert (root / rows[0].title).is_file()
            report['cases'].append('android_native_list_drag_keeps_files_in_place')
        app.begin_file_selection()
        for row in rows:
            if android:
                child = native.getChildAt(row.index - native.getFirstVisiblePosition())
                assert native.performItemClick(child, row.index, native.getItemIdAtPosition(row.index))
            else:
                from toga_iOS.libs import NSIndexPath
                path = NSIndexPath.indexPathForRow(row.index, inSection=0)
                native.selectRowAtIndexPath(path, animated=False, scrollPosition=0)
                browser.native_list._impl.native_controller.tableView_didSelectRowAtIndexPath_(native, path)
            await asyncio.sleep(.1)
        assert len(app.file_checked) == 2
        if android:
            assert native.getCheckedItemCount() == 2
        app.cut_files()
        assert await app.browser_file_location(('Local files', 'Destination'))
        await dict(app.file_item_commands())['Paste move here']()
        for name in ('Move alpha.txt', 'Move beta.txt'):
            assert (root / 'Destination' / name).read_text() == name
            assert not (root / name).exists()
        report['cases'].append('native_multi_selection_cut_paste_verified')

    async def check_cross_provider_move(self, app, provider, report):
        from types import SimpleNamespace
        from mobile.file_operations import FileDestination, FileOperationRequest
        from services.documents.progress import open_progress

        assert await app.show_files(location=('Local files', ''))
        source = app.file_provider
        name = 'Boundary.epub'
        content = b'Generated reader-state fixture'
        (source.root / name).write_bytes(content)
        reference = dict(type='local', path=str(source.root / name))
        app.recent_documents.remember_file(SimpleNamespace(kind='epub', title=name), reference)
        state = open_progress(source, name, app.private_root, kind='epub',
                              app=app, revision=source.entry(name)['revision'])
        assert state.save({'position': 37, 'epub_bookmarks': ['passage']}).value == 'saved'
        client = app.cloud_client
        target = FileDestination(app.private_root, client, provider, client.generation)
        request = FileOperationRequest('move', source, name, name, target)
        assert await app.file_operations().run(lambda: request)
        assert not (source.root / name).exists()
        with provider.open(name) as stream:
            assert stream.read() == content
        assert not any(item.get('source', {}).get('path') == reference['path'] for item in app.recent_documents.items)
        protected = open_progress(provider, name, app.private_root, kind='epub',
                                  app=app, revision=provider.entry(name)['revision'])
        assert not protected.load()
        assert 'original storage' in app.file_status.value
        (source.root / name).write_bytes(b'Replacement')
        assert not open_progress(source, name, app.private_root, kind='epub',
                                 app=app, revision=source.entry(name)['revision']).load()
        report['cases'].append('ordinary_to_localcrypt_verified_separate_history')


def main():
    return WorkspaceMoveProbe('Workspace Move QA', 'io.github.ispaure.logisticsnotebookqa')
