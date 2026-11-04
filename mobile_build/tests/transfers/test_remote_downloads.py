"""Selected downloads preserve siblings, capture destination and never remove sources."""
from commonUtils.testing.stages import TestStage

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from commonUtils.runtime.resources.local import LocalFiles
from features.rclone.mobile.remote_downloads import RemoteDownload
from features.rclone.mobile.cloud_ui import CloudUI
from mobile_build.tests.support.app import create_app

TEST_STAGE = TestStage.REGRESSION


class RemoteDownloadTests(unittest.TestCase):
    def setUp(self):
        self.folder = self.enterContext(TemporaryDirectory())
        self.destination = LocalFiles(Path(self.folder))
        self.client = NS(generation=3)
        self.opened = NS(client=self.client, remote='Cloud', generation=3, identity='a'*64,
                         check=Mock(), close=Mock())
        self.source = NS(client=self.client, remote='Cloud', generation=3, private=True,
                         reopen=Mock(return_value=self.opened))

    def transfer(self, job, client, **kwargs):
        kwargs['check'](client, job, kwargs['cancelled'])
        root = kwargs['local_path']()
        (root/'note.txt').write_bytes(b'only selected contents')
        self.arguments = job, kwargs
        return 1

    def test_file_pull_publishes_only_selected_file_and_keeps_siblings(self):
        (Path(self.folder)/'keep.txt').write_text('keep')
        request = RemoteDownload(self.source, 'nested/note.txt', False)
        with patch('features.rclone.mobile.remote_downloads.sync_copy', side_effect=self.transfer):
            outcome = request.execute(self.client, self.destination, 'renamed.txt', lambda:False, Mock())
        self.assertEqual(outcome.operation, 'download')
        self.assertEqual((Path(self.folder)/'renamed.txt').read_bytes(), b'only selected contents')
        self.assertEqual((Path(self.folder)/'keep.txt').read_text(), 'keep')
        self.assertEqual(sorted(p.name for p in Path(self.folder).iterdir()), ['keep.txt','renamed.txt'])
        job,options = self.arguments
        self.assertEqual(job['prefix'], 'nested/note.txt')
        self.assertFalse(options['download']['directory'])
        self.assertFalse(options['push'])
        self.opened.close.assert_called_once()

    def test_folder_pull_keeps_selected_scope_and_unlocked_crypt_destination(self):
        destination = LocalFiles(Path(self.folder))
        destination.private = True
        destination.remote, destination.identity = 'OtherCrypt', 'b'*64
        destination._access = NS(check=Mock())
        request = RemoteDownload(self.source, 'nested/folder', True)
        with patch('features.rclone.mobile.remote_downloads.sync_copy', side_effect=self.transfer):
            request.execute(self.client, destination, 'folder', lambda:False, Mock())
        self.assertEqual((Path(self.folder)/'folder/note.txt').read_bytes(), b'only selected contents')
        values=self.arguments[1]['download']
        self.assertEqual(values,dict(download=True,directory=True,destination_remote='OtherCrypt',destination_identity='b'*64))
        self.assertEqual(self.arguments[0]['prefix'],'nested/folder')
        destination._access.check.assert_called()

    def test_existing_item_changed_credentials_and_cancellation_do_not_overwrite(self):
        request = RemoteDownload(self.source, 'note.txt', False)
        (Path(self.folder)/'note.txt').write_text('keep')
        with patch('features.rclone.mobile.remote_downloads.sync_copy') as transfer:
            with self.assertRaises(ValueError):
                request.execute(self.client,self.destination,'note.txt',lambda:False,Mock())
            transfer.assert_not_called()
            self.client.generation=4
            with self.assertRaises(ValueError):
                request.execute(self.client,self.destination,'other.txt',lambda:False,Mock())
            transfer.assert_not_called()
        self.assertEqual((Path(self.folder)/'note.txt').read_text(),'keep')
        self.client.generation=3
        with self.assertRaises(Exception):
            request.execute(self.client,self.destination,'cancelled.txt',lambda:True,Mock())
        self.assertEqual([p.name for p in Path(self.folder).iterdir()],['note.txt'])

    def test_failed_native_pull_cleans_only_its_owned_staging(self):
        (Path(self.folder)/'keep.txt').write_text('keep')
        def fail(job,client,**kwargs):
            (kwargs['local_path']()/'partial.txt').write_text('partial')
            raise OSError('offline')
        with patch('features.rclone.mobile.remote_downloads.sync_copy',side_effect=fail):
            with self.assertRaises(OSError):
                RemoteDownload(self.source,'folder',True).execute(self.client,self.destination,'new',lambda:False,Mock())
        self.assertEqual([p.name for p in Path(self.folder).iterdir()],['keep.txt'])
        self.opened.close.assert_called_once()


