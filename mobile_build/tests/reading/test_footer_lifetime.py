"""Pure owned scheduler/close contracts; no native toolkit or timer substitution."""
import ast
import gc
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import weakref

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

ROOT = Path(__file__).resolve().parents[3]


def definitions(path, name, method=None):
    tree = ast.parse((ROOT / path).read_text())
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == name)
    if method:
        node = next(item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == method)
    scope = dict(__package__='mobile')
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), scope)
    return scope[method or name]


Deferred = definitions('Python/mobile/reader_controls.py', 'DeferredFooterEdges')


class Handle:
    def __init__(self, callback):
        self.callback, self.cancelled = callback, False

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.callback()


class Loop:
    def __init__(self):
        self.handles = []

    def call_soon(self, callback):
        handle = Handle(callback)
        self.handles.append(handle)
        return handle


class Footer:
    def __init__(self):
        self._layout_app = NS(loop=Loop())
        self.visible = True
        self.refresh_edges = Mock()
        self.edge_timer_diagnostic = Mock()

    def edge_refresh_visible(self):
        return self.visible


class FooterLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.footer = Footer()
        self.deferred = Deferred(self.footer)
        self.loop = self.footer._layout_app.loop

    def test_hundred_reflows_create_one_callback_and_use_latest_width(self):
        for width in range(100):
            self.deferred.request(width)
        self.assertEqual(len(self.loop.handles), 1)
        self.loop.handles[0].fire()
        self.footer.refresh_edges.assert_called_once_with(99)
        self.assertIsNone(self.deferred.pending)

    def test_hidden_before_dispatch_does_not_refresh_and_can_reactivate(self):
        self.deferred.request(100)
        self.footer.visible = False
        self.loop.handles[0].fire()
        self.footer.refresh_edges.assert_not_called()
        self.deferred.request(200)
        self.assertEqual(len(self.loop.handles), 1)
        self.footer.visible = True
        self.deferred.request(200)
        self.loop.handles[-1].fire()
        self.footer.refresh_edges.assert_called_once_with(200)

    def test_hidden_reflow_cancels_the_existing_pending_refresh(self):
        self.deferred.request(100)
        self.footer.visible = False
        self.deferred.request(200)
        self.assertTrue(self.loop.handles[0].cancelled)
        self.assertIsNone(self.deferred.pending)
        self.loop.handles[0].fire()
        self.footer.refresh_edges.assert_not_called()

    def test_retire_cancels_once_and_rejects_new_requests(self):
        self.deferred.request(100)
        handle = self.loop.handles[0]
        self.deferred.close()
        self.deferred.close()
        self.assertTrue(handle.cancelled)
        handle.fire()
        self.deferred.request(300)
        self.assertEqual(len(self.loop.handles), 1)
        self.footer.refresh_edges.assert_not_called()

    def test_native_callback_does_not_keep_owner_alive_and_gc_cancels(self):
        self.deferred.request(100)
        reference = weakref.ref(self.footer)
        del self.footer
        gc.collect()
        self.assertIsNone(reference())
        self.assertTrue(self.loop.handles[0].cancelled)
        self.assertTrue(self.deferred.closed)

    def test_same_width_reentrant_reflow_does_not_requeue(self):
        self.footer.refresh_edges.side_effect = lambda width: self.deferred.request(width)
        self.deferred.request(100)
        self.loop.handles[0].fire()
        self.assertEqual(len(self.loop.handles), 1)
        self.assertEqual(self.deferred.requests, 2)

    def test_new_width_during_delivery_gets_one_followup(self):
        self.footer.refresh_edges.side_effect = lambda width: self.deferred.request(200)
        self.deferred.request(100)
        self.loop.handles[0].fire()
        self.assertEqual(len(self.loop.handles), 2)
        self.loop.handles[1].fire()
        self.assertEqual(len(self.loop.handles), 2)
        self.assertEqual(self.footer.refresh_edges.call_args_list[-1].args, (200,))

    def test_real_footer_disposal_unsubscribes_and_drops_app(self):
        dispose = definitions('Python/mobile/reader_controls.py', 'PageFooter', 'dispose')
        subscription = Mock()
        self.footer._edge_refresh = self.deferred
        self.footer._edge_subscription = subscription
        self.deferred.request(10)
        dispose(self.footer)
        dispose(self.footer)
        subscription.dispose.assert_called_once_with()
        self.assertIsNone(self.footer._layout_app)
        self.assertTrue(self.loop.handles[0].cancelled)

    def test_real_close_guard_preserves_then_permanently_retires_footer(self):
        close = definitions('Python/mobile/reader_sessions.py', 'Readers', 'close')
        events = []
        owner = NS(book_busy=False, page_footer=NS(dispose=lambda: events.append('retire')),
                   suspend=lambda: events.append('suspend'))
        app = NS(workspace=NS(close=Mock(return_value=False)), save_workspace=Mock(), reader_closed=Mock())
        manager = NS(controllers={'key': owner}, app=app, active=object())
        self.assertFalse(close(manager, 'key'))
        self.assertEqual(events, [])
        app.workspace.close.return_value = True
        self.assertTrue(close(manager, 'key'))
        self.assertEqual(events, ['retire', 'suspend'])
        self.assertNotIn('key', manager.controllers)

    def test_real_provider_accepted_disposal_retires_its_view_footer(self):
        import sys
        dispose = definitions('Python/mobile/provider_document.py', 'ProviderDocumentSession', 'dispose')
        footer = Mock()
        owner = NS(crypt_view=NS(page_footer=footer), app=object())
        document = NS(closed=False, owner=owner, reader=None, metadata_fields={})
        close_reader = Mock()
        helpers = {
            'mobile.provider_ui': NS(private_label=lambda text: text),
            'services.documents.mobile_reading': NS(close_document_reader=close_reader),
            'mobile.page_animation': NS(cancel_page_slide=Mock()),
            'mobile.ios_content_background': NS(clear=Mock()),
            'mobile.external_display': NS(sync=Mock()),
        }
        with patch.dict(sys.modules, helpers):
            dispose(document)
            dispose(document)
        footer.dispose.assert_called_once_with()
        close_reader.assert_called_once_with(None)
        self.assertTrue(document.closed)

    def test_immersive_controls_reactivate_after_their_actual_reattachment(self):
        immersive = definitions('Python/mobile/reader_controls.py', 'ReadingFrame', 'set_immersive')
        class Box:
            def __init__(self, children=()):
                self.children = list(children)
                self.style = NS()
            def add(self, child):
                self.children.append(child)
            def remove(self, child):
                self.children.remove(child)
            def insert(self, index, child):
                self.children.insert(index, child)
        footer = NS(request_edge_refresh=Mock())
        control = Box()
        control._reader_page_footer = footer
        content = Box()
        widget = Box([content, control])
        frame = NS(content=content, controls=[control], widget=widget,
                   margin=16, top_controls=0, restore=None)
        footer.request_edge_refresh.side_effect = lambda: self.assertIn(control, widget.children)
        immersive(frame, True, comic=True)
        footer.request_edge_refresh.assert_not_called()
        self.assertNotIn(control, widget.children)
        immersive(frame, False, comic=True)
        footer.request_edge_refresh.assert_called_once_with()

    def test_actual_native_visibility_rejects_detached_or_inactive_without_bridging(self):
        visible = definitions('Python/mobile/reader_controls.py', 'PageFooter', 'edge_refresh_visible')
        self.assertFalse(visible(NS(_layout_app=NS(active_host=False), widget=NS(parent=object()))))
        self.assertFalse(visible(NS(_layout_app=NS(active_host=True), widget=NS(parent=None))))

    def test_qa_diagnostics_are_bounded_metadata_and_observer_errors_are_contained(self):
        import json
        import tempfile
        diagnostic = definitions('Python/mobile/reader_controls.py', 'PageFooter', 'edge_timer_diagnostic')
        with tempfile.TemporaryDirectory() as directory:
            app = NS(_native_suite_timings=object(), paths=NS(cache=directory),
                     loop=NS(is_running=lambda: True, is_closed=lambda: False,
                             _timers={1, 2}, _cfrunloop=NS(value=123)))
            owner = NS(_layout_app=app)
            with patch('time.monotonic', side_effect=range(100, 1100)), patch('builtins.print'):
                for _ in range(100):
                    diagnostic(owner, 'before-schedule', self.deferred)
            result = json.loads((Path(directory) / 'logistics-native-ui-reader-edge-timers.json').read_text())
            self.assertTrue(result['diagnostic_only'])
            self.assertEqual(len(result['recent']), 24)
            self.assertEqual(result['recent'][-1]['footer_requests'], 0)
            self.assertEqual(result['recent'][-1]['native_timer_count'], 2)
            self.assertEqual(set(result['recent'][-1]), {
                'stage', 'at', 'loop_type', 'loop_running', 'loop_closed', 'main_thread',
                'cf_loop', 'native_timer_count', 'footer_requests', 'footer_deliveries',
                'pending', 'retired'})
            app.loop.is_running = Mock(side_effect=RuntimeError('observer only'))
            diagnostic(owner, 'before-schedule', self.deferred)

    def test_diagnostics_disabled_without_owning_qa_marker(self):
        diagnostic = definitions('Python/mobile/reader_controls.py', 'PageFooter', 'edge_timer_diagnostic')
        # No paths, timer internals or loop API exist; disabled mode must not inspect them.
        diagnostic(NS(_layout_app=NS()), 'before-schedule', self.deferred)


if __name__ == '__main__':
    unittest.main()


class FooterHostVisibilityTests(unittest.TestCase):
    def test_attached_non_native_backend_does_not_require_a_native_widget(self):
        visible = definitions('Python/mobile/reader_controls.py', 'PageFooter', 'edge_refresh_visible')
        owner = NS(_layout_app=NS(active_host=True), widget=NS(parent=object(), _impl=NS()))
        with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_dummy.widgets.box'):
            self.assertTrue(visible(owner))
