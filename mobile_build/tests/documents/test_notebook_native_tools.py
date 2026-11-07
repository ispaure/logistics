"""Native drawing chrome mirrors DOM controls without owning notebook edits."""
import asyncio
import json
import unittest
from types import SimpleNamespace as NS
from dataclasses import replace
from unittest.mock import AsyncMock, patch
from features.notebooks.mobile.native_tools import NativeDrawingTools, TOOLS
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


class Panel:
    closed = busy = native_input_pending = False


class NativeToolsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.panel = Panel()
        self.panel.app = NS(presentation=NS(surface=unittest.mock.Mock()))
        self.panel.web = object()
        self.manager = NativeDrawingTools(self.panel)
        self.enterContext(patch.object(self.manager, 'visible', return_value=True))
        self.manager.web = self.panel.web
        self.manager.header = NS(parent=object(), remove=unittest.mock.Mock())
        self.manager.strip = NS(parent=self.manager.header, _impl=NS(native=NS(hidden=False)))
        self.manager.buttons = {name:NS(enabled=False, _impl=NS(native=NS(hidden=False))) for name in TOOLS}
        self.manager.anchor = lambda name: [100, -48, 44, 48]
        self.state = {name:dict(disabled=name == 'redo', active=name == 'pen') for name in TOOLS}

    async def test_full_drawing_toolbar_is_selected_before_native_geometry_is_available(self):
        self.panel._canvas_ready = True
        self.panel.app.presentation.native_notebook_toolbar = False
        self.assertFalse(self.manager.fits(controller=None))

    async def test_native_window_controller_and_hidden_ancestors_bound_visibility(self):
        window = NS(ptr=NS(value=10))
        parent = NS(isHidden=False, superview=None)
        native = NS(window=window, isHidden=False, superview=parent)
        self.manager.header._impl = NS(native=native)
        controller = NS(ptr=NS(value=20))
        self.manager.controller = controller
        self.panel.app = NS(active_host=True, main_window=NS(_impl=NS(native=window)),
            native_host=NS(state=NS(destination='files'), adapter=NS(content_controller=lambda destination:controller)))
        # Invoke the real native ownership predicate, not the dummy-backend shim.
        self.assertTrue(NativeDrawingTools.visible(self.manager, self.panel))
        native.window = None
        self.assertFalse(NativeDrawingTools.visible(self.manager, self.panel))
        native.window = window
        parent.isHidden = True
        self.assertFalse(NativeDrawingTools.visible(self.manager, self.panel))
        parent.isHidden = False
        self.manager.controller = NS(ptr=NS(value=21))
        self.assertFalse(NativeDrawingTools.visible(self.manager, self.panel))
        self.manager.controller = controller
        self.panel.app.active_host = False
        self.assertFalse(NativeDrawingTools.visible(self.manager, self.panel))

    async def test_initial_canvas_ready_requests_native_header_render_without_rotation(self):
        from features.notebooks.mobile.panel import NotebookPanel
        panel = NS(web=object(), native_drawing_tools=object(),
            app=NS(adaptive=NS(render=unittest.mock.Mock())), refresh_fold=unittest.mock.Mock())
        await NotebookPanel.canvas_loaded(panel, panel.web)
        self.assertTrue(panel._canvas_ready)
        panel.app.adaptive.render.assert_called_once_with()
        panel.refresh_fold.assert_called_once_with()
        panel.app.adaptive.render.reset_mock()
        await NotebookPanel.canvas_loaded(panel, object())
        panel.app.adaptive.render.assert_not_called()

    async def test_real_dom_state_controls_enabled_and_selection_without_changing_model(self):
        self.manager.query = AsyncMock(return_value=json.dumps(self.state))
        with patch.object(self.panel.app.presentation, 'surface') as surface:
            await self.manager.refresh()
        self.assertTrue(self.manager.buttons['undo'].enabled)
        self.assertFalse(self.manager.buttons['redo'].enabled)
        self.assertEqual(surface.call_args_list[0].kwargs['background'], 'hover')
        self.manager.query.assert_awaited_once_with('window.notebookNativeTools?.(null)')
        self.assertFalse(self.panel.busy)

    async def test_busy_and_pending_ink_renew_lease_without_dispatching_actions(self):
        self.manager.query = AsyncMock(return_value=json.dumps(self.state))
        for field in ('busy', 'native_input_pending'):
            with self.subTest(field=field):
                self.manager.query.reset_mock()
                setattr(self.panel, field, True)
                await self.manager.activate('undo')
                self.manager.query.assert_not_awaited()
                await self.manager.refresh()
                self.manager.query.assert_awaited_once_with('window.notebookNativeTools?.(null)')
                self.assertTrue(all(not button.enabled for button in self.manager.buttons.values()))
                self.assertTrue(getattr(self.panel, field))
                setattr(self.panel, field, False)

    async def test_hidden_lease_keeps_strip_mounted_but_hides_flattened_buttons(self):
        strip = self.manager.strip
        buttons = self.manager.buttons.copy()
        self.manager.query = AsyncMock(side_effect=[json.dumps(self.state), 'null', None, json.dumps(self.state)])
        await self.manager.refresh()
        self.assertTrue(buttons['undo'].enabled)
        for _ in range(2):
            await self.manager.refresh()
            self.assertIs(self.manager.strip, strip)
            self.assertIs(strip.parent, self.manager.header)
            self.assertTrue(strip._impl.native.hidden)
            self.assertTrue(all(button._impl.native.hidden and not button.enabled for button in buttons.values()))
        await self.manager.refresh()
        self.assertIs(self.manager.strip, strip)
        self.assertFalse(strip._impl.native.hidden)
        for name, button in buttons.items():
            self.assertIs(self.manager.buttons[name], button)
            self.assertFalse(button._impl.native.hidden)
            self.assertEqual(button.enabled, not self.state[name]['disabled'])

    async def test_new_strip_waits_for_native_attachment_before_querying(self):
        strip = self.manager.strip
        self.manager.visible.return_value = False
        self.manager.owns_controller = unittest.mock.Mock(return_value=True)
        close = self.manager.close = unittest.mock.Mock()
        queried = asyncio.Event()

        async def query(script):
            queried.set()
            return json.dumps(self.state)

        self.manager.query = AsyncMock(side_effect=query)
        task = asyncio.create_task(self.manager.observe())
        try:
            await asyncio.sleep(0)
            close.assert_not_called()
            self.manager.query.assert_not_awaited()
            self.assertIs(self.manager.strip, strip)
            self.assertTrue(all(not button.enabled for button in self.manager.buttons.values()))
            self.manager.visible.return_value = True
            await asyncio.wait_for(queried.wait(), 1)
            self.manager.query.assert_awaited_once_with('window.notebookNativeTools?.(null)')
            self.assertTrue(self.manager.buttons['undo'].enabled)
            self.assertFalse(self.manager.buttons['redo'].enabled)
            close.assert_not_called()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_route_change_retires_unattached_strip_without_renewing_lease(self):
        self.manager.visible.return_value = False
        self.manager.owns_controller = unittest.mock.Mock(return_value=True)
        close = self.manager.close = unittest.mock.Mock()
        self.manager.query = AsyncMock(return_value=json.dumps(self.state))
        task = asyncio.create_task(self.manager.observe())
        await asyncio.sleep(0)
        self.manager.owns_controller.return_value = False
        await asyncio.wait_for(task, .5)
        close.assert_called_once_with()
        self.manager.query.assert_not_awaited()

    async def test_retired_canvas_cannot_receive_actions(self):
        self.panel.web = object()
        self.manager.query = AsyncMock()
        await self.manager.activate('undo')
        self.manager.query.assert_not_awaited()

    async def test_taps_wait_for_observer_and_never_overlap_queries(self):
        self.manager.query = AsyncMock(return_value=json.dumps(self.state))
        await self.manager.lock.acquire()
        task = asyncio.create_task(self.manager.activate('undo'))
        await asyncio.sleep(0)
        self.manager.query.assert_not_awaited()
        self.manager.lock.release()
        with patch.object(self.panel.app.presentation, 'surface'):
            await task
        self.manager.query.assert_awaited_once_with('window.notebookNativeTools?.({"name": "undo", "anchor": [100, -48, 44, 48]})')

    async def test_malformed_state_restores_dom_and_retires_strip(self):
        self.manager.query = AsyncMock(return_value='{}')
        close = self.manager.close = unittest.mock.Mock()
        await self.manager.activate('undo')
        close.assert_called_once()

    async def test_cancellation_does_not_cancel_native_javascript_completion(self):
        from features.notebooks.mobile.panel import _bounded_input_result
        native = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(_bounded_input_result(native, 1))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(native.cancelled())
        native.set_result('late completion')
        await asyncio.sleep(0)


    async def test_unresolved_native_future_blocks_repeated_queries_and_restore(self):
        native = asyncio.get_running_loop().create_future()
        web = NS(evaluate_javascript=unittest.mock.Mock(return_value=native))
        self.manager.web = self.panel.web = web
        self.panel.app = NS(loop=asyncio.get_running_loop())
        waiter = asyncio.create_task(self.manager.query('first'))
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        self.assertFalse(native.cancelled())
        with self.assertRaises(TimeoutError):
            await self.manager.query('second')
        self.manager.close()
        await asyncio.sleep(0)
        web.evaluate_javascript.assert_called_once_with('first')
        native.set_result('late')
        await asyncio.sleep(0)
        self.assertEqual(self.manager.pending, {})

    async def test_stalled_native_future_does_not_retain_retired_controller(self):
        import gc
        import weakref
        native = asyncio.get_running_loop().create_future()
        panel = Panel()
        panel.app = NS(loop=asyncio.get_running_loop())
        panel.web = NS(evaluate_javascript=unittest.mock.Mock(return_value=native))
        manager = NativeDrawingTools(panel)
        manager.web = panel.web
        reference = weakref.ref(manager)
        waiter = asyncio.create_task(manager.query('first'))
        await asyncio.sleep(0)
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        manager.close()
        del waiter, manager
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        gc.collect()
        self.assertIsNone(reference())
        self.assertFalse(native.cancelled())
        native.set_result('late completion is safe')
        await asyncio.sleep(0)

    async def test_late_old_snapshot_never_updates_new_canvas_controls(self):
        result = asyncio.get_running_loop().create_future()
        self.manager.query = AsyncMock(side_effect=lambda script: result)
        async def query(script):
            return await result
        self.manager.query = query
        task = asyncio.create_task(self.manager.refresh())
        await asyncio.sleep(0)
        self.manager.epoch += 1
        self.manager.web = self.panel.web = object()
        self.manager.header = NS(parent=object(), remove=unittest.mock.Mock())
        self.manager.strip = NS(parent=self.manager.header)
        new_buttons = {name:NS(enabled=False) for name in TOOLS}
        self.manager.buttons = new_buttons
        result.set_result(json.dumps(self.state))
        with patch.object(self.panel.app.presentation, 'surface') as surface:
            await task
        surface.assert_not_called()
        self.assertTrue(all(not button.enabled for button in new_buttons.values()))


