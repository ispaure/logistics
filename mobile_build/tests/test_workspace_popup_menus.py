"""Anchored workspace commands retain mapping identity and current busy guards."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

from mobile.action_menu import WorkspaceMenu
import test_folder_source_tabs as folder_tests


class WorkspaceCommandTests(TestCase):
    setUp = folder_tests.FolderSourceTabTests.setUp
    tearDown = folder_tests.FolderSourceTabTests.tearDown

    def test_opening_commands_keeps_workspace_route_and_dispatches_push(self):
        app = self.app
        (app.private_root / 'LocalFiles' / 'Notes').mkdir(parents=True)
        app.show_locations()
        before = list(app.routes.screens['files'])
        with patch.object(app, 'show_local_push') as push:
            actions = dict(app.workspace_menu_actions('Notes'))
            self.assertEqual(app.routes.screens['files'], before)
            self.assertIn('Browse Local', actions)
            self.assertIn('Delete local folder…', actions)
            app.loop.run_until_complete(actions['Push…']())
            push.assert_called_once_with('Notes')

    def test_stale_and_busy_commands_cannot_start_push(self):
        app = self.app
        (app.private_root / 'LocalFiles' / 'Notes').mkdir(parents=True)
        app.show_locations()
        with patch.object(app, 'show_local_push') as push:
            actions = dict(app.workspace_menu_actions('Notes'))
            app.cloud_busy = True
            app.loop.run_until_complete(actions['Push…']())
            push.assert_not_called()
            self.assertNotIn('Push…', dict(app.workspace_menu_actions('Notes')))
            app.cloud_busy = False
            app.folder_picker_choices.pop('Notes')
            app.loop.run_until_complete(actions['Push…']())
            push.assert_not_called()


class AppleWorkspaceMenuTests(TestCase):
    def test_uncached_native_menu_loads_current_commands_without_fallback_page(self):
        impl = type('AppleButton', (), {'__module__': 'toga_iOS.widgets.button'})()
        impl.native = NS()
        button = NS(_impl=impl)
        classes = {name: Mock() for name in ('UIMenu', 'UIAction', 'UIDeferredMenuElement')}
        callback, fallback, completion = Mock(), Mock(), Mock()
        loader = Mock(side_effect=[[('Push…', callback)], [('Pull…', callback)]])
        bridge = NS(ObjCClass=lambda name: classes[name], Block=lambda callback, *args: callback,
                    ObjCBlock=lambda callback, *args: callback, objc_id=object, ns_from_py=lambda value: value)
        with patch.dict('sys.modules', {'rubicon.objc': bridge}):
            menu = WorkspaceMenu(button, loader, invoke=lambda action: action(),
                                 context=Mock(), fallback=fallback)
            loader.assert_not_called()
            provider = classes['UIDeferredMenuElement'].elementWithUncachedProvider.call_args.args[0]
            provider(completion)
            provider(completion)
            self.assertEqual(loader.call_count, 2)
            self.assertTrue(impl.native.showsMenuAsPrimaryAction)
            labels = [call.args[0] for call in classes['UIAction'].actionWithTitle.call_args_list]
            self.assertEqual(labels, ['Push…', 'Pull…'])
            menu.blocks[-1](None)
            callback.assert_called_once()
            fallback.assert_not_called()
            menu.dispose()
            provider(completion)
            self.assertEqual(completion.call_args.args[0], [])
            self.assertEqual(loader.call_count, 2)


class ColdWorkspaceTransferTests(TestCase):
    def test_mapped_pull_and_push_initialize_connection_ui_before_credentials(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import AsyncMock
        from mobile.app import LogisticsMobile
        from test_mirror_jobs import MirrorClient
        for push in (False, True):
            with self.subTest(push=push), TemporaryDirectory() as directory:
                LogisticsMobile.storage_root = Path(directory)
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                try:
                    app.cloud_client = MirrorClient()
                    app.cloud_client.cancel = Mock()
                    job, _ = app.mirror_store().create(app.cloud_client, 'Remote', 'folder')
                    app.show_locations()
                    self.assertFalse(hasattr(app, 'cloud_view'))
                    actions = dict(app.workspace_menu_actions('folder'))
                    async def exercise():
                        with patch.object(app, 'require_remote_credentials_async',
                                          new=AsyncMock(return_value=False)) as credentials:
                            await actions['Push…' if push else 'Pull…']()
                            self.assertFalse(await app.transfer_task)
                            credentials.assert_awaited_once()
                            self.assertTrue(hasattr(app, 'cloud_view'))
                            self.assertFalse(app._review_starting)
                    app.loop.run_until_complete(exercise())
                finally:
                    app.main_window.close()
                    app.loop.close()
                    LogisticsMobile.storage_root = None
