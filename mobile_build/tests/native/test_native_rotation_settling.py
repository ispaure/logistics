"""Native rotation auditing tolerates transitions, never persistent overflow."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from unittest.mock import AsyncMock, patch

from mobile_build.native_tests.tests.logisticsmobile import rotation_checks
from commonUtils.testing import waiting


class RotationSettlingTests(unittest.IsolatedAsyncioTestCase):
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


class RotationFailureEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_snapshot_is_synchronous_and_preserves_original_exception(self):
        failure=AssertionError('Native rotation did not complete: landscape-left')
        app=object()
        with patch.object(rotation_checks,'rotate',new=AsyncMock(side_effect=failure)) as rotate, \
                patch.object(rotation_checks.sys,'platform','ios'), \
                patch.object(rotation_checks,'rotation_failure_snapshot') as capture:
            with self.assertRaises(AssertionError) as caught:
                await rotation_checks.rotate_panel(app,panel='folder',cycle=1,orientation='landscape-left')
            self.assertIs(caught.exception,failure)
            rotate.assert_awaited_once_with(app,'landscape-left')
            capture.assert_called_once_with(app,panel='folder',cycle=1,orientation='landscape-left')

    async def test_observer_failure_cannot_replace_original_failure(self):
        failure=AssertionError('original timeout')
        with patch.object(rotation_checks,'rotate',new=AsyncMock(side_effect=failure)), \
                patch.object(rotation_checks.sys,'platform','ios'), \
                patch.object(rotation_checks,'rotation_failure_snapshot',side_effect=RuntimeError('observer')):
            with self.assertRaises(AssertionError) as caught:
                await rotation_checks.rotate_panel(object(),panel='folder',cycle=1,orientation='landscape-left')
            self.assertIs(caught.exception,failure)

    async def test_success_does_not_run_failure_observer(self):
        with patch.object(rotation_checks,'rotate',new=AsyncMock()), \
                patch.object(rotation_checks,'rotation_failure_snapshot') as capture:
            await rotation_checks.rotate_panel(object(),panel='folder',cycle=0,orientation='portrait')
            capture.assert_not_called()

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
