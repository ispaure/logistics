"""Native size and inset changes wake responsive layouts without navigation."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from mobile.ios_reader_chrome import notify_viewport


class ViewportTests(unittest.TestCase):
    def test_regions_materialize_native_array_without_reflecting_swift_collection(self):
        from mobile.ios_reader_chrome import occlusion_geometry
        raw = object()  # Deliberately not Python-iterable.
        region = SimpleNamespace(frame=SimpleNamespace(origin=SimpleNamespace(x=-4, y=0),
            size=SimpleNamespace(width=88, height=212)))
        native = Mock()
        native.reservedRegionsOfKind.return_value = raw
        array = Mock()
        array.arrayWithArray.return_value = [region]
        kind = SimpleNamespace(occlusionRegionKind=lambda: 'occlusion')
        bridge = SimpleNamespace(SEL=lambda value: value,
            ObjCClass=lambda name: array if name == 'NSMutableArray' else kind)
        with patch.dict('sys.modules', {'rubicon.objc': bridge}):
            self.assertEqual(occlusion_geometry(native), ((-4, 0, 88, 212),))
        array.arrayWithArray.assert_called_once_with(raw)
        native.reservedRegionsOfKind.assert_called_once_with('occlusion', options=0)

    def test_occlusion_changes_refresh_without_size_inset_or_edge_changes(self):
        from unittest.mock import patch
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        app = SimpleNamespace(active_host=True, loop=loop, resize_workspace=Mock())
        container = SimpleNamespace(content=SimpleNamespace(interface=SimpleNamespace(app=app)),
            width=951, height=669, top_inset=0, bottom_inset=0, left_inset=0, right_inset=84)
        async def exercise():
            with patch('mobile.ios_reader_chrome.occlusion_geometry', return_value=((867, 0, 84, 120),)) as regions:
                notify_viewport(container)
                await asyncio.sleep(0)
                notify_viewport(container)
                await asyncio.sleep(0)
                self.assertEqual(app.resize_workspace.call_count, 1)
                for value in (((867, 0, 84, 212),), ((867, 0, 84, 120),), ()):
                    regions.return_value = value
                    notify_viewport(container)
                    notify_viewport(container)
                    await asyncio.sleep(0)
                self.assertEqual(app.resize_workspace.call_count, 4)
        loop.run_until_complete(exercise())

    def test_bar_edge_change_refreshes_actions_without_a_size_change(self):
        from unittest.mock import patch
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        app = SimpleNamespace(active_host=True, loop=loop, resize_workspace=Mock())
        controller = object()
        container = SimpleNamespace(content=SimpleNamespace(interface=SimpleNamespace(app=app)),
            width=600, height=600, top_inset=0, bottom_inset=0, left_inset=0, right_inset=0,
            controller=controller)
        async def exercise():
            with patch('mobile.ios_toolbar.vertical_edge', return_value=2) as edge:
                notify_viewport(container)
                await asyncio.sleep(0)
                notify_viewport(container)
                await asyncio.sleep(0)
                self.assertEqual(app.resize_workspace.call_count, 1)
                for value in (1, 0, 2):
                    edge.return_value = value
                    notify_viewport(container)
                    await asyncio.sleep(0)
                self.assertEqual(app.resize_workspace.call_count, 4)
                edge.assert_called_with(controller)
        loop.run_until_complete(exercise())

    def test_size_and_inset_changes_coalesce_and_wake_on_portrait_return(self):
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        app = SimpleNamespace(active_host=True, loop=loop, resize_workspace=Mock())
        container = SimpleNamespace(content=SimpleNamespace(interface=SimpleNamespace(app=app)),
                                    width=390, height=700, top_inset=100, bottom_inset=34,
                                    left_inset=0, right_inset=0)
        async def exercise():
            notify_viewport(container)
            notify_viewport(container)
            await asyncio.sleep(0)
            self.assertEqual(app.resize_workspace.call_count, 1)
            for width, height, left in ((740, 320, 59), (390, 700, 0), (390, 700, 4)):
                container.width, container.height, container.left_inset = width, height, left
                notify_viewport(container)
                await asyncio.sleep(0)
            self.assertEqual(app.resize_workspace.call_count, 4)
            container.width = 800
            notify_viewport(container)
            app.active_host = False
            await asyncio.sleep(0)
            self.assertEqual(app.resize_workspace.call_count, 4)
        loop.run_until_complete(exercise())


class ShellContainmentTests(unittest.TestCase):
    def test_native_host_removes_outer_bar_and_restores_toolkit_ownership(self):
        from mobile.ios_reader_chrome import install_shell_root, restore_shell_root
        content, outer, root, placeholder = Mock(), Mock(), Mock(), Mock()
        content.title = 'Logistics'
        content.view.autoresizingMask = 0
        outer.viewControllers = [content]
        window = SimpleNamespace(rootViewController=outer, bounds=object())
        adapter = SimpleNamespace(parent=content, outer_navigation=outer,
                                  window=SimpleNamespace(_impl=SimpleNamespace(native=window)))
        root_class, controller_class = Mock(), Mock()
        root_class.alloc.return_value.init.return_value = root
        controller_class.alloc.return_value.init.return_value = placeholder
        bridge = SimpleNamespace(SEL=lambda value: value, ObjCClass=lambda name: controller_class)
        with patch.dict('sys.modules', {'rubicon.objc': bridge}):
            install_shell_root(adapter, root_class)
            self.assertIs(window.rootViewController, root)
            outer.setViewControllers.assert_called_once_with([placeholder], animated=False)
            self.assertEqual(placeholder.title, 'Logistics')
            root.addChildViewController.assert_called_once_with(content)
            content.didMoveToParentViewController.assert_called_once_with(root)
            install_shell_root(adapter, root_class)
            root_class.alloc.assert_called_once()
            placeholder.title = 'Updated window title'
            restore_shell_root(adapter)
            self.assertIs(window.rootViewController, outer)
            outer.setViewControllers.assert_called_with([content], animated=False)
            self.assertEqual(content.removeFromParentViewController.call_count, 2)
            self.assertEqual(content.title, 'Updated window title')
            self.assertEqual(content.view.autoresizingMask, 0)
            restore_shell_root(adapter)
            self.assertEqual(content.removeFromParentViewController.call_count, 2)

    def test_legacy_sdk_keeps_the_existing_root(self):
        from mobile.ios_reader_chrome import install_shell_root
        content = Mock()
        content.respondsToSelector.return_value = False
        adapter = SimpleNamespace(parent=content)
        root_class = Mock()
        with patch.dict('sys.modules', {'rubicon.objc': SimpleNamespace(SEL=lambda value: value, ObjCClass=Mock())}):
            install_shell_root(adapter, root_class)
        root_class.alloc.assert_not_called()


class NavigationAdapter(SimpleNamespace):
    pass


class WindowOcclusionTests(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.addCleanup(close_loop, self.loop)
        clearance = patch('mobile.ios_system_occlusions.reserve_bar_clearance')
        self.clearance = clearance.start(); self.addCleanup(clearance.stop)
        self.navigation = SimpleNamespace(view=Mock(), navigationBar=Mock())
        self.secondary = SimpleNamespace(view=Mock(), navigationBar=Mock())
        self.app = SimpleNamespace(active_host=True, loop=self.loop,
            native_host=SimpleNamespace(adapter=NavigationAdapter(navigation=[self.navigation])),
            adaptive=SimpleNamespace(secondary=self.secondary), resize_workspace=Mock())

    def test_root_only_changes_refresh_bar_owners_and_reclaim_idle_clearance(self):
        from unittest.mock import patch
        from mobile.ios_system_occlusions import observe_window_occlusions
        native = object()

        async def exercise():
            with patch('mobile.ios_reader_chrome.occlusion_geometry', return_value=((867, 0, 84, 124),)) as regions:
                # No leaf layout or window-size notification is delivered.
                for height in (124, 216, 124):
                    regions.return_value = ((867, 0, 84, height),)
                    observe_window_occlusions(self.app, native)
                    observe_window_occlusions(self.app, native)
                    await asyncio.sleep(0)
                self.assertEqual(self.app.resize_workspace.call_count, 3)
                for owner in (self.navigation, self.secondary):
                    self.assertEqual(owner.view.setNeedsLayout.call_count, 3)
                    self.assertEqual(owner.navigationBar.setNeedsLayout.call_count, 3)
                    self.assertEqual(owner.view.layoutIfNeeded.call_count, 3)
                # Stable geometry must not keep invalidating menus/layout.
                observe_window_occlusions(self.app, native)
                await asyncio.sleep(0)
                self.assertEqual(self.app.resize_workspace.call_count, 3)
                regions.assert_called_with(native)
        self.loop.run_until_complete(exercise())

    def test_outer_action_owner_receives_system_region_updates(self):
        from mobile.ios_system_occlusions import observe_window_occlusions
        outer = SimpleNamespace(view=Mock(), navigationBar=Mock())
        self.app.native_host.adapter.outer_navigation = outer
        more = SimpleNamespace(view=Mock(), navigationBar=Mock())
        self.app.native_host.destinations = ['chat']
        self.app.native_host.adapter.navigation_for = lambda destination: more
        async def exercise():
            with patch('mobile.ios_reader_chrome.occlusion_geometry', return_value=((382, 0, 84, 250),)):
                observe_window_occlusions(self.app, object())
                await asyncio.sleep(0)
            self.clearance.assert_any_call(outer)
            self.clearance.assert_any_call(more)
            outer.view.layoutIfNeeded.assert_called_once()
            more.view.layoutIfNeeded.assert_called_once()
        self.loop.run_until_complete(exercise())

    def test_missing_adapter_at_refresh_does_not_raise_or_consume_geometry(self):
        from mobile.ios_system_occlusions import observe_window_occlusions
        host = self.app.native_host
        host.destinations = ['chat']
        adapter = host.adapter
        adapter.navigation_for = Mock(return_value=self.navigation)
        native = object()
        errors = []
        self.loop.set_exception_handler(lambda loop, context: errors.append(context['exception']))

        async def exercise():
            with patch('mobile.ios_reader_chrome.occlusion_geometry', return_value=()):
                observe_window_occlusions(self.app, native)
                host.adapter = None
                await asyncio.sleep(0)
                self.assertEqual(errors, [])
                self.clearance.assert_not_called()
                self.app.resize_workspace.assert_not_called()
                self.assertFalse(self.app._ios_occlusion_refresh_pending)
                host.adapter = adapter
                observe_window_occlusions(self.app, native)
                await asyncio.sleep(0)
            self.clearance.assert_any_call(self.navigation)
            self.app.resize_workspace.assert_called_once()
        self.loop.run_until_complete(exercise())

    def test_same_geometry_on_replacement_coalesces_and_refreshes_current_owner(self):
        from mobile.ios_system_occlusions import observe_window_occlusions
        host = self.app.native_host
        first = SimpleNamespace(view=Mock(), navigationBar=Mock())
        later = SimpleNamespace(view=Mock(), navigationBar=Mock())
        native = object()

        async def exercise():
            with patch('mobile.ios_reader_chrome.occlusion_geometry', return_value=()):
                observe_window_occlusions(self.app, native)
                host.adapter = NavigationAdapter(navigation=[first])
                observe_window_occlusions(self.app, native)
                await asyncio.sleep(0)
                self.navigation.view.layoutIfNeeded.assert_not_called()
                first.view.layoutIfNeeded.assert_called_once()
                self.app.resize_workspace.assert_called_once()
                host.adapter = NavigationAdapter(navigation=[later])
                observe_window_occlusions(self.app, native)
                await asyncio.sleep(0)
                later.view.layoutIfNeeded.assert_called_once()
                self.assertEqual(self.app.resize_workspace.call_count, 2)
        self.loop.run_until_complete(exercise())

    def test_updates_coalesce_and_retired_windows_do_not_refresh(self):
        from unittest.mock import patch
        from mobile.ios_system_occlusions import observe_window_occlusions
        self.app.adaptive.secondary = self.navigation

        async def exercise():
            with patch('mobile.ios_reader_chrome.occlusion_geometry', return_value=((382, 0, 84, 170),)) as regions:
                observe_window_occlusions(self.app, object())
                regions.return_value = ((382, 0, 84, 250),)
                observe_window_occlusions(self.app, object())
                await asyncio.sleep(0)
                self.assertEqual(self.navigation.view.setNeedsLayout.call_count, 1)
                self.assertEqual(self.app.resize_workspace.call_count, 1)
                regions.return_value = ()
                observe_window_occlusions(self.app, object())
                self.app.active_host = False
                await asyncio.sleep(0)
                self.assertEqual(self.app.resize_workspace.call_count, 1)
        self.loop.run_until_complete(exercise())


class AndroidViewportTests(unittest.TestCase):
    def test_unchanged_global_layout_does_not_reenter_responsive_panels(self):
        from mobile.layout_events import native_resize_changed
        backend = type('Backend', (), {'__module__': 'toga_android.app'})
        native = Mock()
        native.getWidth.return_value, native.getHeight.return_value = 1080, 1920
        for name in ('getPaddingLeft', 'getPaddingTop', 'getPaddingRight', 'getPaddingBottom'):
            getattr(native, name).return_value = 0
        bar = Mock()
        bar.getWidth.return_value, bar.getVisibility.return_value = 1080, 0
        window = object()
        app = SimpleNamespace(main_window=window, _impl=backend(), body=object(),
            native_host=SimpleNamespace(adapter=SimpleNamespace(mode='bottom',
                impl=SimpleNamespace(native=native, native_navigationview=bar)),
                state=SimpleNamespace(destination='files')))
        self.assertTrue(native_resize_changed(app, window))
        self.assertFalse(native_resize_changed(app, window))
        native.getPaddingBottom.return_value = 400
        self.assertTrue(native_resize_changed(app, window))
        self.assertFalse(native_resize_changed(app, window))
        self.assertTrue(native_resize_changed(app, None))
        app.native_host.state.destination = 'chat'
        self.assertTrue(native_resize_changed(app, window))


class FixedControlAuditTests(unittest.TestCase):
    def test_page_button_hit_area_must_stay_above_home_indicator(self):
        from mobile_build.native_tests.tests.logisticsmobile.rotation_checks import assert_control_bounds
        window = SimpleNamespace(safeAreaInsets=SimpleNamespace(left=0, right=0, top=62, bottom=34),
                                 bounds=SimpleNamespace(size=SimpleNamespace(width=402, height=874)))
        rect = SimpleNamespace(origin=SimpleNamespace(x=4, y=808),
                               size=SimpleNamespace(width=48, height=48))
        with self.assertRaises(AssertionError):
            assert_control_bounds(rect, window, 'Previous page')
        rect.origin.y = 792
        assert_control_bounds(rect, window, 'Previous page')

    def test_callable_native_window_is_counted_and_cutout_overlap_is_rejected(self):
        import toga
        from unittest.mock import patch
        from mobile_build.native_tests.tests.logisticsmobile import rotation_checks
        window = SimpleNamespace(ptr=SimpleNamespace(value=1),
            safeAreaInsets=SimpleNamespace(left=47, right=47, top=0, bottom=21),
            bounds=SimpleNamespace(size=SimpleNamespace(width=844, height=390)))
        rect = SimpleNamespace(origin=SimpleNamespace(x=47, y=20),
                               size=SimpleNamespace(width=100, height=44))
        button = toga.Button('Keep clear of the notch')
        body = toga.Box(children=[button])
        native = SimpleNamespace(window=lambda: window, isHidden=lambda: False,
                                 bounds=object(), convertRect=lambda *args, **kwargs: rect)
        app = SimpleNamespace(body=body, main_window=SimpleNamespace(_impl=SimpleNamespace(native=window)))
        with patch.object(rotation_checks.sys, 'platform', 'ios'), \
                patch.object(body._impl, 'native', SimpleNamespace(window=lambda: window), create=True), \
                patch.object(button._impl, 'native', native, create=True):
            self.assertEqual(rotation_checks.assert_visible_controls(app), 1)
            body.title_actions = (button,)
            self.assertEqual(rotation_checks.assert_visible_controls(app), 1)
            body.remove(button)
            self.assertEqual(rotation_checks.assert_visible_controls(app), 1)
            rect.origin.x = 0
            with self.assertRaises(AssertionError):
                rotation_checks.assert_visible_controls(app)

    def test_uikit_navigation_uses_bar_bounds_while_content_keeps_safe_insets(self):
        import toga
        import sys
        from unittest.mock import patch
        from mobile_build.native_tests.tests.logisticsmobile import rotation_checks
        window = SimpleNamespace(ptr=SimpleNamespace(value=1),
            safeAreaInsets=SimpleNamespace(left=62, right=62, top=0, bottom=20),
            bounds=SimpleNamespace(size=SimpleNamespace(width=874, height=402)))
        bounds = SimpleNamespace(origin=SimpleNamespace(x=0, y=0),
                                 size=SimpleNamespace(width=874, height=54))
        rect = SimpleNamespace(origin=SimpleNamespace(x=38, y=0),
                               size=SimpleNamespace(width=44, height=44))
        body = toga.Box()
        native = SimpleNamespace(window=lambda: window, isHidden=lambda: False, alpha=1,
            bounds=object(), convertRect=Mock(return_value=rect), accessibilityLabel=None,
            isKindOfClass=lambda cls: True, subviews=[])
        bar = SimpleNamespace(isHidden=lambda: False, alpha=1, window=lambda: window,
            accessibilityLabel=None, bounds=bounds,
            isKindOfClass=lambda cls: False, subviews=lambda: [native])
        host = SimpleNamespace(adapter=SimpleNamespace(navigation=[SimpleNamespace(navigationBar=lambda: bar)]),
            destinations=['files'], state=SimpleNamespace(destination='files'))
        app = SimpleNamespace(body=body, native_host=host,
            main_window=SimpleNamespace(_impl=SimpleNamespace(native=window)))
        with patch.object(rotation_checks.sys, 'platform', 'ios'), \
                patch.dict(sys.modules, {'rubicon.objc': SimpleNamespace(ObjCClass=lambda name: object())}), \
                patch.object(body._impl, 'native', SimpleNamespace(window=lambda: window), create=True):
            self.assertEqual(rotation_checks.assert_visible_controls(app), 1)
            native.convertRect.assert_called_with(native.bounds, toView=bar)
            with self.assertRaises(AssertionError):
                rotation_checks.assert_control_bounds(rect, window, 'Content control')
            rect.origin.x = -5
            with self.assertRaises(AssertionError):
                rotation_checks.assert_visible_controls(app)


class ControlClearanceTests(unittest.TestCase):
    def test_vertical_bar_delegates_compression_without_adding_insets(self):
        from mobile.ios_system_occlusions import reserve_bar_clearance
        item = Mock(verticalBarCompressionBehavior=0)
        bar = Mock()
        bar.isHidden.return_value = False
        owner = SimpleNamespace(navigationBar=bar, topViewController=SimpleNamespace(navigationItem=item))
        with patch('mobile.ios_toolbar.vertical_edge', return_value=2), patch.dict(
                'sys.modules', {'rubicon.objc': SimpleNamespace(SEL=lambda name: name)}):
            self.assertFalse(reserve_bar_clearance(owner))
            self.assertEqual(item.verticalBarCompressionBehavior, 1)
            self.assertFalse(hasattr(owner, 'additionalSafeAreaInsets'))
            bar.isHidden.return_value = True
            reserve_bar_clearance(owner)
            self.assertEqual(item.verticalBarCompressionBehavior, 1)

    def test_native_bars_do_not_add_island_offsets_as_activity_changes(self):
        from mobile.ios_system_occlusions import reserve_bar_clearance
        from types import SimpleNamespace as NS
        insets = NS(top=5, left=2, bottom=3, right=4)
        owner = NS(navigationBar=Mock(), additionalSafeAreaInsets=insets)
        with patch.dict('sys.modules', {'rubicon.objc': NS(SEL=lambda name: name)}), patch(
                'mobile.ios_reader_chrome.occlusion_geometry') as regions:
            for occupied in (82, 120, 212, 400, 82):
                regions.return_value = ((535, 0, 134, occupied),)
                self.assertFalse(reserve_bar_clearance(owner))
                self.assertIs(owner.additionalSafeAreaInsets, insets)
            regions.assert_not_called()

    def test_closed_open_and_two_activities_use_current_column_geometry(self):
        from mobile.ios_system_occlusions import control_top_clearance as clearance
        self.assertEqual(clearance(((170, 8, 120, 62),), 0, 460, 59), 78)
        self.assertEqual(clearance(((850, 0, 90, 40),), 840, 950, 0), 48)
        self.assertEqual(clearance(((850, 0, 90, 40), (850, 52, 90, 52)), 840, 950, 0), 112)
        self.assertEqual(clearance(((850, 0, 90, 40), (850, 52, 90, 52)), 0, 800, 0), 0)
        self.assertEqual(clearance((), 0, 460, 59), 59)
        self.assertEqual(clearance(((850, 400, 90, 40),), 840, 950, 0), 0)

    def test_retiring_old_inset_preserves_other_owners_during_reentrant_layout(self):
        from mobile.ios_system_occlusions import reserve_bar_clearance
        from types import SimpleNamespace as NS
        def insets(top, left, bottom, right):
            return NS(top=top, left=left, bottom=bottom, right=right)
        class Owner:
            navigationBar = Mock()
            _logistics_occlusion_top = 8
            _insets = insets(13, 2, 3, 4)
            @property
            def additionalSafeAreaInsets(self):
                return self._insets
            @additionalSafeAreaInsets.setter
            def additionalSafeAreaInsets(self, value):
                self._insets = value
                self.reentered = reserve_bar_clearance(self)
        owner = Owner()
        with patch.dict('sys.modules', {'rubicon.objc': NS(SEL=lambda name: name, UIEdgeInsets=insets)}):
            self.assertTrue(reserve_bar_clearance(owner))
            self.assertFalse(owner.reentered)
            self.assertFalse(reserve_bar_clearance(owner))
        self.assertEqual(owner.additionalSafeAreaInsets, insets(5, 2, 3, 4))


class ContentBandTests(unittest.TestCase):
    def test_visible_native_title_retains_its_vertical_space(self):
        from mobile.ios_system_occlusions import compact_content_top
        item = SimpleNamespace(title='Nested page', titleView=None, prompt=None)
        owner = SimpleNamespace(navigationItem=item)
        navigation = SimpleNamespace(topViewController=owner, isNavigationBarHidden=lambda: False)
        controller = SimpleNamespace(navigationController=navigation)
        container = SimpleNamespace(controller=controller, top_inset=100)
        with patch('mobile.ios_toolbar.vertical_edge', return_value=2):
            self.assertFalse(compact_content_top(container))
            self.assertEqual(container.top_inset, 100)

    def test_vertical_shell_reclaims_only_unoccupied_content_column(self):
        from mobile.ios_system_occlusions import compact_content_top
        from types import SimpleNamespace as NS
        frame = NS(origin=NS(x=0, y=0), size=NS(width=951, height=669))
        window = NS(safeAreaInsets=NS(top=82))
        native = NS(window=window, bounds=frame, convertRect=lambda *a, **kw: frame,
                    respondsToSelector=lambda selector: True)
        controller = NS(navigationController=None)
        container = NS(controller=controller, native=native, top_inset=82, left_inset=0, right_inset=84)
        with patch('mobile.ios_toolbar.vertical_edge', return_value=2) as edge, patch.dict(
                'sys.modules', {'rubicon.objc': NS(SEL=lambda name: name)}), patch(
                'mobile.ios_reader_chrome.occlusion_geometry', return_value=((867, 0, 84, 212),)) as regions:
            self.assertTrue(compact_content_top(container))
            self.assertEqual(container.top_inset, 0)
            regions.return_value = ((800, 0, 151, 212),)
            self.assertTrue(compact_content_top(container))
            self.assertEqual(container.top_inset, 220)
            regions.return_value = ()
            compact_content_top(container)
            self.assertEqual(container.top_inset, 82)
            edge.return_value = 0
            container.top_inset = 140
            self.assertFalse(compact_content_top(container))
            self.assertEqual(container.top_inset, 140)

    def test_equal_size_move_and_all_safe_edges_change_geometry(self):
        from mobile.ios_system_occlusions import native_geometry
        from types import SimpleNamespace as NS
        frame = NS(origin=NS(x=0, y=0), size=NS(width=460, height=669))
        window = NS(frame=frame)
        safe = NS(top=82, left=0, bottom=28, right=84)
        native = NS(window=window, bounds=frame, safeAreaInsets=safe, convertRect=lambda *a, **kw: frame)
        previous = native_geometry(native)
        for field, value in (('left', 84), ('right', 0)):
            setattr(safe, field, value)
            current = native_geometry(native)
            self.assertNotEqual(current, previous)
            previous = current
        frame.origin.x = 490
        self.assertNotEqual(native_geometry(native), previous)
