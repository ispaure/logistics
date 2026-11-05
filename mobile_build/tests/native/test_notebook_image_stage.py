"""Failure-injected lifecycle checks; these do not claim native image acceptance."""
import asyncio
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from commonUtils.testing.stages import TestStage
from mobile_build.native_tests.tests.logisticsmobile import notebook_image_checks as checks

TEST_STAGE = TestStage.REGRESSION


class ImageStageCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def run_failure(self, *, cancelled=False, private=False, provider_close_fails=False, late_unrelated=False, partial_open=False, partial_clone=False):
        from features.notebooks.notebook import Notebook
        from commonUtils.runtime.resources.local import LocalFiles
        with TemporaryDirectory() as directory:
            root=Path(directory)
            original=NS(closed=False)
            registry={'original':original}
            sessions={'original':NS(id='original')}
            workspace=NS(sessions=sessions,active='original')
            workspace.activate=lambda key:setattr(workspace,'active',key)
            def close(key,guard):
                assert guard(sessions[key])
                del sessions[key]
                workspace.active='original'
            workspace.close=close
            client=NS(generation=7,request=Mock(side_effect=AssertionError('Credentials must not be replaced')))
            recent=NS(path=root/'recent.json',items=[dict(provider='notebook',resource='original',kind='notebook')])
            app=NS(private_root=root,paths=NS(cache=root),workspace=workspace,notebook_panel=original,
                   native_host=NS(state=NS(destination='files')),cloud_client=client,recent_documents=recent,
                   routes=NS(render=Mock()),save_workspace=Mock(),show_home=Mock(),set_feature_enabled=Mock())
            providers=[];repositories=[];created=[]
            unrelated=NS(closed=False,busy=False,session=NS(id='late-unrelated'),
                document=NS(resource=NS(provider=NS(root=root/'unrelated-provider')),recovery=None))
            unrelated.dispose=Mock(side_effect=lambda:setattr(unrelated,'closed',True))
            class Provider(LocalFiles):
                def __init__(self,path,*args):
                    super().__init__(path)
                    self.private=bool(args)
                    self.closed=False
                    if args:self.test_client=args[0]
                    providers.append(self)
                def close(self):
                    self.closed=True
                    if provider_close_fails:raise OSError('injected provider close failure')
            class Resource:
                def __init__(self,provider,path,**kwargs):self.provider,self.path=provider,path
                def read(self):return (self.provider.root/self.path).read_bytes()
            class Panel:
                def __init__(self,resource):
                    self.closed=False;self.busy=False
                    self.session=NS(id='image-'+str(len(created)))
                    self.editor=NS(notebook=Notebook.read(resource.read()))
                    recovery=None
                    if not resource.provider.private:
                        recovery=NS(keys={self.session.id},open=lambda key:self.editor.notebook)
                        recovery.delete=lambda key:recovery.keys.remove(key)
                        repositories.append(recovery)
                    self.document=NS(resource=resource,recovery=recovery,key=self.session.id)
                    impl=type('Backend',(),{'__module__':'toga_android.webview'})()
                    png='data:image/png;base64,iVBORw0KGgo='
                    self.web=NS(_impl=impl,evaluate_javascript=AsyncMock(return_value=png))
                    created.append(self)
                def retire_canvas(self):self.busy=False
                def dispose(self):self.closed=True;self.document=None
            async def open_notebook(app,*,resource):
                panel=Panel(resource);registry[panel.session.id]=panel
                sessions[panel.session.id]=panel.session
                app.notebook_panel=panel;workspace.active=panel.session.id
                recent.items=[]  # Opening bounded history may evict an old row.
                if partial_open:
                    if partial_clone:
                        panel.document.resource=NS(provider=NS(root=resource.provider.root))
                    raise failure
                return True
            def close_notebook(app,key,choice):
                panel=registry.pop(key);panel.dispose();workspace.close(key,guard=lambda value:True)
                return True
            failure=asyncio.CancelledError('injected timeout cancellation') if cancelled else AssertionError('injected pixel failure')
            class Workflow:
                def __init__(self,evaluate,editor,capture,progress=None,diagnostic=None):
                    self.cases=[]
                    assert diagnostic is None or callable(diagnostic)
                async def run(self):
                    if not private or app.notebook_panel.document.resource.provider.private:
                        app.notebook_panel.busy=True
                        if late_unrelated:
                            # A different owner publishes a panel after this run's
                            # baseline snapshot, immediately before our failure.
                            registry[unrelated.session.id]=unrelated
                            sessions[unrelated.session.id]=unrelated.session
                            app.notebook_panel=unrelated
                        raise failure
                async def send(self,action):pass
                async def idle(self):pass
                async def unlock(self):pass
            with ExitStack() as context:
                context.enter_context(patch('commonUtils.runtime.resources.local.LocalFiles',Provider))
                context.enter_context(patch('features.rclone.localcrypt.mobile.resources.CryptFiles',Provider))
                context.enter_context(patch('services.documents.storage.DocumentResource',Resource))
                context.enter_context(patch('services.documents.mobile_notebooks.open_notebook',open_notebook))
                context.enter_context(patch('services.documents.mobile_notebooks.close_notebook',close_notebook))
                context.enter_context(patch('services.documents.mobile_notebooks.panels',lambda app:registry))
                context.enter_context(patch.object(checks,'ImageWorkflow',Workflow))
                # Cleanup injection is independent of real native-view qualification.
                context.enter_context(patch.object(checks,'verify_native_image_view',return_value='toga_android.webview'))
                context.enter_context(patch('mobile_build.native_tests.tests.logisticsmobile.fixtures.capture_window',AsyncMock()))
                with self.assertRaises(type(failure)) as raised:
                    await checks.exercise_notebook_images(app)
            self.assertIs(raised.exception,failure)
            expected={'original','late-unrelated'} if late_unrelated else {'original'}
            self.assertEqual(set(sessions),expected)
            self.assertEqual(set(registry),expected)
            if late_unrelated:
                self.assertIs(registry['late-unrelated'],unrelated)
                self.assertIs(sessions['late-unrelated'],unrelated.session)
                self.assertFalse(unrelated.closed)
                unrelated.dispose.assert_not_called()
            self.assertIs(app.notebook_panel,original)
            self.assertFalse(original.closed)
            self.assertEqual(workspace.active,'original')
            self.assertEqual(recent.items,[dict(provider='notebook',resource='original',kind='notebook')])
            app.routes.render.assert_called_once_with('files')
            client.request.assert_not_called()
            self.assertTrue(all(panel.closed for panel in created))
            self.assertTrue(all(provider.closed for provider in providers))
            self.assertTrue(all(not repo.keys for repo in repositories))
            self.assertFalse(list(root.glob('notebook-images-*')))
            report=app._notebook_image_report
            self.assertFalse(report['success'])
            self.assertNotIn('artifacts',report)
            self.assertTrue(all(isinstance(name,str) for name in report.get('artifact_names',[])))
            self.assertTrue(report['cleanup']['original_restored'])
            self.assertTrue(report['cleanup']['files_removed'])
            if private:self.assertIs(providers[-1].test_client,client)
            if provider_close_fails:
                self.assertTrue(report['cleanup']['errors'])
                self.assertIn('injected provider close failure',' '.join(failure.__notes__))
            else:self.assertEqual(report['cleanup']['errors'],[])

    async def test_local_failure_restores_original_and_cleans_all_owned_state(self):
        await self.run_failure()

    async def test_private_failure_reuses_client_and_cleans_both_provider_runs(self):
        await self.run_failure(private=True)

    async def test_timeout_cancellation_propagates_after_cleanup(self):
        await self.run_failure(cancelled=True)

    async def test_cleanup_error_is_evidence_and_does_not_replace_primary_failure(self):
        await self.run_failure(provider_close_fails=True)

    async def test_wrong_staged_fixture_fails_before_touching_app_or_credentials(self):
        original=object()
        client=NS(request=Mock())
        app=NS(notebook_panel=original,cloud_client=client)
        with patch.object(checks,'IMAGE_FIXTURE_SHA256','wrong-hash'):
            with self.assertRaisesRegex(AssertionError,'Staged notebook image fixture differs'):
                await checks.exercise_notebook_images(app)
        self.assertIs(app.notebook_panel,original)
        client.request.assert_not_called()
        self.assertFalse(app._notebook_image_report['success'])
        self.assertTrue(app._notebook_image_report['cleanup']['not_started'])
        self.assertIn('Staged notebook image fixture differs',app._notebook_image_report['error'])

    async def test_late_unrelated_panel_and_session_are_preserved_on_failure(self):
        await self.run_failure(late_unrelated=True)

    async def test_partially_published_owned_provider_is_retired_after_open_failure(self):
        await self.run_failure(partial_open=True)

    async def test_partial_publication_with_cloned_provider_requires_owned_root(self):
        await self.run_failure(partial_open=True,partial_clone=True)
