"""Crash diagnostics must not own the app or hide the original failure."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import gc
import json
from pathlib import Path
import tempfile
import unittest
import weakref
from unittest.mock import AsyncMock, patch

from mobile_build.native_tests.tests.logisticsmobile.rotation_crash_probe import (
    RotationTrace, controller_state, native_flag, native_state,
)


class App:
    pass


class RotationCrashTraceTests(unittest.TestCase):
    def test_scene_snapshot_enumerates_nsset_via_all_objects(self):
        from types import SimpleNamespace as NS
        window = NS(ptr=NS(value=1), rootViewController=None, isKeyWindow=True)
        scene = NS(ptr=NS(value=2), activationState=0, interfaceOrientation=1, windows=[window])
        window.windowScene = scene
        native_app = NS(connectedScenes=NS(allObjects=lambda: [scene]))
        classes = {'NSThread': NS(isMainThread=lambda: True),
                   'UIApplication': NS(sharedApplication=native_app)}
        app = NS(main_window=NS(_impl=NS(native=window)),
                 native_host=NS(adapter=None, state=NS(destination='home')),
                 routes=NS(screens={'home': [('file-picker', object())]}))
        with patch.dict('sys.modules', {'rubicon.objc': NS(ObjCClass=classes.__getitem__)}):
            snapshot = native_state(app)
        self.assertEqual(snapshot['hosts'], [dict(scene=2, activation=0, windows=[1])])
        self.assertEqual(snapshot['routes'], {'home': ['file-picker']})
        self.assertTrue(snapshot['main_thread'])
        self.assertTrue(snapshot['key_window'])
        json.dumps(snapshot)

    def test_controller_getters_store_scalar_addresses_in_both_bridge_forms(self):
        from types import SimpleNamespace as NS
        owner = NS(ptr=NS(value=12))
        for getter in (lambda value: value, lambda value: lambda: value):
            owner.parentViewController = getter(None)
            owner.presentedViewController = getter(NS(ptr=NS(value=34)))
            owner.presentingViewController = getter(None)
            owner.transitionCoordinator = getter(NS(ptr=NS(value=56)))
            self.assertEqual(controller_state(getter(owner)), dict(
                address=12, parent=None, presented=34, presenting=None, transition=56))

    def test_instrumentation_preserves_callback_failure_and_acceptance_predicate(self):
        import asyncio
        from commonUtils.testing.rotation import NativeRotation
        from commonUtils.ui.native.navigation import NativeNavigationHost
        from mobile_build.native_tests.tests.logisticsmobile import rotation_checks, rotation_crash_probe
        from mobile_build.native_tests.tests.logisticsmobile.timings import SuiteTimings

        failure = AssertionError('original orientation failure')
        predicate = lambda: False
        received = []

        def original_request(owner, orientation, *, on_rejected=None):
            on_rejected('native rejection')
            raise failure

        with tempfile.TemporaryDirectory() as directory:
            app = App()
            app.paths = App()
            app.paths.cache = directory
            trace = RotationTrace(app, snapshot=lambda app: {})
            try:
                with patch.object(NativeRotation, 'request', original_request), \
                        patch.object(rotation_checks, 'acknowledge_rotation',
                                     AsyncMock(side_effect=[predicate, failure])), \
                        patch.object(SuiteTimings, 'checkpoint'), \
                        patch.object(NativeNavigationHost, 'install'), \
                        patch.object(NativeNavigationHost, 'uninstall'):
                    rotation_crash_probe.install(trace)
                    owner = NativeRotation(None, platform='ios')
                    with self.assertRaises(AssertionError) as caught:
                        owner.request('portrait', on_rejected=received.append)
                    self.assertIs(caught.exception, failure)
                    self.assertEqual(received, ['native rejection'])
                    result = asyncio.run(rotation_checks.acknowledge_rotation(app, 'portrait', panel='home'))
                    self.assertIs(result, predicate)
                    self.assertFalse(result())
                    with self.assertRaises(AssertionError) as caught:
                        asyncio.run(rotation_checks.acknowledge_rotation(app, 'landscape-left'))
                    self.assertIs(caught.exception, failure)
            finally:
                trace.stream.close()

    def test_native_flags_support_rubicon_properties_and_custom_getters(self):
        owner = App()
        for value in (False, lambda: False):
            owner.flag = value
            self.assertFalse(native_flag(owner, 'flag'))
        for value in (True, lambda: True):
            owner.flag = value
            self.assertTrue(native_flag(owner, 'flag'))

    def test_trace_does_not_retain_application_or_snapshot_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            app = App()
            app.paths = App()
            app.paths.cache = directory
            observed = weakref.ref(app)
            trace = RotationTrace(app, snapshot=lambda app: dict(identity=id(app)))
            try:
                trace.emit('request-before', native=True, orientation='portrait')
                del app
                gc.collect()
                self.assertIsNone(observed())
                trace.emit('owner-gone', native=True)
                rows = [json.loads(line) for line in Path(trace.path).read_text().splitlines()]
                self.assertIn('native', rows[0])
                self.assertNotIn('native', rows[1])
                self.assertEqual([row['sequence'] for row in rows], [1, 2])
            finally:
                trace.stream.close()

    def test_failed_native_getter_and_closed_output_cannot_replace_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            app = App()
            app.paths = App()
            app.paths.cache = directory
            def unavailable(app):
                raise ValueError('scene is detached')
            trace = RotationTrace(app, snapshot=unavailable)
            trace.emit('acknowledgement-raised', native=True, exception='AssertionError')
            trace.stream.close()
            trace.emit('late-finalizer', native=True)
            row = json.loads(Path(trace.path).read_text())
            self.assertEqual(row['exception'], 'AssertionError')
            self.assertEqual(row['snapshot_error'], 'ValueError: scene is detached')


if __name__ == '__main__':
    unittest.main()
