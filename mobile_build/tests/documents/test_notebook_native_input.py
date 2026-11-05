"""Native Pencil ownership and pinned constructor contracts; no digitizer claim."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from types import ModuleType, SimpleNamespace as NS
import sys
import unittest
from unittest.mock import Mock, patch
from mobile import ios_notebook_window as factory
from features.notebooks.mobile import ios_native_pen as feed


class NativeNotebookFactoryTests(unittest.TestCase):
    def frameworks(self, *, native_error=False, container_error=False):
        events = []
        class Native:
            @classmethod
            def alloc(cls):
                if native_error:
                    raise RuntimeError('optional native class unavailable')
                return cls()
            def initWithFrame(self, frame):
                events.append('native'); self.bounds = frame; return self
        class Backend:
            def __init__(self, interface, title, position, size):
                events.append('fallback'); self.interface = interface; interface._impl = self
            def create_container(self):
                if container_error:
                    raise RuntimeError('real product container failure')
                events.append('container'); self.container = NS(native=NS(), controller=object())
            def set_title(self, title): events.append('title')
        toga = ModuleType('toga'); toga.MainWindow = type('MainWindow', (), {})
        window = ModuleType('toga_iOS.window'); window.MainWindow = Backend
        libs = ModuleType('toga_iOS.libs'); libs.UIScreen = NS(mainScreen=NS(bounds=object()))
        libs.UIColor = NS(systemBackgroundColor=lambda: 'system', whiteColor='white')
        objc = ModuleType('rubicon.objc'); objc.ObjCClass = Mock(return_value=Native)
        return {'toga': toga, 'toga_iOS.window': window, 'toga_iOS.libs': libs, 'rubicon.objc': objc}, events

    def test_pinned_constructor_keeps_navigation_container_order_and_toolkit_globals(self):
        frameworks, events = self.frameworks()
        with patch.dict(sys.modules, frameworks), patch('importlib.metadata.version', return_value='0.5.7'), patch.object(factory, '_classes', None):
            backend, interface = factory.window_classes()
            owner = NS(); built = backend(owner, 'title', None, None)
            self.assertIs(owner._impl, built)
            self.assertEqual(events, ['native', 'container', 'title'])
            self.assertIs(built.container.native.frame, built.native.bounds)
            self.assertIs(built.native.rootViewController, built.container.controller)
            self.assertEqual(built.native.backgroundColor, 'system')
            self.assertIs(type(built), frameworks['toga_iOS.window'].MainWindow)
            self.assertIsNot(interface, frameworks['toga'].MainWindow)

    def test_native_constructor_failure_runs_normal_backend(self):
        frameworks, events = self.frameworks(native_error=True)
        with patch.dict(sys.modules, frameworks), patch('importlib.metadata.version', return_value='0.5.7'), patch.object(factory, '_classes', None):
            backend, _ = factory.window_classes(); owner = NS()
            built = backend(owner, 'title', None, None)
            self.assertEqual(events, ['fallback']); self.assertIs(owner._impl, built)

    def test_product_container_failure_is_not_disguised_as_optional_diagnostic_failure(self):
        frameworks, events = self.frameworks(container_error=True)
        with patch.dict(sys.modules, frameworks), patch('importlib.metadata.version', return_value='0.5.7'), patch.object(factory, '_classes', None):
            backend, _ = factory.window_classes(); owner = NS()
            with self.assertRaisesRegex(RuntimeError, 'real product container'):
                backend(owner, 'title', None, None)
            self.assertNotIn('fallback', events)
            self.assertTrue(owner._impl.native.hidden)
            self.assertIsNone(owner._impl.native.rootViewController)

    def test_scene_subclass_keeps_original_overrides_and_native_container(self):
        frameworks, events = self.frameworks()
        base = frameworks['toga_iOS.window'].MainWindow
        class SceneBackend(base):
            def get_size(self): return 'scene-size'
            def set_app(self, app): pass
        with patch.dict(sys.modules, frameworks), patch('importlib.metadata.version', return_value='0.5.7'):
            backend = SceneBackend.__new__(SceneBackend)
            factory.initialize_backend(backend, NS(), 'title', None, None)
        self.assertIs(type(backend), SceneBackend)
        self.assertEqual(backend.get_size(), 'scene-size')
        self.assertEqual(events, ['native', 'container', 'title'])

    def test_named_factory_preserves_original_toolkit_factory_entry(self):
        frameworks, _ = self.frameworks(); original = object()
        app = NS(backend_name='toga_iOS.app', factory=NS(MainWindow=original))
        with patch.dict(sys.modules, frameworks), patch('importlib.metadata.version', return_value='0.5.7'), patch.object(factory, '_classes', None):
            interface = factory.main_window_class(app)
            built = app.factory.LogisticsNotebookNativeInputMainWindow(NS(), 'title', None, None)
        self.assertIs(app.factory.MainWindow, original)
        self.assertEqual(interface._WINDOW_CLASS, 'LogisticsNotebookNativeInputMainWindow')
        self.assertIs(type(built), frameworks['toga_iOS.window'].MainWindow)

    def test_new_toga_version_leaves_native_backend_untouched(self):
        frameworks, _ = self.frameworks()
        with patch.dict(sys.modules, frameworks), patch('importlib.metadata.version', return_value='future'), patch.object(factory, '_classes', None):
            self.assertEqual(factory.window_classes(), (frameworks['toga_iOS.window'].MainWindow, frameworks['toga'].MainWindow))
            frameworks['rubicon.objc'].ObjCClass.assert_not_called()


class NativeNotebookBindingTests(unittest.TestCase):
    def fixture(self):
        native = NS(window=None)
        web = NS(_impl=NS(native=native))
        window = Mock()
        window.isKindOfClass.return_value = True
        window.bindNotebookWebView.return_value = True
        window.notebookWebViewEnabled.return_value = True
        objc = ModuleType('rubicon.objc'); objc.ObjCClass = Mock(return_value=object())
        return web, window, objc

    def test_owned_unattached_window_binds_nonce_before_html_and_retires_once(self):
        web, window, objc = self.fixture()
        with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.widgets.webview'), patch.object(feed, 'native_backend', return_value='toga_iOS.widgets.webview'), patch.dict(sys.modules, {'rubicon.objc': objc}):
            binding = feed.attach(web, window=window)
        self.assertEqual(len(binding.view_id), 32)
        window.bindNotebookWebView.assert_called_once_with(web._impl.native, forceMode=0, viewID=binding.view_id)
        self.assertTrue(binding.enabled)
        binding.close(); binding.close()
        window.unbindNotebookWebView.assert_called_once_with(web._impl.native)
        self.assertFalse(binding.enabled)

    def test_unavailable_native_class_preserves_dom_mode(self):
        web, window, objc = self.fixture(); window.isKindOfClass.return_value = False
        with patch.object(feed, 'native_backend', return_value='toga_iOS.widgets.webview'), patch.dict(sys.modules, {'rubicon.objc': objc}):
            self.assertIsNone(feed.attach(web, window=window))
        window.bindNotebookWebView.assert_not_called()

    def test_constant_mode_is_explicit_not_model_inferred(self):
        web, window, objc = self.fixture()
        with patch.object(feed, 'native_backend', return_value='toga_iOS.widgets.webview'), patch.dict(sys.modules, {'rubicon.objc': objc}):
            binding = feed.attach(web, window=window, constant_pressure=True)
        self.assertEqual(window.bindNotebookWebView.call_args.kwargs['forceMode'], 1)
        binding.close()
        with self.assertRaises(TypeError):
            feed.attach(web, constant_pressure='USB-C')

class NativeNotebookLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_flush_waits_for_native_before_querying_js_idle(self):
        from features.notebooks.mobile import panel as module
        from unittest.mock import AsyncMock
        panel = module.NotebookPanel.__new__(module.NotebookPanel)
        panel.web = NS(evaluate_javascript=AsyncMock(return_value=True))
        panel.bridge = NS(active=True); panel.closed = False; panel.busy = False
        panel.pen_input = NS(owns_native_transport=True, pending=True)
        async def release(delay): panel.pen_input.pending = False
        with patch.object(module, 'native_backend', return_value='toga_iOS.widgets.webview'), patch.object(module.asyncio, 'sleep', side_effect=release):
            await panel.flush_input()
        panel.web.evaluate_javascript.assert_awaited_once_with('window.notebookIdle?.() === true')

    async def test_flush_timeout_retains_pending_input_and_never_queries_idle(self):
        from features.notebooks.mobile import panel as module
        from unittest.mock import AsyncMock
        panel = module.NotebookPanel.__new__(module.NotebookPanel)
        panel.web = NS(evaluate_javascript=AsyncMock(return_value=True))
        panel.bridge = NS(active=True); panel.closed = False; panel.busy = False
        panel.pen_input = NS(owns_native_transport=True, pending=True)
        with patch.object(module, 'native_backend', return_value='toga_iOS.widgets.webview'), patch.object(module.asyncio, 'sleep', new=AsyncMock()):
            with self.assertRaisesRegex(TimeoutError, 'Finishing pen input'):
                await panel.flush_input()
        self.assertTrue(panel.pen_input.pending)
        panel.web.evaluate_javascript.assert_not_awaited()

    async def test_direct_save_retry_ack_is_nonerror_and_does_not_save_or_clear_native_queue(self):
        from features.notebooks.mobile import panel as module
        from unittest.mock import AsyncMock
        panel = module.NotebookPanel.__new__(module.NotebookPanel)
        async def wait(value): return await value
        panel.bridge = NS(active=True, wait=wait)
        panel.web = NS(evaluate_javascript=AsyncMock(return_value=True))
        panel.editor = NS(); panel.busy = False; panel.closed = False
        panel.pen_input = NS(owns_native_transport=True, pending=True)
        panel.document = NS(save=Mock())
        panel.state = lambda: {'native_pen': True}
        await panel.perform({'op': 'save'})
        panel.document.save.assert_not_called()
        self.assertTrue(panel.pen_input.pending)
        script = panel.web.evaluate_javascript.call_args.args[0]
        self.assertIn('Finishing pen input; try again.', script)
        self.assertIn('window.notebookUpdate(', script)
        self.assertTrue(script.partition(';')[0].endswith(',"")'))
        self.assertFalse(panel.busy)

    async def test_native_close_flushes_before_dirty_decision_and_discard_remains_explicit(self):
        import asyncio
        from mobile.workspace import Workspace
        from mobile.session_workflows.transitions import SessionTransitions
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from uuid import uuid4
        with TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory).resolve())
            session = workspace.open('notebook', uuid4().hex, 'notebook')
            notebook = NS(native_transport=True, document=NS(dirty=False), editor=NS(notebook=NS(name='Synthetic')), closed=False)
            async def flush(): notebook.document.dirty = True
            notebook.flush_input = flush
            host = NS(workspace=workspace, active_host=True, loop=asyncio.get_running_loop(), text_views={},
                      provider_sessions=lambda: NS(controllers={}), visible_reader=lambda: None,
                      _notebook_views={session.id: notebook}, close_session=Mock(), document_close_dialog=Mock())
            owner = SessionTransitions(host)
            self.assertTrue(owner.request_close_session(session.id))
            host.document_close_dialog.assert_not_called()
            await notebook._native_close_task
            host.document_close_dialog.assert_called_once()
            host.close_session.assert_not_called()
            discard = host.document_close_dialog.call_args.args[3]
            discard()
            host.close_session.assert_called_once_with(session.id, choice='discard')

    async def test_direct_discard_drops_pending_transport_but_normal_close_is_vetoed(self):
        from services.documents import mobile_notebooks as module
        panel = NS(busy=False, native_input_pending=True, document=NS(dirty=False, recovery_deleted=False), dispose=Mock())
        host = NS(_notebook_views={'key': panel}, workspace=NS(close=Mock()), save_workspace=Mock(), reader_closed=Mock(), refresh_document_list=Mock())
        self.assertFalse(module.close_notebook(host, 'key', 'keep'))
        panel.dispose.assert_not_called()
        self.assertTrue(module.close_notebook(host, 'key', 'discard'))
        panel.dispose.assert_called_once()
        self.assertFalse(host._notebook_views)

    async def test_unresolved_native_js_future_times_out_without_cancelling_late_completion(self):
        import asyncio
        from features.notebooks.mobile import panel as module
        query = asyncio.get_running_loop().create_future()
        panel = module.NotebookPanel.__new__(module.NotebookPanel)
        panel.web = NS(evaluate_javascript=lambda script: query)
        panel.bridge = NS(active=True); panel.closed = False; panel.busy = False
        panel.pen_input = NS(owns_native_transport=True, pending=False)
        with patch.object(module, 'native_backend', return_value='toga_iOS.widgets.webview'):
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(panel.flush_input(timeout=.01), timeout=.5)
        self.assertFalse(query.cancelled())
        self.assertFalse(query.done())
        query.set_result(True)
        await asyncio.sleep(0)
        self.assertTrue(query.result())

    async def test_flush_failure_still_offers_discard_for_clean_model_and_pending_native_ink(self):
        import asyncio
        from unittest.mock import AsyncMock
        from mobile.workspace import Workspace
        from mobile.session_workflows.transitions import SessionTransitions
        from services.documents import mobile_notebooks as documents
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from uuid import uuid4
        with TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory).resolve())
            session = workspace.open('notebook', uuid4().hex, 'notebook')
            notebook = NS(native_transport=True, native_input_pending=True, busy=False,
                document=NS(dirty=False, recovery_deleted=False), editor=NS(notebook=NS(name='Synthetic')),
                closed=False, dispose=Mock(), flush_input=AsyncMock(side_effect=TimeoutError('Finishing pen input')),
                save_from_view=AsyncMock(side_effect=TimeoutError('Finishing pen input')))
            host = NS(workspace=workspace, active_host=True, loop=asyncio.get_running_loop(), text_views={},
                provider_sessions=lambda: NS(controllers={}), visible_reader=lambda: None,
                _notebook_views={session.id: notebook}, document_close_dialog=Mock(), save_workspace=Mock(),
                reader_closed=Mock(), refresh_document_list=Mock())
            host.close_session = lambda key, choice='keep': documents.close_notebook(host, key, choice)
            owner = SessionTransitions(host)
            self.assertTrue(owner.request_close_session(session.id))
            await notebook._native_close_task
            host.document_close_dialog.assert_called_once()
            save, discard = host.document_close_dialog.call_args.args[2:]
            with patch.object(documents, 'show_notebook_close_error') as explain:
                await save()
                explain.assert_called_once()
            self.assertIn(session.id, workspace.sessions)
            self.assertEqual(notebook.flush_input.await_count, 1)
            notebook.save_from_view.assert_awaited_once()
            self.assertTrue(discard())
            self.assertNotIn(session.id, workspace.sessions)
            notebook.dispose.assert_called_once()
            self.assertEqual(notebook.flush_input.await_count, 1, 'Discard must not attempt the stalled flush again')
            notebook.save_from_view.assert_awaited_once()


class NativeNotebookCloseFactoryTests(unittest.TestCase):
    def test_actual_native_x_and_menu_close_reach_native_guard_without_querying_stalled_js(self):
        import asyncio
        import toga
        from unittest.mock import AsyncMock
        from mobile_build.tests.support.app import create_app
        from mobile.session_workflows.transitions import SessionTransitions
        from services.documents import mobile_notebooks as documents
        app = create_app(self)
        session = app.workspace.open('notebook', 'f' * 32, 'notebook')
        query = app.loop.create_future()
        web = NS(evaluate_javascript=Mock(return_value=query))
        panel = NS(app=app, view=toga.Box(), web=web, session=session, busy=False,
            native_transport=True, native_input_pending=True, closed=False,
            editor=NS(notebook=NS(name='Retained draft')),
            document=NS(dirty=False,recovery_deleted=False,resource=None),
            flush_input=AsyncMock(side_effect=TimeoutError('stalled JS')),
            dispose=Mock())
        app._notebook_views = {session.id:panel}
        self.addCleanup(app._notebook_views.clear)
        with patch.object(type(panel.view._impl),'__module__','toga_iOS.widgets.box'):
            documents.install_notebook_controls(panel)
        owner = SessionTransitions(app)
        with patch.object(app,'request_reader_close',side_effect=owner.request_close_session) as request, \
                patch.object(app,'document_close_dialog',return_value=True) as dialog, \
                patch.object(app,'save_workspace'), patch.object(app,'reader_closed'), \
                patch.object(app,'refresh_document_list'):
            app.loop.run_until_complete(asyncio.wait_for(panel.view._reader_close_button.on_press(),.5))
            if panel._native_close_task is not None:
                app.loop.run_until_complete(panel._native_close_task)
            close_menu = next(callback for title,callback in panel.native_actions.raw_actions if title=='Close document')
            app.loop.run_until_complete(asyncio.wait_for(close_menu(),.5))
            if panel._native_close_task is not None:
                app.loop.run_until_complete(panel._native_close_task)
            self.assertEqual(request.call_count,2)
            self.assertEqual(dialog.call_count,2)
            web.evaluate_javascript.assert_not_called()
            self.assertFalse(query.done())
            self.assertEqual(app._reader_returns[session.id],('home',None,False))
            self.assertTrue(dialog.call_args.args[3]())
            self.assertNotIn(session.id,app.workspace.sessions)
            panel.dispose.assert_called_once()


class NativeNotebookResponseSafetyTests(unittest.IsolatedAsyncioTestCase):
    def panel(self):
        from features.notebooks.mobile.panel import NotebookPanel
        from features.notebooks.bridge import Bridge
        panel=NotebookPanel.__new__(NotebookPanel)
        panel.bridge=Bridge();panel.closed=False;panel.busy=False;panel.pen_input=None
        panel.web=NS();panel.view=NS(children=[panel.web]);panel.status=NS(text='')
        panel.app=NS(active_host=True,adaptive=NS(render=Mock()))
        panel.editor=NS(index=0,notebook=NS(page=lambda index:NS(strokes=[])))
        panel.document=NS(resource=object(),recovery=object(),dirty=False,recovery_deleted=False)
        panel.library=Mock();panel.state=lambda:{'native_pen':False}
        return panel

    async def test_stalled_response_releases_busy_and_explicit_discard_closes_without_second_flush(self):
        import asyncio
        from services.documents import mobile_notebooks as documents
        panel=self.panel();query=asyncio.get_running_loop().create_future()
        panel.web.evaluate_javascript=Mock(return_value=query)
        panel.dispose=Mock();panel.busy=True
        task=asyncio.create_task(panel._respond(panel.web,'response-only',panel.bridge,timeout=.02))
        await asyncio.sleep(0)
        self.assertFalse(panel.busy)
        host=NS(_notebook_views={'key':panel},workspace=NS(close=Mock()),save_workspace=Mock(),reader_closed=Mock(),refresh_document_list=Mock())
        self.assertTrue(documents.close_notebook(host,'key','discard'))
        panel.dispose.assert_called_once()
        with self.assertRaises(TimeoutError):await task
        self.assertFalse(query.cancelled())
        query.set_result(True)
        await asyncio.sleep(0)
        panel.web.evaluate_javascript.assert_called_once_with('response-only')

    async def test_actual_page_preview_response_stall_discards_and_ignores_late_retired_result(self):
        import asyncio
        from functools import partial
        from services.documents import mobile_notebooks as documents
        panel=self.panel();query=asyncio.get_running_loop().create_future()
        entered=asyncio.Event()
        def evaluate(script):
            entered.set()
            return query
        web=panel.web
        web.evaluate_javascript=Mock(side_effect=evaluate)
        panel._respond=partial(panel._respond,timeout=.02)
        def dispose():
            panel.closed=True
            panel.bridge.retire()
            panel.web=None
        panel.dispose=Mock(side_effect=dispose)
        host=NS(_notebook_views={'key':panel},workspace=NS(close=Mock()),save_workspace=Mock(),reader_closed=Mock(),refresh_document_list=Mock())
        with patch('features.notebooks.previews.page_previews',return_value=[]):
            task=asyncio.create_task(panel.perform({'op':'page-previews','start':0}))
            await asyncio.wait_for(entered.wait(),.5)
            self.assertFalse(panel.busy)
            self.assertTrue(documents.close_notebook(host,'key','discard'))
            await asyncio.wait_for(task,.5)
        self.assertTrue(panel.closed)
        self.assertEqual(panel.status.text,'')
        panel.app.adaptive.render.assert_not_called()
        web.evaluate_javascript.assert_called_once()
        self.assertFalse(query.cancelled())
        query.set_result(True)
        await asyncio.sleep(0)

    async def test_page_preview_timeout_still_dispatches_exactly_one_nonerror_final_ack(self):
        import asyncio
        from functools import partial
        panel=self.panel();query=asyncio.get_running_loop().create_future()
        def evaluate(script):
            if script.startswith('window.notebookPagePreviews('):return query
            value=asyncio.get_running_loop().create_future();value.set_result(True);return value
        panel.web.evaluate_javascript=Mock(side_effect=evaluate)
        panel._respond=partial(panel._respond,timeout=.01)
        with patch('features.notebooks.previews.page_previews',return_value=[]):
            await asyncio.wait_for(panel.perform({'op':'page-previews','start':0}),.5)
        scripts=[call.args[0] for call in panel.web.evaluate_javascript.call_args_list]
        self.assertEqual(len(scripts),2)
        self.assertTrue(scripts[0].startswith('window.notebookPagePreviews('))
        self.assertTrue(scripts[1].startswith('window.notebookUpdate('))
        self.assertTrue(scripts[1].partition(';')[0].endswith(',"")'))
        self.assertFalse(panel.busy)
        panel.library.assert_not_called()
        self.assertFalse(query.cancelled())
        query.set_result(True)
        await asyncio.sleep(0)
        self.assertEqual(panel.web.evaluate_javascript.call_count,2)

    async def test_active_persistence_worker_keeps_busy_and_vetoes_discard_until_finished(self):
        import asyncio
        import threading
        from services.documents import mobile_notebooks as documents
        panel=self.panel();panel.view.children=[]
        entered,release=threading.Event(),threading.Event()
        def save():
            entered.set()
            if not release.wait(1):raise RuntimeError('owned worker was not released')
        panel.document.save=save;panel.dispose=Mock()
        host=NS(_notebook_views={'key':panel},workspace=NS(close=Mock()),save_workspace=Mock(),reader_closed=Mock(),refresh_document_list=Mock())
        task=asyncio.create_task(panel.perform({'op':'save'}))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait,.5))
            self.assertTrue(panel.busy)
            self.assertFalse(documents.close_notebook(host,'key','discard'))
            panel.dispose.assert_not_called()
        finally:
            release.set()
            await task
        self.assertFalse(panel.busy)
        self.assertTrue(documents.close_notebook(host,'key','discard'))

    async def test_provider_save_timeout_is_real_operation_error_and_keeps_dirty_draft(self):
        import asyncio
        panel=self.panel()
        panel.document.dirty=True
        panel.document.save=Mock(side_effect=TimeoutError('Provider save timed out'))
        panel._response_unavailable=Mock()
        def evaluate(script):
            result=asyncio.get_running_loop().create_future();result.set_result(True);return result
        panel.web.evaluate_javascript=Mock(side_effect=evaluate)
        await panel.perform({'op':'save'})
        panel.document.save.assert_called_once()
        self.assertTrue(panel.document.dirty)
        panel._response_unavailable.assert_not_called()
        panel.library.assert_not_called()
        scripts=[call.args[0] for call in panel.web.evaluate_javascript.call_args_list]
        self.assertEqual(len(scripts),1)
        self.assertIn('Provider save timed out',scripts[0])
        self.assertTrue(scripts[0].partition(';')[0].endswith(',"\")'))
        self.assertIn('textContent=',scripts[0])
        self.assertIn('Provider save timed out',panel.status.text)
        self.assertIs(panel.view._native_reader_status,panel.status)
        panel.app.adaptive.render.assert_called_once()
        self.assertFalse(panel.busy)

    async def test_save_as_failure_after_early_ack_does_not_ack_or_unblock_queued_worker(self):
        import asyncio
        import threading
        from services.documents import mobile_notebooks as documents
        panel=self.panel();panel.document.dirty=True
        entered,release=threading.Event(),threading.Event()
        workers=[]
        def apply(action):
            entered.set()
            if not release.wait(1):raise RuntimeError('owned stroke worker was not released')
        panel.editor.apply=Mock(side_effect=apply)
        def evaluate(script):
            result=asyncio.get_running_loop().create_future();result.set_result(True);return result
        panel.web.evaluate_javascript=Mock(side_effect=evaluate)
        async def picker(owner):
            workers.append(asyncio.create_task(panel.perform({'op':'stroke','points':[[1,2,.5]]})))
            if not await asyncio.to_thread(entered.wait,.5):raise AssertionError('queued worker did not start')
            raise OSError('Destination unavailable')
        panel.app.editor_picker=lambda:NS(show_notebook_destination=picker)
        panel.dispose=Mock()
        host=NS(_notebook_views={'key':panel},workspace=NS(close=Mock()),save_workspace=Mock(),reader_closed=Mock(),refresh_document_list=Mock())
        try:
            await panel.perform({'op':'save-as'})
            self.assertTrue(panel.busy)
            self.assertFalse(documents.close_notebook(host,'key','discard'))
            scripts=[call.args[0] for call in panel.web.evaluate_javascript.call_args_list]
            self.assertEqual(sum(script.startswith('window.notebookUpdate(') for script in scripts),1)
            self.assertEqual(len(scripts),2)
            self.assertTrue(scripts[1].startswith('document.getElementById("status").textContent='))
            self.assertIn('Destination unavailable',panel.status.text)
            self.assertTrue(panel.document.dirty)
            panel.library.assert_not_called()
        finally:
            panel.view.children=[]
            release.set()
            for worker in workers:await worker

    async def test_library_action_cannot_clear_busy_of_worker_dispatched_by_its_ack(self):
        import asyncio
        import threading
        panel=self.panel();panel.session=NS(id='key')
        entered,release=threading.Event(),threading.Event()
        workers=[]
        def apply(action):
            entered.set()
            if not release.wait(1):raise RuntimeError('owned stroke worker was not released')
        panel.editor.apply=Mock(side_effect=apply)
        async def evaluate(script):
            workers.append(asyncio.create_task(panel.perform({'op':'stroke','points':[[1,2,.5]]})))
            self.assertTrue(await asyncio.to_thread(entered.wait,.5))
            return True
        panel.web.evaluate_javascript=Mock(side_effect=evaluate)
        seen=[]
        panel.app.request_reader_close=lambda key:seen.append(panel.busy)
        try:
            await panel.perform({'op':'library'})
            self.assertEqual(seen,[True])
            self.assertTrue(panel.busy)
        finally:
            panel.view.children=[]
            release.set()
            for worker in workers:await worker

    async def test_provider_error_notice_survives_secondary_js_failure_without_dropping_canvas(self):
        panel=self.panel();panel.document.dirty=True
        panel.document.save=Mock(side_effect=OSError('Provider unavailable'))
        panel.web.evaluate_javascript=Mock(side_effect=RuntimeError('Display also unavailable'))
        panel._response_unavailable=Mock()
        await panel.perform({'op':'save'})
        self.assertTrue(panel.document.dirty)
        self.assertIn('Provider unavailable',panel.status.text)
        panel.library.assert_not_called()
        panel._response_unavailable.assert_not_called()
        self.assertTrue(panel.bridge.active)

    async def test_save_ack_queued_uri_is_admitted_before_native_close_decision(self):
        await self.save_ack_admission_case(unconfirmed=False)

    async def test_unconfirmed_post_save_idle_retains_session_and_reports_native_error(self):
        await self.save_ack_admission_case(unconfirmed=True)

    async def save_ack_admission_case(self, *, unconfirmed):
        await self.host_queue_save_case(queued_ink=not unconfirmed, unconfirmed_idle=unconfirmed)

    async def test_save_decision_finishes_after_persistence_even_if_response_ack_never_completes(self):
        await self.host_queue_save_case(stalled_ack=True)

    async def host_queue_save_case(self, *, queued_ink=False, unconfirmed_idle=False, stalled_ack=False):
        import asyncio
        from functools import partial
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from uuid import uuid4
        from mobile.workspace import Workspace
        from mobile.session_workflows.transitions import SessionTransitions
        from services.documents import mobile_notebooks as documents
        panel=self.panel();web=panel.web
        panel.pen_input=NS(owns_native_transport=True,pending=False)
        panel.document.dirty=True
        panel.document.save=Mock(side_effect=lambda:setattr(panel.document,'dirty',False))
        panel.document.discard=Mock(side_effect=lambda:setattr(panel.document,'dirty',False))
        panel._respond=partial(panel._respond,timeout=.01)
        panel.flush_input=partial(panel.flush_input,timeout=.12)
        panel.save_from_view=partial(panel.save_from_view,timeout=.12)
        panel.editor.notebook.name='Retained draft'
        def dispose():
            panel.closed=True
            panel.bridge.retire()
            panel.web=None
        panel.dispose=Mock(side_effect=dispose)
        js={'head':None,'admitted':False,'stroke_admitted':False,'ack':False}
        workers=[]
        late_ack=asyncio.get_running_loop().create_future()
        late_idle=asyncio.get_running_loop().create_future()
        def completed(value):
            future=asyncio.get_running_loop().create_future();future.set_result(value);return future
        def evaluate(script):
            if "window.notebookNativeAction('save')" in script:
                self.assertIsNone(js['head'])
                js['head']='save';js['admitted']=True
                workers.append(asyncio.create_task(panel.perform({'op':'save'})))
                return completed(True)
            if script.startswith('queue.slice'):return completed(False)
            if script.startswith('window.notebookUpdate('):
                self.assertEqual(js['head'],'save','A host Save must never ACK a stroke without its own JS queue head')
                js['head']='stroke' if queued_ink else None
                js['ack']=True
                return late_ack if stalled_ack else completed(True)
            if script.startswith('window.notebookIdle'):
                if js['ack'] and unconfirmed_idle:return late_idle
                if js['head']=='stroke':
                    # The C queue emptied before the next URI entered Python.
                    self.assertFalse(panel.native_input_pending)
                    self.assertFalse(panel.document.dirty)
                    panel.document.dirty=True
                    js['stroke_admitted']=True
                    js['head']=None
                return completed(js['head'] is None)
            raise AssertionError('Unexpected host-save JavaScript')
        web.evaluate_javascript=Mock(side_effect=evaluate)
        with TemporaryDirectory() as directory:
            workspace=Workspace(Path(directory).resolve())
            session=workspace.open('notebook',uuid4().hex,'notebook');panel.session=session
            host=NS(workspace=workspace,active_host=True,loop=asyncio.get_running_loop(),text_views={},
                provider_sessions=lambda:NS(controllers={}),visible_reader=lambda:None,
                _notebook_views={session.id:panel},document_close_dialog=Mock(),save_workspace=Mock(),
                reader_closed=Mock(),refresh_document_list=Mock(),adaptive=NS(render=Mock()))
            panel.app=host
            host.close_session=lambda key,choice='keep':documents.close_notebook(host,key,choice)
            owner=SessionTransitions(host)
            try:
                with patch('features.notebooks.mobile.panel.native_backend',return_value='toga_iOS.widgets.webview'), \
                        patch.object(documents,'show_notebook_close_error') as explain:
                    owner.request_close_session(session.id)
                    await panel._native_close_task
                    save=host.document_close_dialog.call_args.args[2]
                    await asyncio.wait_for(save(),.5)
                self.assertTrue(js['admitted'])
                panel.document.save.assert_called_once()
                if queued_ink or unconfirmed_idle:
                    self.assertIn(session.id,workspace.sessions)
                    panel.dispose.assert_not_called()
                    if queued_ink:
                        self.assertTrue(js['stroke_admitted'])
                        self.assertTrue(panel.document.dirty)
                        explain.assert_not_called()
                    else:
                        explain.assert_called_once()
                        self.assertIsInstance(explain.call_args.args[2],TimeoutError)
                    calls=web.evaluate_javascript.call_count
                    self.assertTrue(host.close_session(session.id,choice='discard'))
                    self.assertEqual(web.evaluate_javascript.call_count,calls,'Discard must never reflush')
                else:
                    self.assertNotIn(session.id,workspace.sessions)
                    explain.assert_not_called()
                panel.dispose.assert_called_once()
                panel.library.assert_not_called()
                self.assertFalse(late_ack.cancelled())
                self.assertFalse(late_idle.cancelled())
            finally:
                for future in (late_ack,late_idle):
                    if not future.done():future.set_result(True)
                for worker in workers:await worker
