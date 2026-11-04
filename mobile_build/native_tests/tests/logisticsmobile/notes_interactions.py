"""Native coordinate dispatch and copy acceptance shared by the drawer probe."""
from commonUtils.testing.stages import TestStage

import asyncio
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import patch
import toga

TEST_STAGE = TestStage.REGRESSION


class NotesInteractionChecks:
    @property
    def apple_probe(self):
        return type(self._impl).__module__.startswith('toga_iOS.')

    def native_rect(self, native):
        if self.apple_probe:
            frame = native.convertRect(native.bounds, toView=None)
            return tuple(map(float, (frame.origin.x, frame.origin.y, frame.size.width, frame.size.height)))
        from java import jarray, jint
        position = jarray(jint)(2)
        native.getLocationOnScreen(position)
        return position[0], position[1], native.getWidth(), native.getHeight()

    async def touch_native(self, native, *, fraction=.5, swipe=0):
        x, y, width, height = self.native_rect(native)
        x, y = x + width * fraction, y + height * (.8 if swipe else .5)
        if self.apple_probe:
            payload = dict(action='swipe', points=[x - swipe * 65, y, x + swipe * 65, y]) if swipe else dict(action='tap', points=[x, y])
            output = Path(self.paths.cache)
            (output / 'notes-touch-request.json').write_text(json.dumps(payload))
            for _ in range(300):
                done = output / 'notes-touch-done'
                if done.exists():
                    done.unlink()
                    break
                await asyncio.sleep(.1)
            else:
                raise AssertionError('Native coordinate driver did not reply')
        else:
            from android.view import MotionEvent
            from android.os import SystemClock
            root = native.getRootView()
            left, top, _, _ = self.native_rect(root)
            started = SystemClock.uptimeMillis()
            for action, offset, elapsed in ((0, -65 * swipe, 0), (2, 0, 100), (1, 65 * swipe, 200)):
                density = native.getContext().getResources().getDisplayMetrics().density
                event = MotionEvent.obtain(started, started + elapsed, action, x - left + offset * density, y - top, 0)
                try:
                    root.dispatchTouchEvent(event)
                finally:
                    event.recycle()
                await asyncio.sleep(.04)
        await asyncio.sleep(.4)

    async def wait_for(self, condition, label):
        for _ in range(200):
            if condition():
                return
            await asyncio.sleep(.05)
        raise AssertionError(label)

    async def check_empty_swipes(self, owner, report):
        assert owner.path is None
        for direction, side in ((1, 'files'), (-1, 'links')):
            await self.touch_native(owner.welcome._impl.native, swipe=direction)
            await self.wait_for(lambda: owner.sidebar.side == side, 'Empty swipe did not open ' + side)
            owner.sidebar.show_detail()
            owner.sidebar.finish_dismissals()
            await asyncio.sleep(.3)
        # A real native tap must still activate the Open card.
        await self.touch_native(owner.open_card._impl.native)
        await self.wait_for(lambda: owner.sidebar.side == 'files', 'Open card tap was swallowed')
        owner.sidebar.show_detail()
        owner.sidebar.finish_dismissals()
        report['native_empty_swipes_and_card'] = True

    async def check_library_copies(self, owner, report, storage):
        provider = owner.library.provider
        for source, directory in (('Home.md', False), ('Long folder name for compact row preview', True)):
            for number in (1, 2):
                owner.sidebar.show_sidebar()
                await asyncio.sleep(.4)
                def source_row():
                    return next((row for row in owner.rows.children if any(
                        getattr(child, 'vault_path', None) == source for child in row.children)), None)
                await self.wait_for(lambda: source_row() is not None,
                    f'Missing published {storage} row {source}; notice={owner.notice.text}')
                row = source_row()
                menu = row.children[-1]
                assert (menu.style.width, menu.style.height) == (48, 48)
                before = owner.path
                choices = []
                async def choose(dialog):
                    choices.extend(value for _, value, _ in dialog.choices)
                    return 'copy'
                with patch.object(owner.view.window, 'dialog', new=choose):
                    # Both edges lie outside the visible dots. Hit the real native
                    # hierarchy, so filename overlap or parent clipping fails here.
                    await self.touch_native(menu._impl.native, fraction=.05 if number == 1 else .95)
                    await self.wait_for(lambda: getattr(owner, 'file_action_view', None) is not None, 'Menu edge did not open Copy')
                assert 'copy' in choices
                assert owner.path == before, 'Menu tap opened the adjacent filename'
                form = owner.file_action_view
                field = next(child for child in form.children if isinstance(child, toga.TextInput))
                base = source if directory else 'Home'
                suffix = '' if directory else '.md'
                assert field.value == base + ' - Copy' + suffix, field.value
                copy = next(child for child in form.children if isinstance(child, toga.Button) and child.text == 'Copy')
                await self.touch_native(copy._impl.native)
                await self.wait_for(lambda: getattr(owner, 'file_action_view', None) is None, 'Native Copy did not finish')
                target = base + ' - Copy' + (' (2)' if number == 2 else '') + suffix
                entry = await asyncio.to_thread(provider.entry, target)
                assert entry['directory'] == directory
                original = source + '/Child.md' if directory else source
                copied = target + '/Child.md' if directory else target
                def content(path):
                    with provider.open(path) as stream:
                        return stream.read()
                assert await asyncio.to_thread(content, original) == await asyncio.to_thread(content, copied)
        report['native_library_copy_' + storage] = True
        report['native_library_menu_edges_' + storage] = True

    async def check_private_copies(self, report):
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        from mobile.obsidian import open_vault
        self.show_cloud(present=False)
        restoring = getattr(self, 'cloud_restore_task', None)
        if restoring is not None:
            await restoring
        fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
        self.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
        root = self.private_root / 'PrivateCopyQA'
        root.mkdir(exist_ok=True)
        provider = CryptFiles(root, self.cloud_client, 'Secret')
        provider.create_file('Home.md', BytesIO(b'# Private copy fixture'))
        provider.mkdir('Long folder name for compact row preview')
        provider.create_file('Long folder name for compact row preview/Child.md', BytesIO(b'Private child'))
        report['localcrypt_inventory'] = [row['path'] for row in await asyncio.to_thread(provider.list)]
        owner = await open_vault(self, provider, '', 'files')
        if getattr(owner, 'tree_task', None) is not None:
            await owner.tree_task
        try:
            await self.check_library_copies(owner, report, 'localcrypt')
        finally:
            owner.dispose()
        await self.check_workspace_copies(report, provider=provider)

    async def check_workspace_copies(self, report, *, provider=None):
        await self.show_files(location=('Local files', ''))
        storage = 'local' if provider is None else 'localcrypt'
        if provider is not None:
            self.file_roots['QA LocalCrypt'] = provider
            self.file_changing_location = True
            try:
                self.file_storage.items = list(self.file_roots)
                self.file_storage.value = 'QA LocalCrypt'
                self.file_location.value = ''
            finally:
                self.file_changing_location = False
            await self.browse_files()
        provider = self.file_provider
        provider.create_file('Workspace.md', BytesIO(b'# Workspace copy'))
        provider.mkdir('Workspace Folder')
        provider.create_file('Workspace Folder/Child.md', BytesIO(b'Workspace child'))
        await self.browse_files()
        for source in ('Workspace.md', 'Workspace Folder'):
            browser = self.file_browser
            index = next(i for i, row in enumerate(browser.native_list.data) if row.title == source)
            native = browser.native_list._impl.native
            if self.apple_probe:
                from toga_iOS.libs import NSIndexPath
                cell = native.cellForRowAtIndexPath(NSIndexPath.indexPathForRow(index, inSection=0))
                button = cell.accessoryView
            else:
                native.setSelection(index)
                await asyncio.sleep(.3)
                row = native.getChildAt(index - native.getFirstVisiblePosition())
                button = row.getChildAt(row.getChildCount() - 1)
            await self.touch_native(button, fraction=.05)
            await self.wait_for(lambda: getattr(browser, '_item_menu', None) is not None, 'Workspace menu edge missed')
            menu = browser._item_menu
            assert 'Copy' in dict(menu.actions)
            # Select Copy through its actual native action-sheet/list label.
            if self.apple_probe:
                from rubicon.objc import ObjCClass
                from commonUtils.ui.native.keyboard import native_value
                def find(view):
                    if view.isKindOfClass(ObjCClass('UILabel')) and str(view.text) == 'Copy':
                        return view
                    for child in native_value(view.subviews):
                        result = find(child)
                        if result is not None:
                            return result
                label = find(menu.native.view)
            else:
                listing = menu.native.getListView()
                label = listing.getChildAt(next(i for i, (title, _) in enumerate(menu.actions) if title == 'Copy'))
            assert label is not None
            await self.touch_native(label)
            await self.wait_for(lambda: not self.cloud_busy, 'Workspace copy did not finish')
            await asyncio.sleep(.5)
            target = 'Workspace - Copy.md' if source.endswith('.md') else source + ' - Copy'
            assert (await asyncio.to_thread(provider.entry, target))['directory'] == (not source.endswith('.md'))
        report['native_workspace_file_folder_copy_' + storage] = True
        report['native_workspace_menu_edges_' + storage] = True
