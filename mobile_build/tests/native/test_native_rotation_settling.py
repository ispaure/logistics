"""Native rotation auditing tolerates transitions, never persistent overflow."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from contextlib import ExitStack
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from mobile_build.native_tests.tests.logisticsmobile import rotation_checks
from commonUtils.testing import waiting


class RotationSettlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_rotation_failure_records_state_without_changing_deadline(self):
        for observation in (None, RuntimeError('observer unavailable')):
            failure = AssertionError('native acknowledgement timed out')
            app = NS(main_window=object())
            with patch.object(rotation_checks, 'NativeRotation'), \
                    patch.object(rotation_checks.sys, 'platform', 'ios'), \
                    patch.object(rotation_checks, 'wait_until', new=AsyncMock(side_effect=failure)) as wait, \
                    patch.object(rotation_checks, 'rotation_failure_snapshot', side_effect=observation) as capture:
                with self.assertRaises(AssertionError) as caught:
                    await rotation_checks.rotate(app, 'landscape-left', timeout=.1)
                self.assertIs(caught.exception, failure)
                self.assertEqual(wait.call_args.kwargs['timeout'], .1)
                capture.assert_called_once_with(app, panel='native-request', cycle=-1, orientation='landscape-left')

    async def test_ios_response_not_possible_still_requires_exact_orientation(self):
        scene = NS(interfaceOrientation=3)
        app = NS(main_window=NS(_impl=NS(native=NS(windowScene=scene))))
        rotation = Mock(errors=['Error Domain=BSActionErrorDomain Code=1 response-not-possible'])

        async def wait(predicate, *, timeout, message):
            self.assertEqual(timeout, rotation_checks.IOS_ROTATION_ACK_TIMEOUT)
            self.assertFalse(predicate())
            scene.interfaceOrientation = 1
            self.assertTrue(predicate())

        with (
            patch.object(rotation_checks, 'NativeRotation', return_value=rotation),
            patch.object(rotation_checks.sys, 'platform', 'ios'),
            patch.object(rotation_checks, 'wait_until', side_effect=wait),
        ):
            await rotation_checks.rotate(app, 'portrait', settle=0)
        rotation.acknowledged.assert_not_called()

    async def test_transient_native_morph_is_remeasured_before_acceptance(self):
        with patch.object(rotation_checks, 'assert_visible_controls',
                          side_effect=[AssertionError('button still morphing'), 4]) as audit, \
                patch.object(waiting.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            self.assertEqual(await rotation_checks.settled_visible_controls(object()), 4)
            self.assertEqual(audit.call_count, 2)
            sleep.assert_awaited_once_with(.1)

    async def test_persistent_overflow_still_fails_after_bounded_settling(self):
        with patch.object(rotation_checks, 'assert_visible_controls',
                          side_effect=AssertionError('control outside viewport')) as audit, \
                patch.object(waiting, 'monotonic', side_effect=[0, 1, 2, 2]), \
                patch.object(waiting.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            with self.assertRaisesRegex(AssertionError, 'control outside viewport'):
                await rotation_checks.settled_visible_controls(object())
            self.assertEqual(audit.call_count, 2)
            self.assertEqual(sleep.await_count, 1)


class RotationLayoutReadinessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.diagnostics = {}
        self.elapsed = 0
        self.sleep = self.enterContext(patch.object(rotation_checks.asyncio, 'sleep', side_effect=self.advance))
        self.enterContext(patch.object(rotation_checks, 'monotonic', side_effect=lambda: self.elapsed))
        self.native_geometry_sample = self.enterContext(patch.object(
            rotation_checks, 'rotation_native_geometry', return_value=((402, 874), None)))
        self.acknowledged = Mock(return_value=True)

    async def advance(self, delay):
        self.elapsed += delay

    async def settle(self, app=None):
        return await rotation_checks.settled_rotation_layout(app, self.acknowledged, self.diagnostics)

    def fixture(self):
        def rect(width,height,y=0):
            return NS(origin=NS(x=0,y=y),size=NS(width=width,height=height))
        container=NS(bounds=rect(402,874),safeAreaInsets=NS(left=0,right=0,top=116,bottom=34))
        body=NS(bounds=rect(750,754))
        body.convertRect=lambda bounds,**kwargs:rect(bounds.size.width,bounds.size.height,116)
        window=NS(bounds=rect(402,874),safeAreaInsets=container.safeAreaInsets)
        view=NS(_impl=NS(native=body,container=NS(native=container)))
        app=NS(body=NS(children=[view]),main_window=NS(_impl=NS(native=window)))
        return app,body

    def native_geometry(self):
        stack=ExitStack()
        stack.enter_context(patch.object(rotation_checks.sys,'platform','ios'))
        stack.enter_context(patch('mobile.ios_content_background.preview_edge',return_value=0))
        stack.enter_context(patch('mobile.reading.reader_edges.page_footer',return_value=None))
        stack.enter_context(patch('mobile.document_location.side_title_reader',return_value=None))
        return stack

    async def test_valid_controls_do_not_accept_body_before_async_portrait_resize(self):
        app,body=self.fixture()
        async def resize(delay):
            body.bounds.size.width = 402
            await self.advance(delay)
        self.sleep.side_effect = resize
        with self.native_geometry(),patch.object(rotation_checks,'assert_visible_controls',return_value=4) as controls:
            count=await self.settle(app)
            geometry=rotation_checks.safe_geometry(app)
        self.assertEqual(count,4)
        self.assertEqual(geometry['view_width'],402)
        self.assertEqual(controls.call_count,5)
        self.assertEqual(self.acknowledged.call_count,5)

    async def test_persistent_stale_body_preserves_original_assertion_at_deadline(self):
        app,_=self.fixture()
        with self.native_geometry(),patch.object(rotation_checks,'assert_visible_controls',return_value=4):
            with self.assertRaises(AssertionError) as caught:
                await self.settle(app)
        self.assertEqual(caught.exception.args[0]['view_width'],750)
        self.assertEqual(self.elapsed, rotation_checks.CONTROL_SETTLE_TIMEOUT)
        self.assertEqual(len(self.diagnostics['samples']), 4)
        self.assertEqual(self.diagnostics['samples'][-1]['geometry']['view_width'], 750)

    async def test_controls_and_body_share_one_budget_instead_of_two(self):
        app,_=self.fixture()
        async def slow_layout(delay):
            await self.advance(1.9)
        self.sleep.side_effect = slow_layout
        with self.native_geometry(), \
                patch.object(rotation_checks,'assert_visible_controls',side_effect=[AssertionError('control morph'),4]) as controls:
            with self.assertRaises(AssertionError) as caught:
                await self.settle(app)
        self.assertEqual(caught.exception.args[0]['view_width'],750)
        self.assertEqual(controls.call_count,2)
        self.assertAlmostEqual(self.sleep.await_args.args[0], .1)

    async def test_persistent_control_failure_is_not_hidden_by_valid_body(self):
        app,body=self.fixture();body.bounds.size.width=402
        failure=AssertionError('required control hidden or outside viewport')
        with self.native_geometry(),patch.object(rotation_checks,'assert_visible_controls',side_effect=failure):
            with self.assertRaises(AssertionError) as caught:
                await self.settle(app)
        self.assertIs(caught.exception,failure)
        self.assertNotIn(str(failure), str(self.diagnostics))

    async def test_native_geometry_runtime_error_is_not_retried(self):
        app,_=self.fixture()
        with patch.object(rotation_checks,'assert_visible_controls',return_value=4), \
                patch.object(rotation_checks,'safe_geometry',side_effect=RuntimeError('native read failed')) as geometry:
            with self.assertRaisesRegex(RuntimeError,'native read failed'):
                await self.settle(app)
        geometry.assert_called_once()

    async def test_valid_control_movement_restarts_stability_even_at_same_count(self):
        positions = iter([10, 10, 10, 12, 12, 12, 12])
        def controls(app, *, frames):
            frames.append((1, (next(positions), 0, 44, 44)))
            return 1
        with patch.object(rotation_checks, 'assert_visible_controls', side_effect=controls), \
                patch.object(rotation_checks, 'safe_geometry', return_value={'view_width': 402}):
            self.assertEqual(await self.settle(), 1)
        self.assertEqual(self.sleep.await_count, 6)

    async def test_one_lost_acknowledgement_restarts_stability(self):
        self.acknowledged.side_effect = [True] * 3 + [False] + [True] * 4
        with patch.object(rotation_checks, 'assert_visible_controls', return_value=4) as controls, \
                patch.object(rotation_checks, 'safe_geometry', return_value={'view_width': 402}):
            self.assertEqual(await self.settle(), 4)
        self.assertEqual(self.acknowledged.call_count, 8)
        self.assertEqual(controls.call_count, 7)

    async def test_valid_but_changing_geometry_times_out_with_bounded_evidence(self):
        with patch.object(rotation_checks, 'assert_visible_controls', return_value=4), \
                patch.object(rotation_checks, 'safe_geometry', side_effect=lambda app: {'view_width': 402 + self.elapsed}):
            with self.assertRaisesRegex(AssertionError, 'did not stabilize'):
                await self.settle()
        self.assertEqual(self.elapsed, rotation_checks.CONTROL_SETTLE_TIMEOUT)
        self.assertEqual(len(self.diagnostics['samples']), 4)
        self.assertEqual([row['reason'] for row in self.diagnostics['samples']], ['Geometry changed'] * 4)

    async def test_final_sample_after_deadline_cannot_pass(self):
        def geometry(app):
            if self.acknowledged.call_count == 4:
                self.elapsed = rotation_checks.CONTROL_SETTLE_TIMEOUT + .1
            return {'view_width': 402}
        with patch.object(rotation_checks, 'assert_visible_controls', return_value=4), \
                patch.object(rotation_checks, 'safe_geometry', side_effect=geometry):
            with self.assertRaisesRegex(AssertionError, 'did not stabilize'):
                await self.settle()
        self.assertEqual(self.acknowledged.call_count, 4)

    async def test_cancellation_propagates_without_waiting_again(self):
        self.sleep.side_effect = asyncio.CancelledError
        with patch.object(rotation_checks, 'assert_visible_controls', return_value=4), \
                patch.object(rotation_checks, 'safe_geometry', return_value={'view_width': 402}):
            with self.assertRaises(asyncio.CancelledError):
                await self.settle()
        self.sleep.assert_awaited_once()
        self.assertEqual(self.diagnostics, {})

    async def test_changed_route_still_fails_after_joint_readiness(self):
        app=NS(show_locations=Mock())
        with patch.object(rotation_checks,'panel_state',side_effect=['original-route','different-route']), \
                patch.object(rotation_checks,'rotate_panel',new=AsyncMock(return_value=4)) as rotate:
            with self.assertRaises(AssertionError):
                await rotation_checks.exercise_rotation(app,cycles=1,panels={'workspaces'})
        rotate.assert_awaited_once_with(app,panel='workspaces',cycle=0,orientation='portrait')

    async def test_wrong_orientation_still_fails_before_layout_acceptance(self):
        app=NS(show_locations=Mock())
        failure=AssertionError('Native rotation did not complete: portrait')
        with patch.object(rotation_checks,'panel_state',return_value='original-route'), \
                patch.object(rotation_checks,'acknowledge_rotation',new_callable=AsyncMock,side_effect=failure), \
                patch.object(rotation_checks,'settled_rotation_layout',new_callable=AsyncMock) as settle, \
                patch.object(rotation_checks.sys,'platform','linux'):
            with self.assertRaises(AssertionError) as caught:
                await rotation_checks.exercise_rotation(app,cycles=1,panels={'workspaces'})
        self.assertIs(caught.exception,failure)
        settle.assert_not_awaited()


class RotationNativeGeometryTests(unittest.TestCase):
    def test_ios_waits_for_presentation_geometry_inside_the_owner_window(self):
        def rect(width):
            return NS(origin=NS(x=0, y=0), size=NS(width=width, height=402))

        def view(identity, parent=None):
            frame = rect(874)
            return NS(ptr=NS(value=identity), frame=frame, superview=parent,
                      layer=NS(frame=frame, presentationLayer=NS(frame=frame)))

        window = view(1)
        window.rootViewController = NS(transitionCoordinator=None)
        window.safeAreaInsets = NS(top=0, right=59, bottom=21, left=59)
        pane = view(2, window)
        body = view(3, pane)
        navigation = NS(transitionCoordinator=None, navigationBar=view(4))
        adapter = NS(navigation_for=Mock(return_value=navigation))
        app = NS(main_window=NS(_impl=NS(native=window)), body=NS(children=[NS(_impl=NS(native=body))]),
                 native_host=NS(adapter=adapter, state=NS(destination='files')))
        pose = {'interface_orientation': 3, 'hinge_status': 2, 'division_regions': [{'x': 200}]}
        with patch.object(rotation_checks.sys, 'platform', 'ios'), \
                patch.object(rotation_checks, 'pose_snapshot', return_value=pose):
            navigation.transitionCoordinator = object()
            self.assertEqual(rotation_checks.rotation_native_geometry(app), (None, 'UIKit transition active'))
            navigation.transitionCoordinator = None
            pane.layer.presentationLayer.frame = rect(402)
            self.assertEqual(rotation_checks.rotation_native_geometry(app), (None, 'UIKit presentation frame moving'))
            pane.layer.presentationLayer.frame = pane.layer.frame
            signature, pending = rotation_checks.rotation_native_geometry(app)
            self.assertIsNone(pending)
            self.assertEqual(signature['pose'], pose)
            self.assertEqual(signature['insets'], (0, 59, 21, 59))
            pane.superview = view(5)
            self.assertEqual(rotation_checks.rotation_native_geometry(app), (None, 'Content is detached from the main window'))

    def test_android_waits_for_rendered_viewport_and_active_navigation_layout(self):
        def view(*, requested=False):
            return NS(getLeft=lambda: 0, getTop=lambda: 0, getWidth=lambda: 874,
                      getHeight=lambda: 402, getVisibility=Mock(return_value=0),
                      isAttachedToWindow=lambda: True, isLayoutRequested=Mock(return_value=requested))

        body, content, bar, decor = view(requested=True), view(), view(), view()
        window = NS(getDecorView=lambda: decor)
        app = NS(body=NS(children=[NS(_impl=NS(native=body))]),
                 _impl=NS(native=NS(getWindow=lambda: window)),
                 native_host=NS(adapter=NS(impl=NS(native_content=content, native_navigationview=bar))))
        with patch.object(rotation_checks.sys, 'platform', 'android'):
            content.isLayoutRequested.return_value = True
            self.assertEqual(rotation_checks.rotation_native_geometry(app)[1], 'Android layout pending')
            content.isLayoutRequested.return_value = False
            bar.isLayoutRequested.return_value = True
            self.assertEqual(rotation_checks.rotation_native_geometry(app)[1], 'Android layout pending')
            bar.getVisibility.return_value = 8
            self.assertIsNone(rotation_checks.rotation_native_geometry(app)[1])
        body.isLayoutRequested.assert_not_called()

    def test_android_tracks_mounted_fixed_targets_and_excludes_scrolled_content(self):
        import sys
        class Button:
            children = ()
        class Scroll:
            pass
        def location(point):
            point[:] = [13, 29]
        fixed = Button()
        fixed._impl = NS(native=NS(getWidth=lambda: 44, getHeight=lambda: 48,
                                   isAttachedToWindow=lambda: True, isShown=lambda: True,
                                   getLocationOnScreen=location))
        scroll = Scroll()
        scroll.children = [Button()]  # Accessing this unmounted control would fail.
        toga = NS(Button=Button, Selection=type('Selection', (), {}), TextInput=type('TextInput', (), {}),
                  MultilineTextInput=type('MultilineTextInput', (), {}), ScrollContainer=Scroll)
        java = NS(jint=int, jarray=lambda kind: lambda size: [kind()] * size)
        with patch.dict(sys.modules, toga=toga, java=java), patch.object(rotation_checks.sys, 'platform', 'android'):
            frames = []
            count = rotation_checks.assert_visible_controls(NS(body=NS(children=[fixed, scroll])), frames=frames)
        self.assertEqual(count, 0)  # Android's existing fixed_controls report field.
        self.assertEqual(frames, [(id(fixed), (13, 29, 44, 48))])


class RotationFailureEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_snapshot_is_synchronous_and_preserves_original_exception(self):
        failure=AssertionError('Native rotation did not complete: landscape-left')
        app=object()
        with patch.object(rotation_checks,'acknowledge_rotation',new=AsyncMock(side_effect=failure)) as rotate, \
                patch.object(rotation_checks.sys,'platform','ios'), \
                patch.object(rotation_checks,'rotation_failure_snapshot') as capture:
            with self.assertRaises(AssertionError) as caught:
                await rotation_checks.rotate_panel(app,panel='folder',cycle=1,orientation='landscape-left')
            self.assertIs(caught.exception,failure)
            rotate.assert_awaited_once_with(app,'landscape-left',panel='folder')
            capture.assert_called_once_with(app,panel='folder',cycle=1,orientation='landscape-left')

    async def test_observer_failure_cannot_replace_original_failure(self):
        failure=AssertionError('original timeout')
        with patch.object(rotation_checks,'acknowledge_rotation',new=AsyncMock(side_effect=failure)), \
                patch.object(rotation_checks.sys,'platform','ios'), \
                patch.object(rotation_checks,'rotation_failure_snapshot',side_effect=RuntimeError('observer')):
            with self.assertRaises(AssertionError) as caught:
                await rotation_checks.rotate_panel(object(),panel='folder',cycle=1,orientation='landscape-left')
            self.assertIs(caught.exception,failure)

    async def test_success_does_not_run_failure_observer(self):
        acknowledged = Mock(return_value=True)
        with patch.object(rotation_checks, 'acknowledge_rotation', new=AsyncMock(return_value=acknowledged)), \
                patch.object(rotation_checks, 'settled_rotation_layout', new=AsyncMock(return_value=4)) as settle, \
                patch.object(rotation_checks,'rotation_failure_snapshot') as capture:
            app = object()
            self.assertEqual(await rotation_checks.rotate_panel(app,panel='folder',cycle=0,orientation='portrait'), 4)
            settle.assert_awaited_once_with(app, acknowledged, {})
            capture.assert_not_called()

    async def test_android_timeout_attaches_bounded_diagnostics_to_the_native_result(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        failure = AssertionError('Native rotation layout did not stabilize')
        async def timeout(app, acknowledged, diagnostics):
            diagnostics.update(samples=[{'reason': 'Android layout pending'}])
            raise failure
        with TemporaryDirectory() as directory, \
                patch.object(rotation_checks.sys, 'platform', 'android'), \
                patch.object(rotation_checks, 'acknowledge_rotation', new=AsyncMock()), \
                patch.object(rotation_checks, 'settled_rotation_layout', side_effect=timeout), \
                patch('builtins.print') as emit:
            app = NS(paths=NS(cache=directory))
            with self.assertRaises(AssertionError) as caught:
                await rotation_checks.rotate_panel(app, panel='folder', cycle=1, orientation='landscape-left')
            path = Path(directory) / 'logistics-native-ui-rotation-failure.json'
            report = json.loads(path.read_text())
        self.assertIs(caught.exception, failure)
        self.assertEqual(report, app._native_rotation_failure)
        self.assertEqual(report['readiness']['samples'], [{'reason': 'Android layout pending'}])
        self.assertEqual((report['panel'], report['cycle'], report['requested_orientation']),
                         ('folder', 1, 'landscape-left'))
        self.assertTrue(emit.call_args.args[0].startswith('LOGISTICS_NATIVE_ROTATION_FAILURE='))

    def test_snapshot_records_public_geometry_and_modal_without_document_content(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace as NS
        with TemporaryDirectory() as directory:
            layer=NS(frame='1032 x 1376',presentationLayer=NS(frame='1032 x 1376'),animationKeys=[])
            view=NS(className='TestView',window=object(),isHidden=False,bounds='1032 x 1376',layer=layer)
            controller=NS(className='TestController',viewIfLoaded=view,
                          transitionCoordinator=NS(isAnimated=True,isInteractive=False),
                          presentedViewController=NS(className='Modal'),isBeingPresented=False,isBeingDismissed=False)
            window=NS(**vars(view));window.rootViewController=controller
            window.windowScene=NS(interfaceOrientation=1,activationState=0)
            app=NS(main_window=NS(_impl=NS(native=window)),paths=NS(cache=directory),
                   screen_privacy=NS(inactive=False,resume_locked=True,disposed=False,interrupted=False,shield=view),
                   native_host=NS(state=NS(destination='files'),adapter=NS(content_controller=lambda dest:controller,navigation_for=lambda dest:controller)),
                   document_name='PRIVATE_CONTENT_MUST_NOT_APPEAR')
            with patch('builtins.print'):
                result=rotation_checks.rotation_failure_snapshot(app,panel='folder',cycle=1,orientation='landscape-left')
            saved=Path(directory)/'logistics-native-ui-rotation-failure.json'
            self.assertEqual(json.loads(saved.read_text()),result)
            self.assertEqual(result['interface_orientation'],1)
            self.assertTrue(result['controllers'][0]['transition_active'])
            self.assertEqual(result['controllers'][0]['modal_class'],'Modal')
            self.assertTrue(result['privacy']['resume_locked'])
            self.assertNotIn(app.document_name,saved.read_text())


class RotationWidthFailureTests(unittest.IsolatedAsyncioTestCase):
    async def check_original_failure(self, stage, observer_error=None):
        from mobile_build.native_tests.tests.logisticsmobile import rotation_screens
        failure = AssertionError('original ' + stage)
        async def visit(app, check, *, panels):
            await check('provider-epub')
        app = object()
        with patch.object(rotation_checks.sys, 'platform', 'ios'), \
                patch.object(rotation_screens, 'visit_screens', side_effect=visit), \
                patch.object(rotation_checks.asyncio, 'sleep', new_callable=AsyncMock), \
                patch.object(rotation_checks, 'panel_state', return_value='unchanged'), \
                patch.object(rotation_checks, 'acknowledge_rotation', new_callable=AsyncMock), \
                patch.object(rotation_checks, 'rotation_failure_snapshot', return_value={'schema': 1}), \
                patch.object(rotation_checks, 'pose_snapshot', return_value={}), \
                patch.object(rotation_checks, 'settled_rotation_layout', new_callable=AsyncMock,
                             side_effect=failure if stage == 'joint' else None, return_value=4), \
                patch.object(rotation_checks, 'safe_geometry', side_effect=failure), \
                patch.object(rotation_checks, 'observe_epub_width_failure', new_callable=AsyncMock,
                             side_effect=observer_error) as observe:
            with self.assertRaises(AssertionError) as caught:
                await rotation_checks.exercise_rotation(app, panels={'provider-epub'})
        self.assertIs(caught.exception, failure)
        context = dict(panel='provider-epub', cycle=0, orientation='portrait')
        if stage == 'joint':
            context['native'] = {'schema': 1}
        observe.assert_awaited_once_with(app, **context)

    async def test_joint_and_final_failures_preserve_original_assertion(self):
        for stage in ('joint', 'final'):
            with self.subTest(stage=stage):
                await self.check_original_failure(stage)

    async def test_observer_error_or_cancellation_never_replaces_either_failure(self):
        for stage in ('joint', 'final'):
            for error in (RuntimeError('observer'), asyncio.CancelledError()):
                with self.subTest(stage=stage, error=type(error).__name__):
                    await self.check_original_failure(stage, error)

    async def test_initial_and_passive_width_records_use_existing_diagnostic_and_cached_result(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            app = NS(paths=NS(cache=directory))
            with patch.object(rotation_checks, 'rotation_failure_snapshot', return_value={'schema': 1}), \
                    patch.object(rotation_checks, 'epub_width_snapshot', side_effect=[{'width': 750}, {'width': 402}]), \
                    patch('builtins.print'):
                await rotation_checks.observe_epub_width_failure(app, panel='provider-epub', cycle=1, orientation='portrait')
            path = Path(directory) / 'logistics-native-ui-rotation-failure.json'
            stored = json.loads(path.read_text())
            self.assertEqual(stored, app._native_rotation_failure)
            self.assertEqual([row['width'] for row in stored['reader_width']['samples']], [750, 402])
            self.assertEqual([row['stage'] for row in stored['reader_width']['samples']],
                             ['latched-failure', 'next-loop-turn'])
            self.assertFalse(path.with_suffix('.tmp').exists())

    async def test_retained_initial_snapshot_survives_later_observer_failure(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            app = NS(paths=NS(cache=directory))
            with patch.object(rotation_checks, 'rotation_failure_snapshot', return_value={'schema': 1}), \
                    patch.object(rotation_checks, 'epub_width_snapshot', side_effect=[{'width': 750}, RuntimeError('observer')]), \
                    patch('builtins.print'):
                with patch.object(rotation_checks.sys, 'platform', 'ios'):
                    await rotation_checks.capture_epub_width_failure(app, panel='provider-epub', cycle=1, orientation='portrait')
            path = Path(directory) / 'logistics-native-ui-rotation-failure.json'
            self.assertEqual(json.loads(path.read_text())['reader_width']['samples'][0]['width'], 750)
