"""Shared document commands follow available space and retain storage context."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from commonUtils.runtime.resources.documents import LocalDocuments
from mobile.app import LogisticsMobile
from mobile.document_sources import folder_action, show_in_folder
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from mobile_build.tests.support.pdf import PDF, native_pdf
from mobile_build.tests.support.readers import RemoteClient
from mobile.action_menu import DocumentNativeMenu


class NativeDocumentMenuTests(TestCase):
    def test_apple_sections_keep_command_handlers_and_use_inline_group_separators(self):
        calls = []
        actions = [(title, lambda title=title: calls.append(title))
                   for title in ('Read aloud…', 'Appearance…', 'All documents', 'Delete document…')]
        native = SimpleNamespace()
        impl = type('AppleButton', (), {'__module__': 'toga_iOS.widgets.button'})()
        impl.native = native
        button = SimpleNamespace(_impl=impl)
        menu_class = SimpleNamespace(menuWithTitle=lambda title, **kwargs: SimpleNamespace(**kwargs))
        action_class = SimpleNamespace(actionWithTitle=lambda title, **kwargs: SimpleNamespace(title=title, **kwargs))
        module = SimpleNamespace(ObjCClass=lambda name: menu_class if name == 'UIMenu' else action_class,
                                 Block=lambda callback, *args: callback, objc_id=object)
        with patch.dict('sys.modules', {'rubicon.objc': module}):
            menu = DocumentNativeMenu(button, actions, invoke=lambda callback: callback(),
                                      context=lambda: None, fallback=Mock())
        sections = native.menu.children
        self.assertTrue(all(section.options == 1 for section in sections))
        self.assertEqual([action.title for section in sections for action in section.children],
                         [title for title, _ in actions])
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
                   for title in ('Show in folder', 'All documents', 'Close document')]
        modules = {
            'android.widget': SimpleNamespace(PopupMenu=Mock(return_value=popup)),
            'android.os': SimpleNamespace(Build=SimpleNamespace(VERSION=SimpleNamespace(SDK_INT=35))),
            'java': SimpleNamespace(dynamic_proxy=lambda interface: object),
        }
        modules['android.widget'].PopupMenu.OnMenuItemClickListener = object
        with patch.dict('sys.modules', modules), \
                patch('mobile.action_menu.android_menu_context', side_effect=lambda context: context):
            menu = DocumentNativeMenu(SimpleNamespace(_impl=impl), actions,
                invoke=lambda callback: callback(), context=lambda: object(), fallback=Mock())
            menu.show()
        self.assertEqual([call.args[:3] for call in native.add.call_args_list], [(0, 0, 0), (0, 1, 1), (1, 2, 2)])
        native.setGroupDividerEnabled.assert_called_once_with(True)
        menu.listener.onMenuItemClick(SimpleNamespace(getItemId=lambda: 2))
        self.assertEqual(selected, ['Close document'])
        menu.dispose()
        popup.dismiss.assert_called_once_with()


class DocumentMenuTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        LogisticsMobile.storage_root = self.root
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.show_cloud(present=False)

    def run_async(self, coroutine):
        return self.app.loop.run_until_complete(coroutine)

    def labels(self, menu):
        return [title for title, _ in menu.actions]

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
                self.assertLess(labels.index('Show in folder'), labels.index('All documents'))
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
                self.assertEqual(Path(drawer.provider.root), path.parent)
                await drawer.browser.close()
                path.unlink()
                owner.reader_actions.refresh()
                labels = self.labels(owner.reader_actions)
                self.assertIn('Show cached copy in folder', labels)
                self.assertNotIn('Show in folder', labels)
                self.assertEqual(labels.count('Show cached copy in folder'), 1)
                self.assertLess(labels.index('Show cached copy in folder'), labels.index('All documents'))
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
