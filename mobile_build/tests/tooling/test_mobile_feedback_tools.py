"""QA acceptance cannot install a main/release APK or target a physical device."""
from commonUtils.testing.stages import TestStage
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

from mobile_build.validation import document_storage_tools as tools

TEST_STAGE = TestStage.REGRESSION


class MobileFeedbackToolsTests(unittest.TestCase):
    def test_comic_probe_waits_for_startup_restore_before_local_or_provider_work(self):
        import asyncio
        from types import SimpleNamespace
        import toga
        from commonUtils.testing.event_loop import close_loop
        from features.rclone.mobile.cloud_ui import CloudUI
        from mobile.app import LogisticsMobile
        from mobile_build.native_tests.tests.logisticsmobile import comic_guidance_probe as probe

        def asynchronous_startup(app):
            # Exercise the native phased startup on the dummy backend. Reader
            # admission and the probe's own on_running/task contract stay real.
            from mobile.appearance import install_appearance
            from mobile.startup import begin_startup
            install_appearance(app)
            app._startup_in_progress = app._async_startup = True
            begin_startup(app)

        original_prepare = CloudUI.prepare_cloud
        def prepare_cloud(cloud):
            original_prepare(cloud)
            if cloud.cloud_client is None:
                # Dummy has no device credential vault. This synthetic client
                # lets the real start_cloud_restore own its normal busy flag.
                cloud.cloud_client = SimpleNamespace(vault=object(), generation=0,
                    package_records=[], cancel=lambda: None, close=lambda: None)

        for basic in (True, False):
            with self.subTest(basic=basic), TemporaryDirectory() as directory, \
                    patch.dict(os.environ, {'TOGA_DUMMY_HOME': directory,
                        'LOGISTICS_COMIC_GUIDANCE_BASIC': '1' if basic else '0'}), \
                    patch.object(toga.App, 'app', toga.App.app):
                started, release = asyncio.Event(), asyncio.Event()
                restored = False
                app = None

                async def restore_cloud(cloud, *args, **kwargs):
                    nonlocal restored
                    self.assertTrue(cloud.cloud_busy)
                    started.set()
                    try:
                        await release.wait()
                        restored = True
                    finally:
                        cloud.set_cloud_busy(False)

                async def local_check(host, report):
                    self.assertTrue(restored)
                    self.assertFalse(host.cloud_busy)

                async def provider_check(host, rtl, provider, copies, report):
                    self.assertTrue(restored)
                    self.assertFalse(host.cloud_busy)
                    owner = await host.provider_owner(provider, copies)
                    self.assertEqual(owner.crypt_reader.key, 'Comics/02.cbz')
                    return owner

                async def visual_check(owner, rtl, report):
                    return owner

                try:
                    with patch.object(LogisticsMobile, 'startup', asynchronous_startup), \
                            patch.object(CloudUI, 'prepare_cloud', prepare_cloud), \
                            patch.object(CloudUI, 'restore_cloud', restore_cloud), \
                            patch.object(probe, 'local_overlay_check', side_effect=local_check) as local, \
                            patch.object(probe.ComicGuidanceProbe, 'provider_matrix', autospec=True,
                                side_effect=provider_check) as provider, \
                            patch.object(probe.ComicGuidanceProbe, 'settled', new_callable=AsyncMock), \
                            patch.object(probe.ComicGuidanceProbe, 'visual_checks', side_effect=visual_check), \
                            patch.object(probe.ComicGuidanceProbe, 'lifecycle_checks', new_callable=AsyncMock), \
                            patch.object(probe.ComicGuidanceProbe, 'library_checks', new_callable=AsyncMock), \
                            patch.object(probe, 'pose_snapshot', return_value={'backend': 'dummy'}), \
                            patch.object(probe, 'capture_window', new_callable=AsyncMock):
                        probe.main().main_loop()
                        app = toga.App.app

                        async def exercise():
                            await asyncio.wait_for(started.wait(), 3)
                            self.assertFalse(app._startup_in_progress)
                            self.assertTrue(app.cloud_busy)
                            local.assert_not_awaited()
                            provider.assert_not_awaited()
                            release.set()
                            await asyncio.wait_for(app._native_check_task, 10)
                            report = json.loads((Path(app.paths.cache) / probe.RESULT).read_text())
                            self.assertTrue(report['success'], report)
                            self.assertTrue(report['reader_cleanup'])
                            if basic:
                                local.assert_awaited_once()
                                provider.assert_not_awaited()
                            else:
                                local.assert_not_awaited()
                                self.assertEqual(provider.await_count, 2)
                        app.loop.run_until_complete(exercise())
                finally:
                    release.set()
                    if app is not None:
                        app.main_window.close()
                        close_loop(app.loop)

    def test_comic_packaged_launch_completes_real_host_startup(self):
        import toga
        from commonUtils.testing.event_loop import close_loop
        from mobile_build.native_tests.tests.logisticsmobile import comic_guidance_probe
        ComicGuidanceProbe = comic_guidance_probe.ComicGuidanceProbe
        with TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'TOGA_DUMMY_HOME': directory}), \
                patch.object(toga.App, 'app', toga.App.app):
            try:
                # Same entry-point contract emitted by copy_payload. Use the
                # real app/startup and only replace the native platform backend.
                exec('from mobile_build.native_tests.tests.logisticsmobile.comic_guidance_probe import main\n'
                     'main().main_loop()', {})
                app = toga.App.app
                self.assertIsInstance(app, ComicGuidanceProbe)
                self.assertFalse(app._startup_in_progress)
                self.assertTrue(app.active_host)
                self.assertIsNotNone(app.main_window.content)
                app.checkpoint()
                # A local-only probe never creates the lazy provider manager.
                # Exercise real finalization without invoking native rendering.
                self.assertFalse(hasattr(app, 'private_sessions'))
                with patch.dict(os.environ, {'LOGISTICS_COMIC_GUIDANCE_BASIC': '1'}), \
                        patch.object(comic_guidance_probe, 'local_overlay_check', new_callable=AsyncMock):
                    app.loop.run_until_complete(app.probe())
                report = json.loads((Path(app.paths.cache) / comic_guidance_probe.RESULT).read_text())
                self.assertTrue(report['success'], report)
                self.assertTrue(report['reader_cleanup'])
                self.assertFalse(hasattr(app, 'private_sessions'))
            finally:
                app = toga.App.app
                if isinstance(app, ComicGuidanceProbe):
                    app.main_window.close()
                    close_loop(app.loop)

    def test_comic_probe_only_overrides_intended_host_hooks(self):
        from mobile.app import LogisticsMobile
        from mobile_build.native_tests.tests.logisticsmobile.comic_guidance_probe import ComicGuidanceProbe
        inherited = {name for base in LogisticsMobile.__mro__ for name in vars(base)}
        defined = {name for name in vars(ComicGuidanceProbe) if not name.startswith('__')}
        self.assertEqual(inherited & defined, {'startup', 'on_running'})
        self.assertIs(ComicGuidanceProbe.checkpoint, LogisticsMobile.checkpoint)

    def test_comic_probe_returns_app_for_the_packaged_main_loop(self):
        from mobile_build.native_tests.tests.logisticsmobile import comic_guidance_probe
        with patch.object(comic_guidance_probe, 'ComicGuidanceProbe') as factory:
            self.assertIs(comic_guidance_probe.main(), factory.return_value)
            factory.assert_called_once_with('Comic Guidance QA', 'io.github.ispaure.logisticscomicqa')
            factory.return_value.main_loop.assert_not_called()

    def test_comic_driver_waits_for_missing_or_partial_requests(self):
        for raw in (b'', b'cat: cache/comic-guidance-request.json: No such file or directory\n',
                    b'run-as: package is not running\n', b'{"action":', b'\xff'):
            for android in (False, True):
                with self.subTest(raw=raw, android=android):
                    self.assertIsNone(tools.comic_guidance_action(raw, android=android))

    def test_comic_driver_accepts_only_supported_platform_actions(self):
        for android in (False, True):
            self.assertEqual(tools.comic_guidance_action(b'{"action":"background"}', android=android),
                             'background')
        for action in ('reduce-motion-on', 'reduce-motion-off'):
            raw = tools.json.dumps(dict(action=action)).encode()
            self.assertEqual(tools.comic_guidance_action(raw, android=True), action)
            with self.assertRaises(ValueError):
                tools.comic_guidance_action(raw)
        for raw in (b'[]', b'null', b'{}', b'{"action":12}', b'{"action":"install"}'):
            for android in (False, True):
                with self.subTest(raw=raw, android=android), self.assertRaises(ValueError):
                    tools.comic_guidance_action(raw, android=android)

    def test_comic_native_touch_requires_flat_finite_nonnegative_points(self):
        for action, points in (('native-tap', [0, 1.5]), ('native-swipe', [0, 1, 2.5, 3])):
            raw = json.dumps(dict(action=action, points=points)).encode()
            self.assertEqual(tools.comic_guidance_action(raw), action)
            with self.assertRaises(ValueError):
                tools.comic_guidance_action(raw, android=True)
            for invalid in (None, {}, '12', [], [1], [1, 2, 3], [[1, 2], [3, 4]],
                            [True, 2], [-1, 2], [float('nan'), 2], [float('inf'), 2],
                            [0, 1, 2, False], [0, 1, 2, -1], [0, 1, 2, float('inf')]):
                with self.subTest(action=action, points=invalid), self.assertRaises(ValueError):
                    tools.comic_guidance_action(json.dumps(dict(action=action, points=invalid)).encode())

    def test_comic_scope_cli_rejects_wrong_probe_or_device_before_staging(self):
        cases = (
            ['ios', '--comic-scope', 'basic'],
            ['android', '--probe', 'comic-guidance', '--comic-scope', 'windows'],
            ['android', '--probe', 'comic-guidance', '--comic-scope', 'fold'],
            ['ios', '--probe', 'comic-guidance', '--comic-scope', 'windows'],
            ['ios', '--probe', 'comic-guidance', '--comic-scope', 'fold', '--family', 'iPhone Duo'],
        )
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'evidence'
            for args in cases:
                with self.subTest(args=args), \
                        patch.object(tools.sys, 'argv', ['document_storage_tools', *args, '--output', str(output)]), \
                        patch.object(tools.sys, 'stderr', new_callable=StringIO), \
                        patch.object(tools, 'stage') as stage:
                    with self.assertRaises(SystemExit) as error:
                        tools.main()
                    self.assertEqual(error.exception.code, 2)
                    stage.assert_not_called()
                    self.assertFalse(output.exists())

    def test_comic_scope_cli_routes_every_supported_scope(self):
        for platform in ('ios', 'android'):
            scopes = tools.COMIC_SCOPES if platform == 'ios' else tuple(
                scope for scope in tools.COMIC_SCOPES if scope not in ('windows', 'fold'))
            for scope in scopes:
                with self.subTest(platform=platform, scope=scope), TemporaryDirectory() as directory:
                    root = Path(directory)
                    workspace = root / 'workspace'
                    workspace.mkdir()
                    args = ['document_storage_tools', platform, '--probe', 'comic-guidance',
                            '--comic-scope', scope, '--output', str(root / 'evidence')]
                    if scope == 'windows':
                        args += ['--family', 'iPad']
                    elif scope == 'fold':
                        args += ['--family', 'iPhone Duo', '--pose', 'partial', '--duoctl', str(root / 'duoctl')]
                    with patch.object(tools.sys, 'argv', args), patch.dict(os.environ), \
                            patch.object(tools, 'SOURCE', tools.SOURCE), \
                            patch.object(tools.manager_settings, 'settings', return_value=({
                                'tools.xcode': 'xcode', 'tools.android_sdk': 'sdk', 'tools.java': 'java'}, None)), \
                            patch.object(tools, 'scratch') as scratch, \
                            patch.object(tools, 'stage', return_value={}), \
                            patch.object(tools, 'run_ios') as ios, patch.object(tools, 'run_android') as android:
                        scratch.return_value.__enter__.return_value = workspace
                        tools.main()
                        selected, other = (ios, android) if platform == 'ios' else (android, ios)
                        selected.assert_called_once()
                        other.assert_not_called()
                        self.assertEqual(selected.call_args.kwargs['comic_scope'], scope)

    def test_comic_android_scope_uses_installed_app_stdin_marker(self):
        for scope in ('matrix', 'basic', 'lifecycle', 'library', 'readers', 'reduced-motion'):
            with self.subTest(scope=scope), TemporaryDirectory() as directory, \
                    patch.object(tools.subprocess, 'run') as run:
                emulator = Mock(adb=Path('/owned/adb'))
                emulator.invoke.return_value = '0.0'
                env = {'ANDROID_HOME': '/owned/sdk'}
                tools.prepare_comic_android(emulator, 'owned-emulator', tools.BUNDLE, Path(directory), env, scope)
                run.assert_called_once_with(['/owned/adb', '-s', 'owned-emulator', 'shell', 'run-as',
                    tools.BUNDLE, 'tee', 'cache/comic-guidance-scope'],
                    input=('matrix' if scope == 'basic' else scope).encode(), env=env,
                    capture_output=True, check=True, timeout=15)
                if scope == 'basic':
                    emulator.invoke.assert_any_call('-s', 'owned-emulator', 'shell', 'run-as',
                        tools.BUNDLE, 'touch', 'cache/comic-guidance-basic')
                if scope == 'reduced-motion':
                    emulator.invoke.assert_any_call('-s', 'owned-emulator', 'shell', 'settings',
                        'put', 'global', 'animator_duration_scale', '0')
                    self.assertTrue((Path(directory) / 'android-os-reduced-motion.json').is_file())

    def exercise_comic_ios(self, root, *, scope=None, request=None, family='iPhone', duoctl=None):
        cache = root / 'container/Library/Caches'
        cache.mkdir(parents=True)
        (cache / 'comic-guidance-result.json').write_text(json.dumps(dict(success=True)))
        if request is not None:
            (cache / 'comic-guidance-request.json').write_text(json.dumps(request))
        client = Mock()
        client.devices.return_value = {'devices': {'runtime': [dict(isAvailable=True,
            name=family, deviceTypeIdentifier='owned-model')]}}
        client.create.return_value = 'owned-simulator'
        client.invoke.side_effect = lambda *args, **kwargs: str(root / 'container') if args[0] == 'get_app_container' else '1'
        env = {'SIMCTL_CHILD_LOGISTICS_COMIC_GUIDANCE_BASIC': 'stale',
               'SIMCTL_CHILD_LOGISTICS_COMIC_GUIDANCE_SCOPE': 'stale'}
        with patch.object(tools, 'AppleSimulators', return_value=client), \
                patch.object(tools.subprocess, 'Popen') as launch, \
                patch.object(tools.subprocess, 'run') as run:
            tools.exercise_ios_app(root / 'QA.app', root / 'evidence', env,
                entry_point='tests.logisticsmobile.comic_guidance_probe', result_name='comic-guidance-result.json',
                family=family, duoctl=duoctl, comic_scope=scope)
        return client, launch, run, cache, root / 'evidence'

    def test_comic_ios_scope_sets_child_environment_and_native_os_policy(self):
        for scope in ('matrix', 'basic', 'lifecycle', 'reduced-motion'):
            with self.subTest(scope=scope), TemporaryDirectory() as directory:
                client, launch, _, _, output = self.exercise_comic_ios(Path(directory), scope=scope)
                environment = launch.call_args.kwargs['env']
                self.assertEqual(environment['SIMCTL_CHILD_LOGISTICS_COMIC_GUIDANCE_SCOPE'],
                                 'matrix' if scope == 'basic' else scope)
                self.assertEqual(environment.get('SIMCTL_CHILD_LOGISTICS_COMIC_GUIDANCE_BASIC'),
                                 '1' if scope == 'basic' else None)
                if scope != 'basic':
                    client.invoke.assert_any_call('launch', 'owned-simulator', 'com.apple.Preferences')
                if scope == 'reduced-motion':
                    writes = client.invoke.call_args_list
                    setting = call('spawn', 'owned-simulator', 'defaults', 'write',
                                   'com.apple.Accessibility', 'ReduceMotionEnabled', '-int', '1')
                    install = call('install', 'owned-simulator', str(Path(directory) / 'QA.app'), timeout=180)
                    self.assertLess(writes.index(setting), writes.index(install))
                    self.assertTrue((output / 'ios-os-reduced-motion.json').is_file())

    def test_comic_ios_native_touch_uses_owned_simulator_and_keeps_receipt(self):
        for action, points in (('native-tap', [3, 4]), ('native-swipe', [1, 2, 3, 4])):
            with self.subTest(action=action), TemporaryDirectory() as directory:
                _, _, run, cache, output = self.exercise_comic_ios(Path(directory),
                    request=dict(action=action, points=points), family='iPhone Duo', duoctl=Path('/reviewed/duoctl'))
                command = [tools.sys.executable, '/reviewed/duoctl', '-d', 'owned-simulator',
                           'tap' if action == 'native-tap' else 'swipe', *map(str, points)]
                if action == 'native-swipe':
                    command += ['--duration', '.25']
                self.assertEqual(run.call_args.args[0], command)
                self.assertTrue(run.call_args.kwargs['check'])
                self.assertTrue((cache / 'comic-guidance-done').is_file())
                self.assertFalse((cache / 'comic-guidance-request.json').exists())
                receipt = json.loads((output / 'ios-comic-native-touches.json').read_text())
                self.assertEqual(receipt, [dict(action=action, points=points, device='owned-simulator', completed=True)])

    def test_comic_diagnostics_retain_bitmap_thumbnail_and_lifecycle_evidence(self):
        names = tools.diagnostics('tests.logisticsmobile.comic_guidance_probe')
        expected = {f'comic-guidance-bitmap-{rtl}-{mask}-{direction}{suffix}.png'
            for rtl in ('ltr', 'rtl') for mask in ('00', '10', '01', '11') for direction in (-1, 1)
            for suffix in ('', '-thumbnail')}
        expected.update(f'comic-guidance-layout-{rtl}-{part}{suffix}.png'
            for rtl in ('ltr', 'rtl') for part in ('half-0', 'half-1', 'spread-0') for suffix in ('', '-thumbnail'))
        expected.update(f'comic-guidance-external-{rtl}-{phase}.png'
            for rtl in ('ltr', 'rtl') for phase in ('before', 'during'))
        expected.update(('comic-guidance-os-static-ltr.png', 'comic-guidance-os-static-rtl.png',
            'comic-guidance-scene-return.png', 'comic-guidance-fold-portrait.png', 'comic-guidance-fold-landscape-left.png'))
        self.assertTrue(expected <= set(names))
        self.assertEqual(len(names), len(set(names)))

    def test_ios_runtime_on_android_is_rejected_before_qa_staging(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'evidence'
            argv = ['document_storage_tools', 'android', '--ios-runtime',
                    'com.apple.CoreSimulator.SimRuntime.iOS-27-1', '--output', str(output)]
            with patch.object(tools.sys, 'argv', argv), \
                    patch.object(tools.sys, 'stderr', new_callable=StringIO) as error_output, \
                    patch.object(tools, 'stage') as stage:
                with self.assertRaises(SystemExit) as error:
                    tools.main()
                self.assertEqual(error.exception.code, 2)
                self.assertIn('--ios-runtime requires iOS', error_output.getvalue())
                stage.assert_not_called()
                self.assertFalse(output.exists())

    def test_wrong_package_and_non_debug_apks_are_rejected_before_device_creation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for metadata in (
                    "package: name='io.github.ispaure.logisticsmobile'\napplication-debuggable\n",
                    "package: name='io.github.ispaure.logisticsstorageqa'\n"):
                with self.subTest(metadata=metadata), \
                        patch('mobile_build.deployment.android_deploy.build_tools', return_value=root), \
                        patch.object(tools.subprocess, 'check_output', return_value=metadata), \
                        patch.object(tools, 'AndroidEmulator') as emulator:
                    with self.assertRaisesRegex(ValueError, 'Debug build.*isolated QA'):
                        tools.exercise_android_app(root / 'input.apk', root, root / 'evidence', {}, {})
                    emulator.assert_not_called()

    def test_mobile_feedback_rejects_explicit_android_device_before_staging(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'evidence'
            argv = ['document_storage_tools', 'android', '--probe', 'mobile-feedback',
                    '--device', 'physical-device', '--output', str(output)]
            with patch.object(tools.sys, 'argv', argv), patch.object(tools, 'stage') as stage:
                with self.assertRaises(SystemExit) as error:
                    tools.main()
                self.assertEqual(error.exception.code, 2)
                stage.assert_not_called()
                self.assertFalse(output.exists())