class NativeToolsMountTests(unittest.TestCase):
    def test_real_factory_fits_five44pt_buttons_beside_title_and_retires_task(self):
        import toga
        from toga.style import Pack
        from mobile_build.tests.support.app import create_app
        panel = Panel()
        panel.app = create_app(self)
        panel._canvas_ready = True
        panel.view = toga.Box()
        panel.web = NS(_impl=NS())
        panel.web.evaluate_javascript = AsyncMock(return_value=None)
        controller = NS(view=NS(bounds=NS(size=NS(width=951, height=669)),
            safeAreaLayoutGuide=NS(layoutFrame=NS(size=NS(width=867)))),
            traitCollection=NS(preferredContentSizeCategory="normal"))
        window = NS(bounds=NS(size=NS(width=951, height=669)))
        header = toga.Box(style=Pack(height=37))
        panel.view.add(header)
        manager = NativeDrawingTools(panel)
        with patch.object(panel.app.main_window._impl, 'native', window, create=True), \
                patch.object(panel.app, '_presentation', replace(panel.app.presentation, fold_division=lambda web:None)):
            self.assertTrue(manager.fits(controller))
            manager.mount(header, controller)
        self.assertEqual(len(manager.buttons), 5)
        self.assertEqual([button.style.width for button in manager.buttons.values()], [44] * 5)
        self.assertEqual(header._title_content.style.height, 48)
        from features.notebooks.mobile.native_tools import LANDSCAPE_INSET
        leading, title, gap, strip = header.children
        available = 867 - 2 * LANDSCAPE_INSET
        self.assertEqual(header.style.margin_left, LANDSCAPE_INSET)
        self.assertAlmostEqual(leading.style.width + title.style.width / 2, available / 3, delta=1)
        self.assertAlmostEqual(
            leading.style.width + title.style.width + gap.style.width + strip.style.width / 2,
            available * 2 / 3, delta=1)
        self.assertIs(manager.strip.parent, header)
        task = manager.task
        manager.close()
        panel.app.loop.run_until_complete(asyncio.sleep(0))
        self.assertTrue(task.cancelled())
        self.assertFalse(hasattr(header, '_title_content'))
        self.assertEqual(len(header.children), 0)
        panel.app.loop.run_until_complete(asyncio.sleep(0))

    def test_retiring_embedded_strip_preserves_note_history_and_actions(self):
        import toga
        from mobile_build.tests.support.app import create_app
        panel = Panel()
        panel.app = create_app(self)
        panel.web = NS(evaluate_javascript=AsyncMock())
        previous, following, actions = toga.Button('Previous'), toga.Button('Next'), toga.Button('Actions')
        row = toga.Box(children=[previous, following, actions])
        manager = NativeDrawingTools(panel)
        manager.mount(row, object(), before=actions)
        self.assertEqual(list(row.children), [previous, following, manager.strip, actions])
        manager.close()
        self.assertEqual(list(row.children), [previous, following, actions])
        panel.app.loop.run_until_complete(asyncio.sleep(0))

    def test_narrow_viewport_is_not_eligible_for_native_strip(self):
        import toga
        from mobile_build.tests.support.app import create_app
        for width, height, safe_width in ((320, 678, 320), (390, 300, 320)):
            panel = Panel()
            panel.app = create_app(self)
            panel._canvas_ready = True
            panel.view = toga.Box()
            panel.web = NS()
            manager=NativeDrawingTools(panel)
            controller=NS(view=NS(bounds=NS(size=NS(width=width,height=height)),
                safeAreaLayoutGuide=NS(layoutFrame=NS(size=NS(width=safe_width)))),
                traitCollection=NS(preferredContentSizeCategory="normal"))
            window=NS(bounds=NS(size=NS(width=width,height=height)))
            with patch.object(panel.app.main_window._impl,'native',window,create=True), \
                    patch.object(panel.app, '_presentation', replace(panel.app.presentation, fold_division=lambda web:None)):
                self.assertFalse(manager.fits(controller))
            self.assertIsNone(manager.task)
            self.assertIsNone(manager.strip)


class NotebookPresentationBoundaryTests(unittest.TestCase):
    def test_host_retirement_callback_and_standalone_default(self):
        from dataclasses import fields
        from services.mobile_presentation import MobilePresentation
        from mobile_build.tests.support.app import create_app
        from features.notebooks.mobile.panel import NotebookPanel
        app = create_app(self)
        panel = NotebookPanel(app, library=False)
        panel.view._notebook_dom_ready = 'old-canvas'
        panel.view._notebook_dom_epoch = 1
        panel.retire_canvas()
        self.assertIsNone(panel.view._notebook_dom_ready)
        self.assertEqual(panel.view._notebook_dom_epoch, 2)
        callback = unittest.mock.Mock()
        with patch.object(app, '_presentation', replace(app.presentation, reset_reader_layout=callback)):
            panel.retire_canvas()
        callback.assert_called_once_with(panel.view)
        standalone = MobilePresentation(**{field.name:getattr(app.presentation, field.name)
            for field in fields(MobilePresentation) if field.name != 'reset_reader_layout'})
        self.assertIsNone(standalone.reset_reader_layout(panel.view))
        self.assertEqual(panel.view._notebook_dom_epoch, 2)
        panel.dispose()