class RemoteDownloadPickerTests(unittest.TestCase):
    def test_native_back_diagnostics_bound_routes_and_exclude_names(self):
        import json
        from mobile_build.native_tests.tests.logisticsmobile.files_checks import download_navigation_state
        secret = 'PRIVATE-FOLDER-AND-DOCUMENT-SENTINEL'
        source, body = NS(), NS()
        screens = [('folder:' + secret, NS(), None) for _ in range(20)]
        screens.insert(0, ('remote-browser', source, None))
        routes = NS(screens={'files': screens}, roots={'files': NS()}, body=lambda *args: body)
        app = NS(routes=routes, native_host=NS(state=NS(destination='files'), adapter=None),
                 navigation_generation=42, visible_reader=lambda: None, active_host=True,
                 loading=False, current=NS(private=True, modified=False, name=secret), _impl=NS())
        tokens = {}
        state = download_navigation_state(app, source, tokens)
        self.assertTrue(state['source_retained'])
        self.assertEqual(state['route_count'], 21)
        self.assertEqual(len(state['routes']), 16)
        self.assertTrue(all(route['kind'] == 'folder' for route in state['routes']))
        self.assertNotIn(secret, json.dumps(state))
        self.assertEqual(download_navigation_state(app, source, tokens)['source'], state['source'])
        self.assertNotEqual(state['body'], state['source'])

    def test_completed_download_back_keeps_real_cloud_browser_route(self):
        from features.rclone.transfers.mobile.models import TransferOutcome
        from mobile_build.tests.support.readers import RemoteClient
        app = create_app(self)
        app.show_cloud(present=False)
        app.cloud_client = RemoteClient()
        import toga
        app.show_view(toga.Box(), destination='files', route='text-destination', title='Earlier picker')
        app.show_cloud()
        retained = app.routes.body('files')
        self.assertIn(app.cloud_view, retained.children)
        picker = app.editor_picker()
        request = RemoteDownload(NS(remote='Fixture'), 'note.txt', False)
        app.loop.run_until_complete(picker.show_destination('note.txt', request))
        with patch.object(RemoteDownload, 'execute', return_value=TransferOutcome('download')), \
                patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
            self.assertTrue(app.loop.run_until_complete(picker.complete_destination()))
        self.assertEqual(app.routes.screens['files'][-1][0], 'transfers')
        self.assertTrue(app.routes.back())
        self.assertIs(app.routes.body('files'), retained)
        self.assertIn(app.cloud_view, retained.children)
        self.assertNotIn('text-destination', [screen[0] for screen in app.routes.screens['files']])

    def test_cancel_new_download_preserves_source_above_an_older_picker(self):
        import toga
        app = create_app(self)
        app.show_cloud(present=False)
        app.show_view(toga.Box(), destination='files', route='text-destination', title='Earlier picker')
        app.show_cloud()
        retained = app.routes.body('files')
        picker = app.editor_picker()
        request = RemoteDownload(NS(remote='Fixture'), 'note.txt', False)
        app.loop.run_until_complete(picker.show_destination('note.txt', request))
        result = picker.cancel_text_destination()
        if hasattr(result, '__await__'):
            app.loop.run_until_complete(result)
        self.assertIs(app.routes.body('files'), retained)
        self.assertIn(app.cloud_view, retained.children)
        self.assertIsNone(picker.panel)
        self.assertNotIn('text-destination', [screen[0] for screen in app.routes.screens['files']])

    def test_native_picker_retirement_preserves_newer_folder_controllers(self):
        from mobile.routes import MobileRoutes
        owner = MobileRoutes.__new__(MobileRoutes)
        base, old, source = object(), object(), object()
        panes = [NS(controller=object()) for _ in range(3)]
        root, navigation = object(), Mock()
        adapter = NS(navigation=[navigation], containers=[(None, root)],
                     navigation_for=Mock(return_value=navigation), release_pane=Mock())
        owner.host = NS(adapter=adapter, destinations=['files'], state=NS(routes={}))
        owner.screens = {'files': [('browser', base, panes[0]),
                                  ('text-destination', old, panes[1]),
                                  ('remote-browser', source, panes[2])]}
        owner.changing = False
        owner.origins = {('files', 'text-destination'): 'documents'}
        owner.folders, owner.render = NS(forget=Mock()), Mock()
        owner._selection_returns = {}
        owner.retire_destination_picker('files')
        navigation.setViewControllers.assert_called_once_with(
            [root, panes[0].controller, panes[2].controller], animated=False)
        adapter.release_pane.assert_called_once_with(panes[1])
        self.assertIs(owner.screens['files'][-1][1], source)
        self.assertEqual(owner.host.state.routes['files'], ['browser', 'remote-browser'])
        self.assertFalse(owner.changing)

    def test_native_download_cancel_already_popped_does_not_pop_source_twice(self):
        import toga
        app = create_app(self)
        app.show_cloud(present=False)
        app.show_view(toga.Box(), destination='files', route='text-destination', title='Earlier picker')
        app.show_cloud()
        retained = app.routes.body('files')
        picker = app.editor_picker()
        request = RemoteDownload(NS(remote='Fixture'), 'note.txt', False)
        app.loop.run_until_complete(picker.show_destination('note.txt', request))
        app.routes.trim('files', len(app.routes.screens['files']) - 1)
        picker.cancel_text_destination(dismissed=True)
        self.assertIs(app.routes.body('files'), retained)
        self.assertIsNone(picker.panel)
        self.assertNotIn('text-destination', [screen[0] for screen in app.routes.screens['files']])

    def test_transfer_back_returns_to_retained_source_folder(self):
        import toga
        app = create_app(self)
        app.show_cloud(present=False)
        source = toga.Box()
        app.show_view(source, destination='files', route='remote-browser', title='Source folder')
        retained = app.routes.body('files')
        async def start(app, destination, target):
            app.show_view(toga.Box(), route='transfers', title='Transfer')
            return True
        request = NS(kind='download', title='Download locally', primary='Download here', complete=start)
        picker = app.editor_picker()
        app.loop.run_until_complete(picker.show_destination('note.txt', request))
        with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
            self.assertTrue(app.loop.run_until_complete(picker.complete_destination()))
        self.assertNotIn('text-destination', [s[0] for s in app.routes.screens['files']])
        self.assertTrue(app.routes.back())
        self.assertIs(app.routes.body('files'), retained)
        self.assertIn(source, retained.children)

    def test_destination_picker_offers_local_received_and_unlocked_crypt(self):
        app=create_app(self)
        app.show_cloud(present=False)
        source=NS(private=True)
        request=RemoteDownload(source,'note.txt',False)
        crypt_root=Path(app.private_root)/'fake-crypt'
        crypt_root.mkdir()
        crypt=LocalFiles(crypt_root)
        crypt.private=True
        def available_crypts(*, roots=None):
            if roots is not None:
                roots['LocalCrypt: empty unlocked']=('Empty', 'a'*64)
            return {'LocalCrypt: unlocked':crypt}
        with patch.object(app,'existing_crypt_locations',side_effect=available_crypts), \
             patch.object(app,'linked_crypt_locations',return_value={}):
            app.loop.run_until_complete(app.editor_picker().show_destination('note.txt',request))
        picker=app.editor_picker()
        self.assertIn('Local files',picker.editor_storage_roots)
        self.assertIn('Received Files',picker.editor_storage_roots)
        self.assertIn('Shared files',picker.editor_storage_roots)
        self.assertIn('LocalCrypt: unlocked',picker.editor_storage_roots)
        self.assertEqual(picker.editor_storage_roots['LocalCrypt: empty unlocked'],'Empty')
        self.assertEqual(picker.picker_primary.text,'Download here')
        self.assertIs(picker.operation.destination_action,request)
        shared = picker.editor_storage_roots['Shared files']
        self.assertFalse(shared.include_collections)
        self.assertNotIn('Local', [row['name'] for row in shared.list()])
        self.assertNotIn('Received Files', [row['name'] for row in shared.list()])
        from services.documents.locations import collection_path
        app.loop.run_until_complete(picker.browser_editor_location(('Shared files', collection_path(app.private_root).name)))
        self.assertEqual(picker.save_as_storage.value,'Local files')
        self.assertEqual(picker.picker_folder.value,'')
        picker.cancel_text_destination()

    def test_confirmation_hands_selected_destination_to_transfer_and_cancel_does_not(self):
        app=create_app(self)
        app.show_cloud(present=False)
        request=NS(kind='download',title='Download locally',primary='Download here',
                   complete=AsyncMock(return_value=True))
        picker=app.editor_picker()
        app.loop.run_until_complete(picker.show_destination('note.txt',request))
        with patch.object(app.main_window,'dialog',new=AsyncMock(return_value=False)):
            self.assertFalse(app.loop.run_until_complete(picker.complete_destination()))
        request.complete.assert_not_called()
        with patch.object(app.main_window,'dialog',new=AsyncMock(return_value=True)):
            self.assertTrue(app.loop.run_until_complete(picker.complete_destination()))
        self.assertEqual(request.complete.await_args.args[2],'note.txt')
        self.assertFalse(app.cloud_busy)
        self.assertIsNone(picker.operation.destination_action)

    def test_remote_menu_offers_download_for_both_files_and_folders(self):
        for directory in (False,True):
            row=dict(path='selected',directory=directory)
            owner=NS(rclone_ui=NS(private_label=lambda text:text),cloud_open_remote='Cloud',
                     cloud_client=NS(generation=1),remote_browser=Mock(),download_remote_item=Mock())
            CloudUI.show_remote_item_actions(owner,row)
            actions=dict(owner.remote_browser.show_item_menu.call_args.args[0])
            self.assertIn('Download locally…',actions)
            actions['Download locally…']()
            owner.download_remote_item.assert_called_once_with(row)
