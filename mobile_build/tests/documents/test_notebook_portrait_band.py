"""Portrait DOM acknowledgement never outlives its canvas or native band."""
import asyncio
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from commonUtils.testing.stages import TestStage
from features.notebooks.mobile.panel import NotebookPanel
TEST_STAGE = TestStage.REGRESSION

class PortraitAcknowledgementTests(unittest.IsolatedAsyncioTestCase):
    def panel(self):
        result=asyncio.get_running_loop().create_future()
        web=NS(evaluate_javascript=Mock(return_value=result))
        panel=NotebookPanel.__new__(NotebookPanel)
        panel.web=web;panel.bridge=object();panel.closed=False
        panel.view=NS(_notebook_dom_epoch=1,_reader_top_band_state={'notebook_candidate':(1,('geometry',))})
        panel._canvas_ready=True;panel._fold_signature=None
        panel.app=NS(loop=NS(create_task=asyncio.create_task,call_soon=Mock()),
            adaptive=NS(render=Mock()),presentation=NS(fold_division=lambda web:None))
        return panel,result

    async def test_native_integer_bool_acknowledges_current_canvas(self):
        panel,result=self.panel();panel.refresh_fold();await asyncio.sleep(0)
        result.set_result(1);await panel._fold_pending
        self.assertEqual(panel.view._notebook_dom_ready,(1,('geometry',)))
        panel.app.adaptive.render.assert_called_once()

    async def test_rotation_ack_cannot_reenable_old_geometry(self):
        panel,result=self.panel();panel.refresh_fold();await asyncio.sleep(0)
        panel.view._reader_top_band_state=None;panel.view._notebook_dom_epoch=2
        result.set_result(1);await panel._fold_pending
        self.assertIsNone(getattr(panel.view,'_notebook_dom_ready',None))
        panel.app.loop.call_soon.assert_called_once()

    async def test_replaced_bridge_or_closed_canvas_ignores_ack(self):
        for change in ('bridge','closed'):
            panel,result=self.panel();panel.refresh_fold();await asyncio.sleep(0)
            setattr(panel,change,object() if change=='bridge' else True)
            result.set_result(1);await panel._fold_pending
            self.assertIsNone(getattr(panel.view,'_notebook_dom_ready',None))
            panel.app.adaptive.render.assert_not_called()

    async def test_rail_change_during_inset_delivery_is_sent_after_ack(self):
        panel, result = self.panel()
        panel.view._reader_top_band_state = None
        panel.view._notebook_viewport_insets = (0, 0, 0)
        panel.refresh_fold()
        await asyncio.sleep(0)

        panel.view._notebook_viewport_insets = (0, 84, 34)
        panel.refresh_fold()
        result.set_result(True)
        await panel._fold_pending
        self.assertEqual(panel._viewport_insets_sent, (0, 0, 0))
        panel.app.loop.call_soon.assert_called_once_with(panel.refresh_fold)

        panel.refresh_fold()
        await panel._fold_pending
        self.assertEqual(panel._viewport_insets_sent, (0, 84, 34))
        panel.web.evaluate_javascript.assert_called_with('window.notebookViewportInsets?.([0, 84, 34])')

    async def test_missing_viewport_hook_does_not_acknowledge_insets(self):
        panel, result = self.panel()
        panel.view._reader_top_band_state = None
        panel.view._notebook_viewport_insets = (0, 84, 34)
        panel.refresh_fold()
        await asyncio.sleep(0)
        result.set_result(None)
        await panel._fold_pending
        self.assertIsNone(getattr(panel, '_viewport_insets_sent', None))

    async def test_timeout_never_cancels_native_query_or_creates_overlap(self):
        panel,result=self.panel()
        async def timeout(query,seconds):raise TimeoutError
        with patch('features.notebooks.mobile.panel._bounded_input_result',timeout):
            panel.refresh_fold();await panel._fold_pending
            self.assertFalse(result.cancelled())
            panel.refresh_fold();await panel._fold_pending
            self.assertEqual(panel.web.evaluate_javascript.call_count,1)
        result.set_result(1)
