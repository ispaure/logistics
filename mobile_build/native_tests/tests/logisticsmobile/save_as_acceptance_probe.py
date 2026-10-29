"""Focused FIX SAVE AS acceptance; synthetic providers, native UI, explicit tap checkpoints."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
import sys
from pathlib import Path
from threading import Event
import traceback
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.provider import ResourceCapabilities
from features.text_editor.resources import LocalTextCopies
from tests.logisticsmobile.destination_probe import DestinationProbe
from tests.logisticsmobile.fixtures import capture_window, make_books


class FixtureFiles(LocalFiles):
    """Use the generic provider listing path so failures/delays exercise that contract."""


class AcceptanceProbe(DestinationProbe):
    async def check_destinations(self):
        output = Path(self.paths.cache) / 'save-as-acceptance'
        output.mkdir(exist_ok=True)
        self.acceptance_output = output
        report = dict(success=False, backend=type(self._impl).__module__, cases=[])
        self.acceptance_report = report
        try:
            if '--taps' in sys.argv:
                self.show_cloud(present=False)
                if getattr(self, 'cloud_restore_task', None):
                    await self.cloud_restore_task
                await self.provider_source_save()
                await self.tap_workflow()
                report['success'] = True
                return
            if '--followup' in sys.argv:
                from tests.logisticsmobile.pdf_probe import PDFProbe
                await PDFProbe.probe(self)
                pdf = json.loads((Path(self.paths.cache) / 'pdf-evidence/result.json').read_text())
                assert pdf['success'], pdf
                self.record('native-pdf-render-search-page-and-controls')
                await self.layout_matrix()
                report['success'] = True
                return
            # Deliberately enter from a cold managed draft before cloud UI exists.
            self.new_document(name='Cold.txt', content='Cold unsaved draft')
            source, owner = self.current, self.editor_view
            await self.show_document_save_as()
            self.editor_picker().cancel_text_destination()
            assert self.current is source and self.editor_view is owner
            assert source.text == 'Cold unsaved draft'
            self.record('cold-managed-save-as-cancel')
            await self.provider_matrix()
            await self.lifecycle_matrix()
            await self.encrypted_matrix()
            await self.actions_matrix()
            await self.layout_matrix()
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            (output / 'result.json').write_text(json.dumps(report, indent=2))
            self.state('complete', **report)

    def record(self, name, **details):
        self.acceptance_report['cases'].append(dict(case=name, **details))
        (self.acceptance_output / 'progress.json').write_text(json.dumps(self.acceptance_report, indent=2))
        print('SAVE_AS_ACCEPTANCE=' + name, flush=True)

    async def provider_matrix(self):
        picker = self.editor_picker()
        root = self.private_root / 'AcceptanceProviders'
        root.mkdir()
        a, b = root / 'A', root / 'B'
        a.mkdir()
        b.mkdir()
        (a / 'same.md').write_bytes(b'A')
        (b / 'same.md').write_bytes(b'B')
        first, second = FixtureFiles(a), FixtureFiles(b)

        async def setup(name='draft.md', data=b'Native retained draft', provider=second):
            await picker.show_text_destination(name, data)
            picker.editor_storage_roots.update({'First': first, 'Second': provider})
            picker.save_as_storage.items = list(picker.editor_storage_roots)
            picker.save_as_storage.value = 'Second'
            await picker._storage_refresh

        await setup()
        for label in ('First', 'Second', 'First', 'Second'):
            picker.save_as_storage.value = label
            await picker._storage_refresh
            assert picker.editor_picker_location == (label, '')
            assert picker._listed_provider is (first if label == 'First' else second)
            assert not picker.picker_parent.enabled
            native = picker.picker_parent._impl.native
            assert not (native.isEnabled() if hasattr(native, 'isEnabled') else native.enabled)
        self.record('native-storage-same-name-root-and-parent-state')

        for name, expected in (('Bare', 'Bare.md'), ('UPPER.TXT', 'UPPER.TXT'),
                               ('Résumé 😀.md', 'Résumé 😀.md'), ('two.dots.md', 'two.dots.md'),
                               ('.hidden', '.hidden.md')):
            await setup()
            picker.save_as_name.value = name
            await picker.confirm_editor_file()
            assert (b / expected).read_bytes() == b'Native retained draft', picker.save_as_status.value
            owner = self.provider_sessions().active
            assert owner.crypt_reader.name == expected
            owner.crypt_text.value = 'Subsequent save'
            await owner.save_crypt()
            assert (b / expected).read_bytes() == b'Subsequent save'
            assert self.close_session(owner.session.id)
        self.record('native-filename-unicode-dots-uppercase-exact-bytes-and-next-save')
        await setup('Source.txt')
        picker.save_as_name.value = 'Text basename'
        await picker.confirm_editor_file()
        assert (b / 'Text basename.txt').read_bytes() == b'Native retained draft'
        assert self.close_session(self.provider_sessions().active.session.id)
        await setup()
        for invalid in ('', 'bad.exe', '../escape', 'nested/file.md', 'trailing.'):
            picker.save_as_name.value = invalid
            await picker.confirm_editor_file()
            assert picker.save_as_status.value and picker.save_as_data == b'Native retained draft'
        self.record('native-invalid-name-correction-retains-draft')

        for operation in ('list', 'mkdir', 'create_file'):
            await setup()
            if operation == 'list':
                with patch.object(second, operation, side_effect=PermissionError('Synthetic listing denied')):
                    assert not await picker.refresh_editor_browser()
                assert picker.editor_picker_location == (picker.save_as_storage.value, picker.picker_folder.value)
                assert await picker.refresh_editor_browser()
            elif operation == 'mkdir':
                picker.new_folder_name.value = 'Denied'
                with patch.object(second, operation, side_effect=PermissionError('Synthetic folder denied')):
                    await picker.create_picker_folder()
                assert picker.save_as_status.value and not (b / 'Denied').exists()
                await picker.create_picker_folder()
                assert picker.picker_folder.value == 'Denied'
            else:
                picker.save_as_name.value = 'Retry'
                with patch.object(second, operation, side_effect=PermissionError('Synthetic write denied')):
                    await picker.confirm_editor_file()
                assert picker.save_as_status.value and picker.save_as_data == b'Native retained draft'
                assert not (b / 'Retry.md').exists()
                await picker.confirm_editor_file()
                assert (b / 'Retry.md').read_bytes() == b'Native retained draft'
                assert self.close_session(self.provider_sessions().active.session.id)
            self.record('native-injected-permission-' + operation + '-retry')

        await setup()
        with patch.object(second, 'capabilities', ResourceCapabilities()):
            picker.update_picker_actions()
            assert not picker.picker_primary.enabled and not picker.picker_new_folder.enabled
        picker.update_picker_actions()
        assert picker.picker_primary.enabled and picker.picker_new_folder.enabled
        self.record('native-read-only-disabled-state-recovery')
        for changed in (False, True):
            await setup()
            (b / 'Conflict.md').write_bytes(b'Original')
            picker.save_as_name.value = 'Conflict.md'
            async def confirm(dialog):
                if changed:
                    (b / 'Conflict.md').write_bytes(b'External change')
                return True
            with patch.object(self.main_window, 'dialog', side_effect=confirm):
                await picker.confirm_editor_file()
            assert (b / 'Conflict.md').read_bytes() == (b'External change' if changed else b'Native retained draft')
            if changed:
                assert picker.save_as_data == b'Native retained draft'
            else:
                assert self.close_session(self.provider_sessions().active.session.id)
        self.record('native-confirmed-replacement-and-revision-conflict')
        await setup()
        picker.save_as_name.value = 'Published'
        with patch.object(LocalTextCopies, 'open', side_effect=OSError('Synthetic reopen failure')):
            await picker.confirm_editor_file()
        assert picker.save_as_data == b'Native retained draft' and picker.save_as_status.value
        self.record('native-injected-publication-reopen-failure', destination_exists=(b / 'Published.md').exists())
        picker.cancel_text_destination()
        await setup()
        picker.save_as_name.value = 'Presentation'
        async def unavailable(**kwargs):
            return False
        with patch.object(self, 'open_crypt', side_effect=unavailable):
            await picker.confirm_editor_file()
        assert (b / 'Presentation.md').read_bytes() == b'Native retained draft'
        assert picker.save_as_data == b'Native retained draft'
        assert 'could not be opened' in picker.save_as_status.value
        self.record('native-injected-editor-presentation-failure-retains-published-copy-and-draft')
        picker.cancel_text_destination()
        await self.show_editor_open()
        picker.editor_storage_roots['Open second'] = second
        picker.save_as_storage.items = list(picker.editor_storage_roots)
        picker.save_as_storage.value = 'Open second'
        await picker._storage_refresh
        picker.save_as_name.value = 'same.md'
        await picker.confirm_editor_file()
        owner = self.provider_sessions().active
        assert owner.crypt_reader.data == b'B'
        assert self.close_session(owner.session.id)
        self.record('native-shared-open-selected-provider-exact-content')

    async def lifecycle_matrix(self):
        picker = self.editor_picker()
        for invalidation in ('cancel', 'navigation', 'credentials'):
            await picker.show_text_destination('Pending.md', b'Pending draft')
            from commonUtils.runtime.resources.selection import ResourceSelection
            started, released = Event(), Event()
            original = ResourceSelection.list
            def delayed(*args, **kwargs):
                started.set()
                if not released.wait(10):
                    raise RuntimeError('Delayed native fixture not released')
                return original(*args, **dict(kwargs, cancelled=lambda: False))
            with patch.object(ResourceSelection, 'list', new=delayed):
                task = asyncio.create_task(picker.refresh_editor_browser())
                try:
                    await self.wait(started.is_set, timeout=10)
                    assert not picker.picker_primary.enabled and not picker.picker_parent.enabled
                    client = self.cloud_client
                    if invalidation == 'cancel':
                        picker.cancel_text_destination()
                    elif invalidation == 'navigation':
                        self.show_settings()
                    else:
                        self.cloud_client = object()
                    released.set()
                    assert not await task
                    if invalidation == 'navigation':
                        assert self.native_host.state.destination == 'settings'
                    self.cloud_client = client
                    assert not self.cloud_busy
                finally:
                    released.set()
                    await task
            picker.clear()
            self.record('native-delayed-list-' + invalidation + '-rejects-late-result')
        self.new_document(name='Closed.txt', content='Closed origin')
        key = self.editor_view.session.id
        await self.show_document_save_as()
        assert self.close_session(key, choice='keep')
        picker.cancel_text_destination(dismissed=True)
        assert key not in self.workspace.sessions
        self.record('native-source-closed-during-picker')
        from tests.logisticsmobile.save_as_origin_probe import Probe
        await Probe.check(self)
        origin = json.loads((Path(self.paths.cache) / 'save-as-origin-result.json').read_text())
        assert origin['success'], origin
        self.record('native-managed-provider-repeated-cancel-back')

    async def encrypted_matrix(self):
        fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
        self.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password',
                                  package_name='Synthetic.zip', session_only=True)
        await asyncio.sleep(.5)
        from features.rclone.localcrypt.mobile.resources import CryptFiles, encrypted_copies
        provider = CryptFiles(self.private_root / 'AcceptanceEncrypted', self.cloud_client, 'Secret')
        picker = self.editor_picker()
        await picker.show_text_destination('Private.md', b'Encrypted exact bytes')
        picker.editor_storage_roots['Encrypted fixture'] = provider
        picker.save_as_storage.items = list(picker.editor_storage_roots)
        picker.save_as_storage.value = 'Encrypted fixture'
        await picker._storage_refresh
        for name in ('Nested', 'Inner'):
            picker.new_folder_name.value = name
            await picker.create_picker_folder()
            assert not picker.save_as_status.value, picker.save_as_status.value
        picker.save_as_name.value = 'Private basename'
        await picker.confirm_editor_file()
        key = 'Nested/Inner/Private basename.md'
        assert encrypted_copies(provider).open(key).data == b'Encrypted exact bytes', picker.save_as_status.value
        assert b'Encrypted exact bytes' not in provider._physical(key).read_bytes()
        owner = self.provider_sessions().active
        owner.crypt_text.value = 'Encrypted subsequent save'
        await owner.save_crypt()
        assert encrypted_copies(provider).open(key).data == b'Encrypted subsequent save'
        await picker.show_crypt_save_as(owner=owner)
        picker.cancel_text_destination()
        assert self.provider_sessions().active is owner
        assert self.close_session(owner.session.id)
        self.record('native-real-localcrypt-nested-create-save-reopen-next-save-cancel')
        from tests.logisticsmobile.file_mutation_checks import exercise_destination_edges
        await exercise_destination_edges(self)
        self.record('native-keyboard-portrait-landscape-errors-switch-overwrite-cancel')

    async def actions_matrix(self):
        self.new_document(name='Actions.md', content='# Alpha\nAlpha body')
        owner = self.editor_view
        await owner.choose_mode('Source')
        owner.toggle_search()
        owner.search.query.value = 'Alpha'
        owner.search.replacement.value = 'Beta'
        owner.search.changed()
        owner.search.next()
        assert owner.search.span is not None
        owner.search.replace_all()
        assert owner.document.text == '# Beta\nBeta body'
        owner.toggle_search()
        await owner.save()
        assert self.store.open(owner.document.id).text == '# Beta\nBeta body'
        original = owner.document.id
        self.save_copy()
        assert self.current.id != original and self.current.text == '# Beta\nBeta body'
        owner = self.editor_view
        await owner.choose_mode('Formatted')
        await asyncio.sleep(.7)
        assert owner.formatted.view in owner.editor_area.children
        await owner.choose_mode('Source')
        assert owner.editor in owner.editor_area.children
        self.show_preview()
        from tests.logisticsmobile.web_checks import wait_for_text
        await wait_for_text(self.preview, 'Beta body')
        self.record('native-save-copy-find-replace-markdown-source-formatted-preview')
        for show in (self.show_home, self.show_locations, self.show_documents_hub, self.show_chat, self.show_settings):
            show()
            await asyncio.sleep(.2)
        nav = self.settings_navigation
        names = list(nav.sections)
        expected = ['App', 'Appearance', 'Read aloud', 'Markdown', 'Text', 'EPUB',
                    'Books & Comics', 'LM Chat', 'Workspaces', 'Reset', 'Help', 'About']
        from features.images.mobile.burst_camera import available
        if available(self):
            expected.insert(2, 'Camera')
        assert names == expected, names
        for name in names:
            nav.choose(name)
            await asyncio.sleep(.1)
            assert nav.sections[name] is not None
        self.record('native-main-destinations-all-settings-categories', categories=names)
        root = self.private_root / 'AcceptanceBooks'
        root.mkdir()
        epub, comic = make_books(root)
        from commonUtils.runtime.resources.documents import LocalDocuments
        for path in (epub, comic):
            record = await asyncio.to_thread(self.reader_manager().catalog.library_store.import_book, LocalDocuments(), path)
            await self.open_book(record['id'])
            reader = self.reader_manager().active
            assert reader.book_reader is not None, reader.book_status.text
            await self.next_book_page()
            assert reader.book_record['position'] == 1 or path == epub
            if path == epub:
                await self.toggle_bookmark()
            reader.show_reader_tools()
            reader.show_library()
            self.record('native-reader-sample-' + path.suffix[1:])
        from tests.logisticsmobile.pdf_probe import PDFProbe
        await PDFProbe.probe(self)
        pdf = json.loads((Path(self.paths.cache) / 'pdf-evidence/result.json').read_text())
        assert pdf['success'], pdf
        self.record('native-pdf-render-search-page-and-controls')

    async def layout_matrix(self):
        from tests.logisticsmobile.rotation_checks import rotate, assert_visible_controls
        from mobile.appearance import refresh_appearance
        picker = self.editor_picker()
        apple = type(self._impl).__module__.startswith('toga_iOS.')
        for theme in ('light', 'dark'):
            if apple:
                self.main_window._impl.native.overrideUserInterfaceStyle = 1 if theme == 'light' else 2
            else:
                from java import jclass
                manager = self._impl.native.getSystemService(jclass('android.content.Context').UI_MODE_SERVICE)
                manager.setApplicationNightMode(1 if theme == 'light' else 2)
            refresh_appearance(self)
            for orientation in ('portrait', 'landscape-left'):
                await rotate(self, orientation)
                await picker.show_text_destination('Accessible.md', b'Accessible draft')
                # Large application control text exercises the supported Toga
                # layout independently of the OS font-scale run by the driver.
                for control in (picker.save_as_name, picker.picker_new_folder,
                                picker.picker_primary, *picker.picker_actions.children):
                    control.style.font_size = 24
                picker.save_as_name.value = 'unsupported.exe'
                await picker.confirm_editor_file()
                assert picker.save_as_status.value
                await asyncio.sleep(.4)
                assert_visible_controls(self)
                native = picker.picker_new_folder._impl.native
                if apple:
                    from rubicon.objc import CGSize
                    title = native.titleLabel
                    assert title.sizeThatFits(CGSize(10000, 10000)).width <= title.bounds.size.width + 1
                else:
                    layout = native.getLayout()
                    assert layout is not None and layout.getEllipsisCount(0) == 0
                await capture_window(self, self.acceptance_output / f'large-{theme}-{orientation}.png')
                assert picker.save_as_data == b'Accessible draft'
                self.record('native-large-text-theme-layout', theme=theme, orientation=orientation)
                picker.cancel_text_destination()
        await rotate(self, 'portrait')

    async def provider_source_save(self):
        root = self.private_root / 'ProviderSourceAcceptance'
        root.mkdir()
        (root / 'Original.txt').write_bytes(b'Original bytes')
        provider = LocalFiles(root)
        assert await self.open_crypt(copies=LocalTextCopies(provider), key='Original.txt', edit=True)
        source = self.provider_sessions().active
        source.crypt_text.value = 'Provider source unsaved draft'
        picker = self.editor_picker()
        await picker.show_crypt_save_as(owner=source)
        picker.save_as_name.value = 'Provider copy'
        await picker.confirm_editor_file()
        saved = self.provider_sessions().active
        assert saved is not source and saved.crypt_reader.name == 'Provider copy.txt', picker.save_as_status.value
        assert (root / 'Original.txt').read_bytes() == b'Original bytes'
        assert (root / 'Provider copy.txt').read_bytes() == b'Provider source unsaved draft'
        saved.crypt_text.value = 'Provider copy subsequent save'
        await saved.save_crypt()
        assert (root / 'Provider copy.txt').read_bytes() == b'Provider copy subsequent save'
        assert self.close_session(saved.session.id)
        assert self.close_session(source.session.id, choice='discard')
        self.record('native-provider-origin-save-as-new-copy-and-subsequent-save')

    async def tap_workflow(self):
        picker = self.editor_picker()
        self.new_document(name='Tap source.txt', content='')
        self.show_documents(edit=True, destination='documents')
        if type(self._impl).__module__.startswith('toga_android.'):
            self.editor_view.editor._impl.native.setContentDescription('Save As acceptance source')
        self.tap_origin = self.current
        self.state('tap-source', instructions='Type Tap draft exact bytes; choose Save As from Document actions')
        deadline = self.loop.time() + 240
        while self.tap_origin.text != 'Tap draft exact bytes':
            self.state('tap-source', text=self.tap_origin.text, editor=self.editor_view.editor.value,
                       name=self.tap_origin.name)
            assert self.loop.time() < deadline, 'Actual source typing did not produce the expected draft'
            await asyncio.sleep(.1)
        if type(self._impl).__module__.startswith('toga_iOS.'):
            button = self.editor_view.actions_button
            native, item = button._impl.native, getattr(button, '_ios_action_item', None)
            def labels(menu):
                if menu is None:
                    return []
                return [str(child.title) for child in menu.children]
            (Path(self.paths.cache) / 'menu-state.json').write_text(json.dumps(dict(
                actions=[title for title, action in self.editor_view.actions.actions],
                native_menu=labels(native.menu), primary=bool(native.showsMenuAsPrimaryAction),
                item_menu=labels(item.menu) if item else [],
                target=str(item.target) if item else '', action=str(item.action) if item else '')))
        await self.wait(lambda: picker.save_as_data is not None, timeout=240)
        assert self.tap_origin.text == 'Tap draft exact bytes'
        await self.wait(lambda: picker._listed_provider is not None and not self.cloud_busy)
        provider = picker._listed_provider
        self.state('tap-save', instructions='New folder: Tapped; filename: Tapped copy; Save here')
        await self.wait(lambda: picker.save_as_data is None, timeout=240)
        assert (provider.root / 'Tapped/Tapped copy.txt').read_bytes() == b'Tap draft exact bytes'
        assert self.provider_sessions().active.crypt_reader.name == 'Tapped copy.txt'
        self.record('actual-taps-new-folder-name-save-reopen')
        self.new_document(name='Menu source.txt', content='Menu draft retained')
        self.show_documents(edit=True, destination='documents')
        self.state('tap-menus')
        await self.wait(lambda: (Path(self.paths.cache) / 'tap-menus-complete').exists(), timeout=240)
        assert self.current.text == 'Menu draft retained'
        assert self.editor_view.export_button.enabled
        if type(self._impl).__module__.startswith('toga_iOS.'):
            from commonUtils.ui.native.documents import _ios_pickers
            assert self.main_window.id not in _ios_pickers, "Dismissed system picker retained its pending operation"
        self.record('actual-menu-taps-open-export-cancel-draft-preserved')


def main():
    return AcceptanceProbe('Save As acceptance QA', 'io.github.ispaure.logisticssaveasqa')
