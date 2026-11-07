"""Disposable native creation flow with the compiled LocalCrypt bridge."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticscreationqa'


class CreationProbe(LogisticsMobile):
    def startup(self):
        import logging
        logging.getLogger().addHandler(logging.FileHandler(Path(self.paths.cache) / 'markdown-qa-python.log', mode='w'))
        self.storage_root = Path(self.paths.cache) / ('creation-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not hasattr(self, 'creation_check'):
            self.creation_check = self.loop.create_task(self.check_creation())

    async def new_form(self):
        picker = self.editor_picker()
        from .fixtures import choose_creation_type
        await choose_creation_type(self, 'txt')
        assert picker.panel is picker.name_panel
        assert picker.next_button.enabled
        return picker

    async def capture_system_keyboard(self, pose):
        from commonUtils.testing.waiting import wait_until
        output = Path(self.paths.cache) / 'document-creation-evidence'
        done = output / 'keyboard-done'
        done.unlink(missing_ok=True)
        request = output / 'keyboard-request.tmp'
        request.write_text(json.dumps(dict(pose=pose)))
        request.replace(output / 'keyboard-request.json')
        await wait_until(done.exists, timeout=30, message='System keyboard screenshot was not captured')

    async def check_keyboard_steps(self, pose='portrait'):
        from mobile.keyboard import picker_keyboard_visible
        from .fixtures import capture_window
        from .rotation_checks import rotate
        if not type(self._impl).__module__.startswith('toga_iOS.'):
            (Path(self.paths.cache) / 'creation-orientation').write_text(pose)
        await rotate(self, pose)
        picker = await self.new_form()
        picker.save_as_name.value = 'Field notes'
        await asyncio.sleep(.3)
        await capture_window(self, Path(self.paths.cache) / f'creation-formats-{pose}.png')
        field = picker.save_as_name._impl.native
        adapter = self.native_host.adapter
        ios = type(self._impl).__module__.startswith('toga_iOS.')
        from commonUtils.testing.waiting import settled_keyboard
        if ios:
            def request():
                if field.window is not None:
                    field.becomeFirstResponder()
            def ready():
                return bool(field.isFirstResponder)
        else:
            from android.content import Context
            from java import jclass
            manager = field.getContext().getSystemService(Context.INPUT_METHOD_SERVICE)
            ime = jclass('androidx.core.view.WindowInsetsCompat$Type').ime()
            controller = jclass('androidx.core.view.WindowCompat').getInsetsController(
                self._impl.native.getWindow(), field)
            def request():
                field.requestFocus()
                if field.hasWindowFocus() and manager.isActive(field):
                    controller.show(ime)
                    manager.showSoftInput(field, 0)
            def ready():
                return bool(field.hasWindowFocus() and field.hasFocus() and manager.isActive(field))
        assert await settled_keyboard(request, lambda: picker_keyboard_visible(self, adapter),
                                      ready=ready, attempts=100), 'Filename keyboard did not appear'
        await asyncio.sleep(.4)
        assert picker.next_button.enabled and picker.name_form.layout.height >= 44
        formats = picker.creation_formats
        if formats.tabbed:
            assert formats.tabs.parent is picker.name_content and formats.cards.parent is None
        if formats.compact:
            assert formats.row.parent is picker.name_content and formats.cards.parent is None
            assert formats.change.enabled
        if ios:
            window = self.main_window._impl.native
            rect = field.convertRect(field.bounds, toView=window)
            keyboard = window.convertRect(adapter.keyboard_frame, fromCoordinateSpace=window.screen.coordinateSpace)
            def frame(value):
                return [round(float(value.origin.x), 1), round(float(value.origin.y), 1),
                        round(float(value.size.width), 1), round(float(value.size.height), 1)]
            scroll = picker.name_form._impl.native
            geometry = dict(field=frame(rect), keyboard=frame(keyboard), inset=adapter.keyboard_inset,
                form=frame(scroll.convertRect(scroll.bounds, toView=window)),
                form_bounds=frame(scroll.bounds), panel=frame(picker.name_panel._impl.native.bounds),
                window=frame(window.bounds), compact=picker._compact_keyboard,
                tabs=frame(picker.creation_formats.tabs._impl.native.bounds))
            assert rect.origin.y >= 0 and rect.origin.y + rect.size.height <= keyboard.origin.y + 1, geometry
        else:
            from android.graphics import Rect
            action = picker.picker_primary if picker.creation_layout.paired else picker.next_button
            tabs = tuple(tab._impl.native for tab in formats.tab_buttons.values()) if formats.tabbed else ()
            for control in (field, action._impl.native, *tabs):
                visible = Rect()
                assert control.getGlobalVisibleRect(visible) and visible.height() >= control.getHeight() - 1
                assert visible.width() >= control.getWidth() - 1
            for control in tabs:
                density = control.getResources().getDisplayMetrics().density
                assert control.getHeight() / density >= 44 - 1 / density
                text = control.getLayout()
                assert text is not None
                assert all(text.getEllipsisCount(i) == 0 for i in range(text.getLineCount())), 'Format title is truncated'
                assert (text.getLineBottom(text.getLineCount() - 1) <= control.getHeight()
                        - control.getCompoundPaddingTop() - control.getCompoundPaddingBottom() + 1), dict(
                    error='Format title is clipped', title=str(control.getText()), height=control.getHeight(),
                    lines=text.getLineCount(), text_bottom=text.getLineBottom(text.getLineCount() - 1),
                    padding=(control.getCompoundPaddingTop(), control.getCompoundPaddingBottom()))
        await capture_window(self, Path(self.paths.cache) / f'creation-name-{pose}.png')
        await self.capture_system_keyboard(pose)
        if ios:
            rect = field.convertRect(field.bounds, toView=window)
            keyboard = window.convertRect(adapter.keyboard_frame, fromCoordinateSpace=window.screen.coordinateSpace)
            assert rect.origin.y >= 0 and rect.origin.y + rect.size.height <= keyboard.origin.y + 1
            await capture_window(self, Path(self.paths.cache) / f'creation-name-{pose}.png')
            scroll = picker.name_form._impl.native
            input_rect = field.convertRect(field.bounds, toView=scroll)
            assert input_rect.origin.y >= scroll.bounds.origin.y - 1
            assert (input_rect.origin.y + input_rect.size.height <=
                    scroll.bounds.origin.y + scroll.bounds.size.height + 1), 'Name input is clipped by its scroll viewport'
            if formats.compact:
                change = formats.change._impl.native
                bounds = change.convertRect(change.bounds, toView=window)
                assert bounds.origin.y >= 0 and bounds.origin.y + bounds.size.height <= keyboard.origin.y + 1
                assert bounds.size.height >= 44, 'Change format lost its touch target'
            if formats.tabbed:
                for tab in formats.tab_buttons.values():
                    native = tab._impl.native
                    bounds = native.convertRect(native.bounds, toView=window)
                    assert bounds.size.width >= 44 and bounds.size.height >= 44
                    assert bounds.origin.x >= 0 and bounds.origin.x + bounds.size.width <= window.bounds.size.width + 1
                    assert bounds.origin.y + bounds.size.height <= keyboard.origin.y + 1
        location, original = picker.editor_picker_location, picker.save_as_name
        if formats.tabbed:
            formats.tab_buttons['Markdown (.md)'].on_press()
            assert picker_keyboard_visible(self, adapter), 'Changing a phone tab dismissed the keyboard'
            assert bool(field.isFirstResponder) if ios else bool(field.hasFocus())
        else:
            formats.change.on_press()
            for _ in range(50):
                if not picker_keyboard_visible(self, adapter):
                    break
                await asyncio.sleep(.1)
            assert not picker_keyboard_visible(self, adapter), 'Change format did not dismiss the keyboard'
            assert formats.cards.parent is picker.name_view and not formats.compact
            formats.buttons['Markdown (.md)'].on_press()
        assert picker.save_as_name is original and picker.destination_filename() == 'Field notes.md'
        assert picker.editor_picker_location == location
        await capture_window(self, Path(self.paths.cache) / f'creation-change-format-{pose}.png')
        await picker.choose_creation_location()
        for _ in range(50):
            if not picker_keyboard_visible(self, adapter):
                break
            await asyncio.sleep(.1)
        assert not picker_keyboard_visible(self, adapter), 'Keyboard stayed open over locations'
        await capture_window(self, Path(self.paths.cache) / f'creation-locations-{pose}.png')
        await picker.browser_editor_location(('Local', ''))
        assert picker.picker_primary.enabled
        await asyncio.sleep(.4)
        assert picker.editor_picker_location == ('Local', '') and picker.picker_primary.enabled
        assert 'Local' in picker.picker_destination.text
        await capture_window(self, Path(self.paths.cache) / f'creation-location-{pose}.png')
        from services.documents.locations import collection_path
        root = collection_path(self.private_root)
        for name, parent in (('Projects', ''), ('Notes', 'Projects'), ('Research', 'Projects')):
            await picker.browser_editor_location(('Local', parent))
            if not (root / parent / name).exists():
                picker.show_new_folder()
                picker.new_folder_name.value = name
                await picker.create_picker_folder()
                assert picker.editor_picker_location == ('Local', '/'.join(filter(None, (parent, name))))
        await picker.browser_editor_location(('Local', 'Projects'))
        await asyncio.sleep(.3)
        assert not (root / 'Projects/Field notes.md').exists()
        assert picker.destination_filename() == 'Field notes.md'
        if not ios:
            for widget in (picker.picker_primary, picker.picker_new_folder):
                native = widget._impl.native
                rect = Rect()
                assert native.getGlobalVisibleRect(rect)
                assert rect.height() >= native.getHeight() - 1
                assert rect.width() >= native.getWidth() - 1
            assert picker.editor_browser.scroll_container().layout.height >= 44, 'Browser has no usable space'
        await capture_window(self, Path(self.paths.cache) / f'creation-folders-{pose}.png')
        picker.cancel_text_destination()

    async def check_adaptive_creation(self):
        from .rotation_checks import rotate
        from .fixtures import capture_window
        from mobile.fold_layout import division
        self.show_home()
        origin = self.body
        picker = await self.new_form()
        layout = picker.creation_layout
        picker.save_as_name.value = 'Rotation draft'
        picker.creation_type.value = 'Markdown (.md)'
        await picker.choose_creation_location()
        await picker.browser_editor_location(('Local', ''))
        samples = []
        for pose in ('landscape-left', 'portrait'):
            if not layout.apple:
                # Large-screen Android may ignore activity orientation requests.
                # Its disposable tablet driver rotates the display itself.
                (Path(self.paths.cache) / 'creation-orientation').write_text(pose)
            await rotate(self, pose)
            await asyncio.sleep(.4)
            assert picker.visible() and picker.editor_picker_location == ('Local', '')
            assert picker.panel is picker.location_panel and picker.destination_filename() == 'Rotation draft.md'
            assert (picker.name_panel.parent is layout) == layout.paired
            assert picker.location_panel.parent is layout
            fold = division(self, layout)
            left, gap = picker.name_panel.layout.content_width, layout.gutter.layout.content_width
            if layout.paired and fold is not None:
                assert abs(left - fold.x) <= 2 and abs(gap - fold.width) <= 2
            if layout.paired:
                picker.save_as_name.value = '../invalid'
                picker.update_effective_name()
                assert not picker.picker_primary.enabled
                picker.save_as_name.value = 'Rotation draft'
                picker.update_effective_name()
                assert picker.picker_primary.enabled
            if not layout.apple:
                from android.graphics import Rect
                button = picker.picker_primary._impl.native
                bounds = Rect()
                density = button.getResources().getDisplayMetrics().density
                assert button.getGlobalVisibleRect(bounds), 'Create is outside the viewport'
                assert bounds.height() / density >= 44, (pose, bounds.height(), density, layout.layout.height)
            samples.append(dict(pose=pose, paired=layout.paired, width=layout.layout.content_width,
                                left=left, gap=gap, fold=vars(fold) if fold else None))
            await capture_window(self, Path(self.paths.cache) / f'creation-{pose}.png')
        if (Path(self.paths.cache) / 'drive-folds').exists():
            from commonUtils.testing.waiting import wait_until
            # The Duo has a vertical book crease in landscape. In portrait
            # the same crease runs horizontally across the form.
            await rotate(self, 'landscape-left')
            folder = Path(self.paths.cache) / 'document-creation-evidence'
            for angle in (0, 180, 127):
                change = dict(angle=angle)
                pending = folder / 'fold-request.tmp'
                pending.write_text(json.dumps(change))
                pending.replace(folder / 'fold-request.json')
                done = folder / 'fold-done.json'
                done.unlink(missing_ok=True)
                await wait_until(lambda: done.exists() and json.loads(done.read_text()) == change,
                                 timeout=50, message='Duo hinge request timed out')
                if angle:
                    await rotate(self, 'landscape-left')
                await wait_until(lambda: layout.paired == (angle != 0), timeout=10,
                                 message=lambda: f'Duo at {angle} degrees: {layout.signature}, {division(self, layout)}')
                if angle == 127:
                    fold = division(self, layout)
                    assert fold is not None and fold.vertical
                    assert abs(picker.name_panel.layout.content_width - fold.x) <= 2
                    assert abs(layout.gutter.layout.content_width - fold.width) <= 2
                assert picker.visible() and picker.editor_picker_location == ('Local', '')
                assert picker.destination_filename() == 'Rotation draft.md'
                samples.append(dict(angle=angle, paired=layout.paired, width=layout.layout.content_width))
        paired = layout.paired
        if layout.apple:
            # Exercise the actual leading bar item in both layouts.
            button = layout.name_cancel if paired else picker.edit_name
            item = button._ios_action_item
            item.target.performSelector(item.action, withObject=item)
            await asyncio.sleep(.3)
        else:
            self.routes.back()
        if not paired:
            assert picker.panel is picker.name_panel and picker.save_as_name.value == 'Rotation draft'
            self.routes.back()
        assert self.body is origin and not picker.visible()
        return samples

    async def create_in(self, filename, location, kind='Plain text (.txt)'):
        self.show_home()
        before = self.store.documents()
        form = await self.new_form()
        form.save_as_name.value = filename
        form.creation_type.value = kind
        await form.choose_creation_location()
        picker = self.editor_picker()
        assert self.store.documents() == before
        assert not any(label.startswith('Remote') for label in picker.editor_storage_roots)
        assert picker.editor_picker_location == ('Shared Files', ''), (picker.panel is picker.name_panel,
            picker.cloud_busy, picker.effective_name.text, picker.save_as_status.value)
        picker.save_as_storage.value = location
        # UIKit may finish its push after the async action returns. Match a
        # user's next action after presentation, rather than cancelling the
        # listing with a still-pending navigation generation change.
        await asyncio.sleep(.3)
        assert await picker.refresh_editor_browser(), picker.save_as_status.value
        await picker.confirm_editor_file()
        owner = self.private_sessions.active
        assert owner is not None, picker.save_as_status.value
        assert owner.crypt_reader.name == filename
        content = 'Native created document: ' + location
        if owner.crypt_reader.kind in ('.md', '.markdown'):
            owner.crypt_edit_mode.value = 'Source'
        owner.crypt_text.value = content
        await owner.save_crypt()
        assert not owner.private_dirty()
        provider = owner._crypt_reader_store.provider
        assert filename in [row['name'] for row in provider.list()]
        if provider.private:
            raw = provider._physical(filename).read_bytes()
            assert raw and content.encode() not in raw
        else:
            assert (provider.root / filename).read_text() == content
        assert self.store.documents() == before
        assert all(route not in ('new-document', 'text-destination')
                   for route, *_ in self.routes.screens['home'])
        assert self.private_sessions.close(owner.session.id, discard=True)
        return dict(location=location, encrypted=provider.private)

    async def create_notebook(self):
        from features.notebooks.notebook import Notebook
        self.show_home()
        form = await self.new_form()
        form.save_as_name.value = 'Native notebook'
        form.creation_type.value = 'Remarkable Document (.rmdoc)'
        await form.choose_creation_location()
        await asyncio.sleep(.3)
        picker = self.editor_picker()
        assert picker.editor_picker_location == ('Shared Files', ''), (picker.panel is picker.name_panel,
            picker.cloud_busy, picker.effective_name.text, picker.save_as_status.value)
        row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'Local')
        assert await picker.browser_editor_folder(row), picker.save_as_status.value
        assert picker.picker_parent.enabled
        await picker.parent_editor_folder()
        assert picker.editor_picker_location == ('Shared Files', ''), (picker.panel is picker.name_panel,
            picker.cloud_busy, picker.effective_name.text, picker.save_as_status.value)
        assert await picker.browser_editor_folder(row), picker.save_as_status.value
        picker.show_new_folder()
        picker.new_folder_name.value = 'Test'
        assert not picker.picker_primary.enabled
        await picker.confirm_editor_file()
        assert picker.visible() and picker.creating_notebook()
        await picker.create_picker_folder()
        assert picker.picker_folder.value == 'Test', picker.save_as_status.value
        assert picker.effective_name.text == 'Save as: Native notebook.rmdoc'
        picker.show_creation_name()
        picker.save_as_name.value = 'Invalid.txt'
        await picker.choose_creation_location()
        assert picker.panel is picker.name_panel and not picker.next_button.enabled
        assert 'ending in .rmdoc' in picker.effective_name.text
        picker.save_as_name.value = 'Native notebook'
        await picker.choose_creation_location()
        assert picker.editor_picker_location == ('Local', 'Test')
        path = picker.editor_provider('Local').root / 'Test/Native notebook.rmdoc'
        await picker.confirm_editor_file()
        assert path.is_file(), picker.save_as_status.value
        assert Notebook.read(path.read_bytes()).name == 'Native notebook'
        assert self.notebook_panel.session.provider == 'notebook'
        assert self.close_session(self.notebook_panel.session.id)
        return dict(location='Local / Test', format='rmdoc', validation_retry=True)

    async def check_creation(self):
        output = Path(self.paths.cache) / 'document-creation-evidence'
        output.mkdir(parents=True, exist_ok=True)
        report = dict(success=False, cases=[])
        try:
            if getattr(self, 'startup_task', None) is not None:
                await asyncio.shield(self.startup_task)
            for pose in ('portrait', 'landscape-left', 'landscape-right'):
                await self.check_keyboard_steps(pose)
                report['cases'].append(dict(keyboard_steps=pose, change_format=True))
            report['layouts'] = await self.check_adaptive_creation()
            report['cases'].append(await self.create_in('Ordinary.txt', 'Local'))
            report['cases'].append(await self.create_in('Note.md', 'Received Files', 'Markdown (.md)'))
            report['cases'].append(await self.create_notebook())
            self.show_cloud(present=False)
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
            self.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password',
                                      package_name='Synthetic.zip', session_only=True)
            remote = next(iter(fixture['copies'].values()))['record']['remote']
            self.cloud_crypt_remotes = {remote}
            from features.rclone.localcrypt.mobile.resources import CryptFiles
            from services.documents.storage import DocumentResource
            provider = CryptFiles(self.private_root / 'LocalCryptFolders', self.cloud_client, remote)
            DocumentResource.publish(provider, 'Existing.txt', b'Encrypted fixture', max_bytes=1024)
            report['cases'].append(await self.create_in('Encrypted.txt', 'LocalCrypt: ' + remote))
            self.show_home()
            form = await self.new_form()
            form.save_as_name.value = 'My notebook'
            form.creation_type.value = 'Remarkable Document (.rmdoc)'
            await form.choose_creation_location()
            await form.browser_editor_location(('Local', ''))
            await asyncio.sleep(.5)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    return CreationProbe('Document Creation QA', BUNDLE)
