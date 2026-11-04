"""Canvas remounting retires the native Pencil observer with its WebView."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from unittest.mock import Mock, patch

import test_notebook_storage as fixture


class NotebookInputLifecycleTests(unittest.TestCase):
    setUp = fixture.NotebookStorageTests.setUp
    tearDown = fixture.NotebookStorageTests.tearDown
    run_async = fixture.NotebookStorageTests.run_async
    create = fixture.NotebookStorageTests.create

    def test_remount_and_dispose_close_each_owned_hover_observer_once(self):
        first, second = Mock(), Mock()
        with patch('features.notebooks.mobile.ios_input.attach', side_effect=[first, second]) as attach:
            panel = self.create(private=False)
            original = panel.web
            self.assertIs(panel.pencil_hover, first)
            panel.mount_canvas()
            first.close.assert_called_once_with()
            self.assertIsNot(panel.web, original)
            self.assertIs(panel.pencil_hover, second)
            self.assertEqual(attach.call_count, 2)
            panel.dispose()
            panel.retire_canvas()
            second.close.assert_called_once_with()
            self.assertIsNone(panel.pencil_hover)

    def test_private_ipad_native_subclass_keeps_hover_eligibility(self):
        import sys
        from types import SimpleNamespace
        from features.notebooks.mobile.ios_input import attach
        base = type('WebView', (), {'__module__': 'toga_iOS.widgets.webview'})
        secured = type('PrivateBackend', (base,),
                       {'__module__': 'commonUtils.ui.native.private_webview'})()
        web = SimpleNamespace(_impl=secured)
        recognizer, hover = object(), object()
        for idiom in (0, 1):
            device = SimpleNamespace(currentDevice=SimpleNamespace(userInterfaceIdiom=idiom))
            objc = SimpleNamespace(ObjCClass=lambda name: device if name == 'UIDevice' else recognizer)
            with self.subTest(idiom=idiom), patch.dict(sys.modules, {'rubicon.objc': objc}), patch(
                    'features.notebooks.mobile.ios_input.PencilHover', return_value=hover) as observer:
                self.assertIs(attach(web), hover if idiom else None)
                if idiom:
                    observer.assert_called_once_with(web, recognizer)
                else:
                    observer.assert_not_called()

    def test_private_android_subclass_attaches_and_retires_pen_owners(self):
        import sys
        import toga
        from types import SimpleNamespace
        native = Mock()
        native.getResources.return_value.getConfiguration.return_value.smallestScreenWidthDp = 700
        def canvas(resource=None, **kwargs):
            view = toga.WebView(**kwargs)
            base = type('AndroidBackend', (type(view._impl),),
                        {'__module__': 'toga_android.widgets.webview'})
            secured = type('PrivateBackend', (base,),
                           {'__module__': 'commonUtils.ui.native.private_webview'})
            view._impl.__class__ = secured
            view._impl.native = native
            return view
        refresh, pen = Mock(), Mock()
        java = SimpleNamespace(jclass=lambda name: SimpleNamespace(
            attach=Mock(return_value=refresh if name.endswith('BooxRefresh') else pen)))
        with patch('services.documents.mobile_views.document_webview', side_effect=canvas), patch.dict(
                sys.modules, {'java': java}):
            panel = self.create(private=True)
            self.assertIs(panel.boox_refresh, refresh)
            self.assertIs(panel.pen_input, pen)
            panel.retire_canvas()
            refresh.close.assert_called_once_with()
            pen.close.assert_called_once_with()
            self.assertIsNone(panel.web)


import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from features.notebooks.mobile import ios_input as module

class PencilInputTraceTests(unittest.IsolatedAsyncioTestCase):
    def make(self,folder):
        self.added=[];self.removed=[]
        self.gesture=SimpleNamespace()
        factory=SimpleNamespace(alloc=lambda:SimpleNamespace(initWithTarget=lambda *a,**kw:self.gesture))
        objc=ModuleType('rubicon.objc');objc.ns_from_py=lambda value:value
        self.query_results=[]
        async def evaluate(script):
            self.query_results.append(script)
            return json.dumps(dict(counts={'accepted-down:pen':3},recent=[]))
        native=SimpleNamespace(addGestureRecognizer=self.added.append,removeGestureRecognizer=self.removed.append)
        web=SimpleNamespace(_impl=SimpleNamespace(native=native),evaluate_javascript=evaluate)
        with patch.dict(sys.modules,{'rubicon.objc':objc}),patch.object(module,'_contact_class',return_value=factory):
            trace=module.PencilInputTrace(web,asyncio.get_running_loop(),Path(folder)/'trace.json')
        return trace

    async def test_pencil_scope_no_interception_and_close_exactly_once(self):
        with TemporaryDirectory() as folder,patch('builtins.print'):
            trace=self.make(folder)
            self.assertEqual(self.gesture.allowedTouchTypes,[2])
            self.assertFalse(self.gesture.cancelsTouchesInView)
            self.assertFalse(self.gesture.delaysTouchesBegan)
            self.assertFalse(self.gesture.delaysTouchesEnded)
            trace.close();trace.close()
            self.assertEqual(self.removed,[self.gesture]);self.assertIsNone(self.gesture.trace_owner)

    async def test_burst_is_bounded_trailing_flush_persists_pair_and_removes_timer(self):
        with TemporaryDirectory() as folder,patch('builtins.print'):
            trace=self.make(folder);trace.clock=lambda:100
            trace.record('begin',1)
            await trace.pending
            for _ in range(150):trace.record('begin',1);trace.record('end',1)
            self.assertEqual(len(trace.recent),24)
            self.assertIsNotNone(trace.timer)
            trace.clock=lambda:103;trace.flush()
            await trace.pending
            saved=json.loads((Path(folder)/'trace.json').read_text())
            self.assertEqual(saved['native']['counts']['begin'],151)
            self.assertEqual(saved['dom']['counts'],{'accepted-down:pen':3})
            self.assertLess((Path(folder)/'trace.json').stat().st_size,16384)
            trace.close();self.assertIsNone(trace.timer);self.assertIsNone(trace.pending)

    async def test_closing_during_pending_js_does_not_cancel_native_result(self):
        with TemporaryDirectory() as folder,patch('builtins.print'):
            trace=self.make(folder);result=asyncio.Future()
            trace.web.evaluate_javascript=lambda script:result
            trace.record('begin',1);task=trace.pending
            await asyncio.sleep(0)
            trace.close()
            await asyncio.gather(task,return_exceptions=True)
            self.assertFalse(result.cancelled());result.set_result('null')
            await asyncio.sleep(0)
            self.assertEqual(self.removed,[self.gesture])

    async def test_native_disk_and_dom_observer_errors_do_not_escape(self):
        with TemporaryDirectory() as folder,patch('builtins.print'):
            trace=self.make(folder)
            async def broken(script):raise RuntimeError('observer')
            trace.web.evaluate_javascript=broken
            trace.output=Path(folder)/'absent'/'bad.json'
            trace.record('begin',1);await trace.pending
            trace.close()
            self.assertEqual(trace.counts,{'begin':1})

    def test_native_begin_observed_before_super_and_no_prevention(self):
        events=[]
        objc=ModuleType('rubicon.objc')
        objc.ObjCClass=lambda name:type('NativeBase',(),{})
        objc.objc_method=lambda function:function
        objc.objc_property=lambda *a,**k:None
        objc.objc_id=object
        objc.send_super=lambda *a,**k:events.append('super')
        with patch.dict(sys.modules,{'rubicon.objc':objc}),patch.object(module,'_contact_trace_class',None):
            gesture=module._contact_class()()
            from weakref import ref
            class Owner:
                def record(self, *args):
                    events.append('observed')
            owner = Owner()
            gesture.trace_owner=ref(owner)
            gesture.touchesBegan_withEvent_(SimpleNamespace(count=1),None)
            self.assertEqual(events,['observed','super'])
            self.assertFalse(gesture.canPreventGestureRecognizer_(None))
            self.assertFalse(gesture.canBePreventedByGestureRecognizer_(None))
            gesture.touchesEnded_withEvent_(SimpleNamespace(count=1),None)
            self.assertEqual(gesture.state,5)
            gesture.trace_owner = None
            gesture.touchesCancelled_withEvent_(SimpleNamespace(count=1),None)
            self.assertEqual(events[-1], 'super')

    async def test_native_property_does_not_retain_its_python_owner(self):
        import gc
        from weakref import ref
        with TemporaryDirectory() as folder:
            trace = self.make(folder)
            owner = ref(trace)
            self.assertIs(self.gesture.trace_owner(), trace)
            del trace
            gc.collect()
            self.assertIsNone(owner())
            self.assertIsNone(self.gesture.trace_owner())

    def test_attach_failure_is_optional_and_unavailable_report_has_no_exception_content(self):
        with TemporaryDirectory() as folder,patch('builtins.print') as printed:
            output=Path(folder)/'trace.json'
            with patch('commonUtils.ui.native.text_size.native_backend',return_value='toga_iOS.widgets.webview'),patch.object(module,'PencilInputTrace',side_effect=RuntimeError('PRIVATE DOCUMENT AND PROVIDER')):
                self.assertIsNone(module.attach_diagnostics(object(),object(),output))
            result=json.loads(output.read_text())
            self.assertFalse(result['available'])
            self.assertEqual(result['reason'],'native-observer-unavailable')
            self.assertNotIn('PRIVATE',output.read_text())
            self.assertNotIn('PRIVATE',str(printed.call_args_list))

    def test_partially_attached_observer_is_removed_and_owned_work_cancelled(self):
        from unittest.mock import Mock
        timer,pending=Mock(),Mock()
        gesture=SimpleNamespace();removed=[];events=[]
        factory=SimpleNamespace(alloc=lambda:SimpleNamespace(initWithTarget=lambda *a,**kw:gesture))
        def add(value):
            events.append('attached')
            value.trace_owner().timer=timer;value.trace_owner().pending=pending
            raise RuntimeError('native add failed after attach')
        native=SimpleNamespace(addGestureRecognizer=add,removeGestureRecognizer=removed.append)
        web=SimpleNamespace(_impl=SimpleNamespace(native=native))
        objc=ModuleType('rubicon.objc');objc.ns_from_py=lambda value:value
        with patch.dict(sys.modules,{'rubicon.objc':objc}),patch.object(module,'_contact_class',return_value=factory):
            with self.assertRaises(RuntimeError):module.PencilInputTrace(web,object(),None)
        self.assertEqual(events,['attached']);self.assertEqual(removed,[gesture])
        self.assertIsNone(gesture.trace_owner)
        timer.cancel.assert_called_once_with();pending.cancel.assert_called_once_with()
        self.assertIs(web._impl.native,native)

    def test_unsupported_backend_does_not_construct_observer_or_write_receipt(self):
        with TemporaryDirectory() as folder:
            output=Path(folder)/'trace.json'
            with patch('commonUtils.ui.native.text_size.native_backend',return_value='toga_android.widgets.webview'),patch.object(module,'PencilInputTrace') as constructor:
                self.assertIsNone(module.attach_diagnostics(object(),object(),output))
            constructor.assert_not_called();self.assertFalse(output.exists())

    async def test_new_observer_has_distinct_nonidentifying_lifetime_nonce(self):
        with TemporaryDirectory() as folder,patch('builtins.print'):
            first=self.make(folder);second=self.make(folder)
            left,right=first.snapshot()['observer_id'],second.snapshot()['observer_id']
            self.assertNotEqual(left,right)
            self.assertEqual(len(left),32)
            self.assertTrue(all(character in '0123456789abcdef' for character in left))
            first.close();second.close()

    def test_dom_lifetime_nonce_accepts_only_exact_random_hex_shape(self):
        first=module._safe_dom_trace(dict(view_id='a'*32))
        second=module._safe_dom_trace(dict(view_id='b'*32))
        self.assertNotEqual(first['view_id'],second['view_id'])
        for token in ('private-document.md','a'*31,'A'*32,7,None,'../'+'a'*29):
            self.assertIsNone(module._safe_dom_trace(dict(view_id=token))['view_id'])

    def test_dom_privacy_projection_drops_unknown_and_content_fields(self):
        result=module._safe_dom_trace(dict(document='SECRET',counts={'title:private':7,'accepted-down:pen':3},
            recent=[dict(kind='accepted-down',type='pen',queued=999,coordinates=[1,2],title='SECRET',trusted=True)]))
        self.assertNotIn('SECRET',json.dumps(result));self.assertNotIn('coordinates',json.dumps(result))
        self.assertEqual(result['counts'],{'accepted-down:pen':3});self.assertEqual(result['recent'][0]['queued'],64)
