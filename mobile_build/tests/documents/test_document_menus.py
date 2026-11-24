"""Shared document commands follow available space and retain storage context."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch

from commonUtils.runtime.resources.documents import LocalDocuments
from mobile.app import LogisticsMobile
from mobile.document_sources import folder_action, show_in_folder
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from mobile_build.tests.support.pdf import PDF, native_pdf
from mobile_build.tests.support.readers import RemoteClient
from mobile.action_menu import DocumentNativeMenu


class NativeDocumentMenuTests(TestCase):
    def test_ios_share_offers_file_contents_as_an_attachment(self):
        from mobile import outbound_share

        path = Path('cache/Selected file.bin')
        url, configuration, payload = object(), object(), object()
        data = SimpleNamespace(identifier='public.data')
        inferred = SimpleNamespace(identifier='dyn.test-binary', isDynamic=lambda: True)
        types = SimpleNamespace(typeWithIdentifier=Mock(return_value=data),
                                typeWithFilenameExtension=Mock(return_value=inferred))
        provider = Mock()
        sheet = SimpleNamespace(popoverPresentationController=None)
        app = SimpleNamespace()

        def present(controller, **_kwargs):
            self.assertIs(controller, sheet)
            controller.completionWithItemsHandler(None, True, None, None)

        presenter = SimpleNamespace(presentViewController=present)
        provider_factory = Mock()
        provider_factory.instancesRespondToSelector.return_value = True
        provider_factory.alloc.return_value.init.return_value = provider
        provider_factory.alloc.return_value.initWithContentsOfURL.return_value = provider
        config_factory = Mock()
        config_factory.alloc.return_value.initWithItemProviders.return_value = configuration
        controller_factory = Mock()
        controller_factory.alloc.return_value.initWithActivityItemsConfiguration.return_value = sheet
        classes = {'NSURL': SimpleNamespace(fileURLWithPath=Mock(return_value=url)), 'UTType': types,
                   'NSItemProvider': provider_factory, 'UIActivityItemsConfiguration': config_factory,
                   'UIActivityViewController': controller_factory,
                   'NSData': SimpleNamespace(dataWithContentsOfURL=Mock(return_value=payload))}
        completion = Mock()
        bridge = SimpleNamespace(ObjCClass=classes.__getitem__, Block=lambda handler, *_: handler,
                                 ObjCBlock=Mock(return_value=completion), CGRect=object,
                                 objc_id=object, objc_block=object, SEL=lambda name: name)
        with patch.dict('sys.modules', {'rubicon.objc': bridge}), \
                patch.object(outbound_share, '_ios_presenter', new=AsyncMock(return_value=(None, presenter))):
            self.assertTrue(asyncio.run(outbound_share._send_ios(app, path, lambda: None, None)))
            register_data = provider.registerDataRepresentationForTypeIdentifier
            self.assertEqual(register_data.call_args.args, (data.identifier,))
            register_data.call_args.kwargs['loadHandler'](object())
            completion.assert_called_once_with(payload, None)
            completion.reset_mock()
            self.assertEqual(provider.suggestedName, path.name)
            self.assertEqual([call[0] for call in provider.mock_calls],
                             ['registerDataRepresentationForTypeIdentifier', 'registerObject'])
            provider.reset_mock()
            known = SimpleNamespace(identifier='com.adobe.pdf', isDynamic=lambda: False,
                                    conformsToType=lambda _: True)
            types.typeWithFilenameExtension.return_value = known
            path = path.with_suffix('.pdf')
            outbound_share._ios_file_provider(path)
            provider_factory.alloc.return_value.initWithContentsOfURL.assert_called_once_with(
                url, contentType=known, openInPlace=False, coordinated=False, visibility=0)
            provider.registerObject.assert_called_once_with(url, visibility=0)
            provider.reset_mock()
            provider_factory.instancesRespondToSelector.return_value = False
            outbound_share._ios_file_provider(path)
        self.assertEqual(types.typeWithFilenameExtension.call_args.args, ('pdf',))
        register = provider.registerFileRepresentationForTypeIdentifier
        register.assert_called_once()
        self.assertEqual(register.call_args.args, (known.identifier,))
        self.assertEqual(register.call_args.kwargs['fileOptions'], 0)
        provider.registerObject.assert_called_once_with(url, visibility=0)
        self.assertEqual([call[0] for call in provider.mock_calls],
                         ['registerFileRepresentationForTypeIdentifier', 'registerObject'])
        register.call_args.kwargs['loadHandler'](object())
        completion.assert_called_once_with(url, False, None)
        self.assertEqual(provider.suggestedName, path.name)
        config_factory.alloc.return_value.initWithItemProviders.assert_called_once_with([provider])
        controller_factory.alloc.return_value.initWithActivityItemsConfiguration.assert_called_once_with(configuration)

    def test_apple_item_share_menu_uses_system_sharing_glyph(self):
        from mobile.action_menu import ios_menu_actions
        from mobile.outbound_share import SEND
        image = Mock()
        action = SimpleNamespace(actionWithTitle=lambda title, **kwargs: SimpleNamespace(title=title, **kwargs))
        classes = {'UIImage': image, 'UIAction': action}
        bridge = SimpleNamespace(ObjCClass=classes.__getitem__, Block=lambda handler, *_: handler, objc_id=object)
        chosen = Mock()
        with patch.dict('sys.modules', {'rubicon.objc': bridge}):
            [row] = ios_menu_actions([(SEND, chosen)], lambda callback: callback(), [])
        image.systemImageNamed.assert_called_once_with('square.and.arrow.up')
        self.assertIs(row.image, image.systemImageNamed.return_value)
        row.handler(None)
        chosen.assert_called_once()

    def test_apple_sections_keep_command_handlers_and_use_inline_group_separators(self):
        calls = []
        actions = [(title, lambda title=title: calls.append(title))
                   for title in ('Read aloud…', 'Appearance…', 'Show in folder', 'Delete document…')]
        native = SimpleNamespace()
        impl = type('AppleButton', (), {'__module__': 'toga_iOS.widgets.button'})()
        impl.native = native
        button = SimpleNamespace(_impl=impl)
        menu_class = SimpleNamespace(menuWithTitle=lambda title, **kwargs: SimpleNamespace(**kwargs))
        action_class = SimpleNamespace(actionWithTitle=lambda title, **kwargs: SimpleNamespace(title=title, **kwargs))
        image_class = SimpleNamespace(systemImageNamed=lambda name: name)
        classes = {'UIMenu': menu_class, 'UIAction': action_class, 'UIImage': image_class}
        module = SimpleNamespace(ObjCClass=classes.__getitem__,
                                 Block=lambda callback, *args: callback, objc_id=object)
        with patch.dict('sys.modules', {'rubicon.objc': module}):
            menu = DocumentNativeMenu(button, actions, invoke=lambda callback: callback(),
                                      context=lambda: None, fallback=Mock())
        sections = native.menu.children
        self.assertTrue(all(section.options == 1 for section in sections))
        self.assertEqual([action.title for section in sections for action in section.children],
                         [title for title, _ in actions])
        self.assertEqual([action.image for section in sections for action in section.children],
                         ['speaker.wave.2', 'textformat.size', 'folder', 'trash'])
        sections[-1].children[0].handler(None)
        self.assertEqual(calls, ['Delete document…'])
        self.assertEqual(sections[-1].children[0].attributes, 2)
        menu.dispose()
        self.assertIsNone(native.menu)

    def test_android_groups_preserve_item_ids_and_dispatch_after_separators(self):
        impl = type('AndroidButton', (), {'__module__': 'toga_android.widgets.button'})()
        impl.native = object()
        popup, native = Mock(), Mock()
        popup.getMenu.return_value = native
        selected = []
        actions = [(title, lambda title=title: selected.append(title))
                   for title in ('Show in folder', 'Show cached copy in folder', 'Close document')]
        modules = {
            'android.widget': SimpleNamespace(PopupMenu=Mock(return_value=popup)),
            'android.os': SimpleNamespace(Build=SimpleNamespace(VERSION=SimpleNamespace(SDK_INT=35))),
            'java': SimpleNamespace(dynamic_proxy=lambda interface: object),
        }
        modules['android.widget'].PopupMenu.OnMenuItemClickListener = object
        with patch.dict('sys.modules', modules), \
                patch('mobile.action_menu.android_menu_context', side_effect=lambda context: context), \
                patch('mobile.action_menu.menu_drawable', side_effect=lambda name, context: name):
            menu = DocumentNativeMenu(SimpleNamespace(_impl=impl), actions,
                invoke=lambda callback: callback(), context=lambda: object(), fallback=Mock())
            menu.show()
        self.assertEqual([call.args[:3] for call in native.add.call_args_list], [(0, 0, 0), (0, 1, 1), (1, 2, 2)])
        native.setGroupDividerEnabled.assert_called_once_with(True)
        popup.setForceShowIcon.assert_called_once_with(True)
        self.assertEqual([call.args[0] for call in native.add.return_value.setIcon.call_args_list],
                         ['folder_hub', 'folder_hub', 'close'])
        menu.listener.onMenuItemClick(SimpleNamespace(getItemId=lambda: 2))
        self.assertEqual(selected, ['Close document'])
        listener = menu.listener
        menu.dispose()
        menu.dispose()
        popup.dismiss.assert_called_once_with()
        popup.setOnMenuItemClickListener.assert_called_with(None)
        self.assertEqual(menu.actions, ())
        # A native callback already queued before detachment may still arrive.
        self.assertTrue(listener.onMenuItemClick(SimpleNamespace(getItemId=lambda: 2)))
        self.assertEqual(selected, ['Close document'])


class DocumentMenuTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        LogisticsMobile.storage_root = self.root
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(close_loop, self.app.loop)
        self.addCleanup(self.app.main_window.close)
        self.app.show_cloud(present=False)

    def run_async(self, coroutine):
        return self.app.loop.run_until_complete(coroutine)

    def labels(self, menu):
        return [title for title, _ in menu.actions]

    def test_open_document_can_be_favourited_and_listing_can_share(self):
        from commonUtils.runtime.platform import OS
        from mobile import favourites, outbound_share
        from services.documents.mobile_storage import document_copies

        app = self.app
        self.assertTrue(self.run_async(app.show_files(location=('Local files', ''))))
        provider = app.file_provider
        first, second = provider.root / 'open-owner.txt', provider.root / 'selected-file.txt'
        first.write_bytes(b'Open document')
        expected = 'Selected file ☃\r\n'.encode()
        second.write_bytes(expected)
        self.assertTrue(self.run_async(app.open_crypt(copies=document_copies(provider), key=second.name)))
        self.run_async(favourites.favourite(app, session=app.private_sessions.active.session))
        app.close_session(app.private_sessions.active.session.id, choice='discard')
        self.assertTrue(self.run_async(app.open_crypt(copies=document_copies(provider), key=first.name)))
        owner = app.private_sessions.active.session
        selected = next(session for session, _ in app.recent_items()
                        if session.title == second.name)
        hub = app.hub_controller()
        captured = []
        staging = self.root / 'share-test'

        async def receive(_app, path, validate, _anchor):
            validate()
            captured.append((path.name, path.read_bytes()))
            return True

        with patch.object(outbound_share, 'get_os', return_value=OS.IOS), \
                patch.object(outbound_share, '_root', return_value=staging), \
                patch.object(outbound_share, '_send_ios', side_effect=receive):
            button, = hub.document_row_menu(selected)
            commands = dict(button.document_actions.load_actions())
            self.assertNotIn('Add to Favourites', commands)
            self.assertNotIn('All documents', commands)
            hub.build_home()
            row_button = next(candidate for candidate in hub._home_recent_buttons
                              if candidate.text == second.name)
            title_controls = row_button.parent
            home_button = title_controls.parent.children[1]
            self.assertEqual(home_button.text, '⋯')
            self.assertEqual(home_button._impl._surface_roles, ('transparent', 'accent', False))
            self.assertNotIn('All documents', dict(home_button.document_actions.load_actions()))
            self.assertEqual([row['title'] for row in favourites.catalog(app).entries()], [second.name])
            self.assertTrue(self.run_async(commands[outbound_share.SEND]()))
            button.document_actions.dispose()

            self.assertTrue(self.run_async(app.show_files(location=('Local files', ''))))
            actions = dict(app.file_item_commands(row=provider.entry(second.name)))
            self.assertTrue(self.run_async(actions[outbound_share.SEND]()))
            self.assertNotIn('Remove from Favourites', actions)
            self.assertNotIn('Add to Favourites', actions)
            self.assertEqual(app.file_item_actions(provider, provider.entry('')), [])
            import toga
            container = toga.Box()
            favourites.populate(app, container, heading=False, allow_remove=True)
            children = container.children[0].children
            self.assertEqual(len(children), 2)
            menu = children[1].document_actions
            self.run_async(dict(menu.load_actions())['Remove from Favourites']())
            menu.dispose()
        self.assertEqual(captured, [(second.name, expected)] * 2)
        self.assertEqual(favourites.catalog(app).entries(), [])
        self.assertEqual(list(staging.iterdir()), [])
        self.assertIn(owner.id, app.workspace.sessions)
        self.assertEqual(first.read_bytes(), b'Open document')

    def test_protected_shares_confirm_validate_and_clean_staging(self):
        from commonUtils.runtime.platform import OS
        from commonUtils.runtime.resources.local import LocalFiles
        from mobile import outbound_share
        from services.documents.storage import FileItem

        class RemoteFixture(LocalFiles):
            remote_storage = private = True
            unlocked = True

            def check(self):
                if not self.unlocked:
                    raise PermissionError('Connection locked')

        provider = RemoteFixture(self.root)
        file = self.root / 'fixture.bin'
        payload = b'\xff\x00synthetic\r\n'
        file.write_bytes(payload)
        item = FileItem(provider, file.name, provider.entry(file.name)['revision'])
        directory = self.root / 'send-cache'
        app = self.app
        app._outbound_share_sheet = None

        async def cancel_sheet(_app, path, validate, _anchor):
            self.assertEqual(path.read_bytes(), payload)
            self.assertTrue(path.is_relative_to(directory))
            validate()
            return False

        with patch.object(outbound_share, 'get_os', return_value=OS.IOS), \
                patch.object(outbound_share, '_root', return_value=directory), \
                patch.object(outbound_share, '_send_ios', side_effect=cancel_sheet) as sheet, \
                patch.object(outbound_share, 'confirm_export', new=AsyncMock(return_value=False)) as confirm, \
                patch.object(app.main_window, 'dialog', new=AsyncMock()), \
                patch('toga.InfoDialog') as dialog:
            self.assertFalse(self.run_async(outbound_share.send(app, item)))
            self.assertFalse(directory.exists())
            sheet.assert_not_called()
            confirm.return_value = True
            self.assertFalse(self.run_async(outbound_share.send(app, item)))
            sheet.assert_awaited_once()
            self.assertEqual(list(directory.iterdir()), [])

            provider.unlocked = False
            self.assertFalse(self.run_async(outbound_share.send(app, item)))
            self.assertEqual(dialog.call_args.args[1], 'Connection locked')
            provider.unlocked = True
            file.write_bytes(b'Replacement bytes')
            self.assertFalse(self.run_async(outbound_share.send(app, item)))
            self.assertIn('selected file changed', dialog.call_args.args[1])
            sheet.assert_awaited_once()
            self.assertEqual(list(directory.iterdir()), [])

    def test_pair_command_tracks_rotation_and_picker_rejects_compact_layout(self):
        app = self.app
        app.create_chosen_document('md')
        menu = app.editor_view.actions
        for label in ('New document', 'Open from Files…', 'Import…', 'Close document'):
            self.assertNotIn(label, self.labels(menu))
        for width, visible in ((390, False), (1024, True), (390, False)):
            with patch.object(app.adaptive, 'width', return_value=width):
                app.adaptive.render()
                self.assertEqual('Open beside another document' in self.labels(menu), visible)
                if not visible:
                    panel = app.body
                    app.adaptive.show_pair_picker()
                    self.assertIs(app.body, panel)

    def test_formats_share_navigation_order_and_show_in_folder(self):
        app = self.app
        folder = self.root / 'LocalFiles' / 'Projects'
        folder.mkdir(parents=True, exist_ok=True)
        epub, comic = make_books(folder)
        text, markdown, pdf = folder / 'note.txt', folder / 'note.md', folder / 'file.pdf'
        text.write_text('Text')
        markdown.write_text('# Markdown')
        pdf.write_bytes(PDF)
        async def exercise():
            for path in (text, markdown, pdf, epub, comic):
                app.show_home()
                self.assertTrue(await app.open_download(path=path), path.name + ': ' + app.cloud_status.value)
                session = app.workspace.sessions[app.workspace.active]
                private = getattr(app, 'private_sessions', None)
                owner = private.controllers.get(session.id) if private else None
                if owner is not None:
                    menu = owner.crypt_actions_menu
                elif session.provider == 'library':
                    menu = app.readers.controllers[session.id].reader_actions
                else:
                    menu = app.editor_view.actions
                labels = self.labels(menu)
                self.assertIn('Show in folder', labels, path.name)
                self.assertNotIn('All documents', labels)
                self.assertNotIn('Close document', labels)
                self.assertTrue(await show_in_folder(app, session))
                self.assertEqual(app.folder_source, 'Local')
                self.assertEqual(app.file_path, 'Projects')
                self.assertTrue(app.close_session(session.id))
        with patch('features.pdf.document.PDFDocument.open', native_pdf):
            self.run_async(exercise())

    def test_imported_source_survives_store_reload_and_missing_source_reveals_cached_copy(self):
        app = self.app
        epub, comic = make_books(self.root)
        store = app.reader_manager().catalog.library_store
        async def exercise():
            for path in (epub, comic):
                record = store.import_book(LocalDocuments(), path)
                from mobile.library import LibraryStore
                # Simulate restart: no runtime source map, freshly loaded records.
                app._document_folder_sources = {}
                app.reader_manager().catalog.library_store = LibraryStore(store.root)
                self.assertTrue(await app.open_book(record['id']))
                owner = app.readers.active
                self.assertIn('Show in folder', self.labels(owner.reader_actions))
                self.assertTrue(await show_in_folder(app, owner.session))
                drawer = app.adaptive.browser('files')
                self.assertTrue(Path(drawer.provider.root).samefile(path.parent))
                await drawer.browser.close()
                path.unlink()
                owner.reader_actions.refresh()
                labels = self.labels(owner.reader_actions)
                self.assertIn('Show cached copy in folder', labels)
                self.assertNotIn('Show in folder', labels)
                self.assertEqual(labels.count('Show cached copy in folder'), 1)
                self.assertNotIn('All documents', labels)
                self.assertTrue(await show_in_folder(app, owner.session))
                drawer = app.adaptive.browser('files')
                self.assertEqual(Path(drawer.provider.root), store.root)
                await drawer.browser.close()
                self.assertTrue(app.close_session(owner.session.id))
        self.run_async(exercise())

    def test_legacy_import_with_unknown_source_reveals_cached_copy(self):
        import json
        app = self.app
        epub, _ = make_books(self.root)
        store = app.reader_manager().catalog.library_store
        record = store.import_book(LocalDocuments(), epub)
        record.pop('source_path')
        store.path(record['id'], '.json').write_text(json.dumps(record))
        async def exercise():
            self.assertTrue(await app.open_book(record['id']))
            owner = app.readers.active
            self.assertEqual(folder_action(app, owner.session)[0][0], 'Show cached copy in folder')
            self.assertTrue(await show_in_folder(app, owner.session))
            drawer = app.adaptive.browser('files')
            self.assertEqual(Path(drawer.provider.root), store.root)
            await drawer.browser.close()
        self.run_async(exercise())

    def test_reveal_remote_file_returns_to_its_cloud_or_server_tab(self):
        from features.rclone.mobile.remote_readers import RemoteReaders
        app = self.app
        app.cloud_client = client = RemoteClient()
        app.set_loaded_remote_names(['Files'])
        async def exercise():
            for server, expected in ((False, 'rclone'), (True, 'Network shares')):
                if server:
                    app.remember_credential_association('Network shares', ['Files'], session_only=False)
                app.show_home()
                self.assertTrue(await app.open_crypt(copies=RemoteReaders(client, 'Files'), key='note.txt'))
                owner = app.private_sessions.active
                app.folder_source = 'Local'
                self.assertTrue(await show_in_folder(app, owner.session))
                self.assertEqual(app.folder_source, expected)
                await app.parent_cloud()
                self.assertEqual(app.native_host.state.destination, 'files')
                self.assertEqual(app.folder_source, expected)
                self.assertTrue(app.close_session(owner.session.id))
        self.run_async(exercise())

    def test_fallback_menu_has_group_spacing_and_invokes_the_selected_command(self):
        app = self.app
        app.create_chosen_document('md')
        menu = app.editor_view.actions
        menu.show_fallback()
        box = app.body.children[0].content
        import toga
        self.assertGreater(sum(isinstance(child, toga.Divider) for child in box.children), 0)
        find = next(child for child in box.children if getattr(child, 'text', '') == 'Find and replace…')
        find.on_press()
        self.assertIn(app.editor_view.search.box, app.editor_view.document_view.children)
        self.run_async(asyncio.sleep(0))
