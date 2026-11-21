"""Root and nested LocalCrypt moves through the native workspace item menu."""
import asyncio
import json
import os
import sys
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
        restart = Path(app.paths.cache) / 'workspace-move-restart.json'
        if sys.platform == 'ios' and restart.exists():
            before = json.loads(restart.read_text())
            report.update(before, phase='restarted', pid=os.getpid())
            await self.check_moved_readers(app, report, before['reading'])
            return
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
        if sys.platform == 'ios':
            report['reading'] = await self.check_moved_readers(app, report)
            report.update(phase='checkpoint', pid=os.getpid())
            from .unified_progress_probe import write_result
            write_result(restart, report)

    async def check_local_selection(self, app, report):
        assert await app.show_files(location=('Local files', ''))
        root = app.file_provider.root
        (root / 'Destination').mkdir()
        (root / 'Destination' / 'Keep.txt').write_text('Keep')
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
        if android:
            app.begin_file_selection()
        else:
            await self.ios_item_action(browser, rows[0], 'Select items')
        for row in rows:
            if android:
                child = native.getChildAt(row.index - native.getFirstVisiblePosition())
                assert native.performItemClick(child, row.index, native.getItemIdAtPosition(row.index))
            else:
                self.ios_select_row(browser, row)
            await asyncio.sleep(.1)
        assert len(app.file_checked) == 2
        if android:
            assert native.getCheckedItemCount() == 2
        if android:
            app.cut_files()
            assert await app.browser_file_location(('Local files', 'Destination'))
            await dict(app.file_item_commands())['Paste move here']()
        else:
            from .video_probe import until
            app.file_cut_button._impl.native.sendActionsForControlEvents(1 << 6)
            await until(lambda: app.pending_file_cut() is not None)
            folder = next(row for row in browser.native_list.data if row.title == 'Destination')
            self.ios_select_row(browser, folder)
            await until(lambda: app.file_path == 'Destination')
            keep = next(row for row in browser.native_list.data if row.title == 'Keep.txt')
            await self.ios_item_action(browser, keep, 'Paste move here')
            await until(lambda: app.pending_file_cut() is None and not app.cloud_busy)
        for name in ('Move alpha.txt', 'Move beta.txt'):
            assert (root / 'Destination' / name).read_text() == name
            assert not (root / name).exists()
        report['cases'].append('native_multi_selection_cut_paste_verified')

    @staticmethod
    def ios_select_row(browser, row):
        from toga_iOS.libs import NSIndexPath
        impl = browser.native_list._impl
        path = NSIndexPath.indexPathForRow(row.index, inSection=0)
        impl.native.selectRowAtIndexPath(path, animated=False, scrollPosition=0)
        impl.native_controller.tableView_didSelectRowAtIndexPath_(impl.native, path)

    @staticmethod
    async def ios_item_action(browser, row, title):
        from toga_iOS.libs import NSIndexPath
        from .video_probe import until

        native = browser.native_list._impl.native
        path = NSIndexPath.indexPathForRow(row.index, inSection=0)
        native.scrollToRowAtIndexPath(path, atScrollPosition=2, animated=False)
        await until(lambda: native.cellForRowAtIndexPath(path) is not None)
        native.cellForRowAtIndexPath(path).accessoryView.sendActionsForControlEvents(1 << 6)
        await until(lambda: getattr(browser, '_item_menu', None) is not None)
        menu = browser._item_menu
        assert title in [str(action.title) for action in menu.native.actions]
        menu.invoke(dict(menu.actions)[title])
        browser.dismiss_item_menu()
        await asyncio.wait_for(asyncio.gather(*tuple(browser.work.tasks)), 45)

    async def check_moved_readers(self, app, report, previous=None):
        from zipfile import ZipFile
        from .fixtures import make_books
        from .unified_progress_probe import UnifiedProgressProbe, solid_page
        from .video_probe import until

        assert await app.show_files(location=('Local files', ''))
        root = app.file_provider.root
        prefix = 'Move Shelf'
        destination = 'Moved Reading'
        names = ('Fixture.cbz', 'Fixture.epub')
        if previous is None:
            shelf = root / prefix
            shelf.mkdir()
            make_books(shelf, chapter_text=''.join(
                f'<p>Progress marker {i:03}. Three sentences mark this unique passage.</p>' for i in range(240)))
            with ZipFile(shelf / names[0], 'w') as archive:
                for page in range(1, 41):
                    archive.writestr(f'{page:03}.png', solid_page(page * 5, 32, 150))
            (root / destination).mkdir()
        reading = {}
        for name in names:
            if previous is None:
                assert await app.show_files(location=('Local files', prefix))
                browser = app.file_browser
                row = next(row for row in browser.native_list.data if row.title == name)
                self.ios_select_row(browser, row)
                await until(lambda: getattr(app, 'private_sessions', None) is not None
                            and app.private_sessions.active is not None)
            else:
                app.show_home()
                recent, = [session for session, _ in app.recent_items()
                           if session.title == name and session.provider == 'file-reference']
                reference = recent.source['path']
                from mobile.document_sources import local_document_path
                assert local_document_path(app, reference) == root / destination / prefix / name, reference
                await app.recent_opener(recent)()
            owner = app.private_sessions.active
            await until(lambda: owner._provider_progress is not None and not owner.cloud_busy)
            if name.endswith('.cbz'):
                digest = await UnifiedProgressProbe.image_digest(app, owner)
                if previous is None:
                    await owner.move_private_page(36)
                    assert await UnifiedProgressProbe.image_digest(app, owner) != digest
                assert owner._provider_displayed_index == 36
                reading[name] = dict(page=37, image=await UnifiedProgressProbe.image_digest(app, owner))
            else:
                location = await UnifiedProgressProbe.epub_location(app, owner)
                if previous is None:
                    offset, _ = owner.provider_epub_view.chapter.find('Progress marker 072.', 0)
                    location = await UnifiedProgressProbe.epub_location(app, owner, seek=offset)
                    await until(lambda: owner.provider_epub_view.offset == offset)
                    owner.toggle_private_bookmark()
                reading[name] = dict(anchor=location['anchor'], bookmarks=sorted(
                    list(mark) for mark in owner.epub_session_bookmarks))
                assert reading[name]['bookmarks'] == [[0, location['anchor']]]
            await owner._provider_progress.flush()
            await UnifiedProgressProbe.close_reader(app, owner)

        if previous is not None:
            assert reading == previous, (reading, previous)
            assert not (root / prefix).exists()
            report['cases'].append('home_after_process_restart_restores_comic_page_37_and_epub_bookmark')
            return reading

        assert await app.show_files(location=('Local files', ''))
        browser = app.file_browser
        shelf = next(row for row in browser.native_list.data if row.title == prefix)
        await self.ios_item_action(browser, shelf, 'Move…')
        picker = app.editor_picker()
        assert picker.operation.destination_action.path == prefix
        label = picker.save_as_storage.value
        await picker.browser_editor_location((label, destination))
        assert picker.picker_primary.enabled, picker.save_as_status.value
        picker.picker_primary._impl.native.sendActionsForControlEvents(1 << 6)
        await until(lambda: (root / destination / prefix / names[0]).exists() and not picker.moving())
        assert not (root / prefix).exists()
        assert (root / destination / prefix / names[1]).is_file()
        report['cases'].append('ios_item_move_menu_and_native_picker_button_moved_reading_folder')
        return reading

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
