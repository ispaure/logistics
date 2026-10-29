"""External display routing must opt into real UIKit sessions, not just paint a window."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import sys
import unittest
from unittest.mock import Mock, patch

from mobile_build.build_support.scene_build import configure
from mobile.external_display import ExternalComicDisplay


class ExternalSceneActivationTests(unittest.TestCase):
    def test_manifest_declares_external_scene_roles_and_is_repeatable(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'LogisticsMobile'
            folder.mkdir()
            info = folder / 'LogisticsMobile-Info.plist'
            info.write_bytes(plistlib.dumps({'CFBundleIdentifier': 'preserved',
                'UIApplicationSceneManifest': {'UISceneConfigurations': {}}}))
            main = folder / 'main.m'
            main.write_text('UIApplicationMain(argc, argv, nil, @"PythonAppDelegate")')
            configure(root)
            result = plistlib.loads(info.read_bytes())
            scenes = result['UIApplicationSceneManifest']['UISceneConfigurations']
            for role in ('UIWindowSceneSessionRoleExternalDisplayNonInteractive', 'UIWindowSceneSessionRoleExternalDisplay'):
                self.assertEqual(scenes[role][0]['UISceneDelegateClassName'], 'LogisticsSceneDelegate')
                self.assertEqual(scenes[role][0]['UISceneClassName'], 'UIWindowScene')
            self.assertEqual(result['CFBundleIdentifier'], 'preserved')
            configure(root)
            self.assertEqual(plistlib.loads(info.read_bytes()), result)

    def test_ios27_registers_once_and_releases_previous_controller(self):
        delegate = object()
        output = ExternalComicDisplay(NS(external_scene_delegate=delegate))
        accessory, configuration = Mock(), Mock()
        factory = Mock()
        factory.alloc.return_value.initWithName.return_value = configuration
        def cls(name):
            return accessory if name == 'UISceneAccessory' else factory
        controller = Mock()
        host = NS(main_window=NS(_impl=NS(native=NS(rootViewController=controller))))
        with patch.dict(sys.modules, {'rubicon.objc': NS(ObjCClass=cls)}):
            output.register_ios(host)
            first = controller.registerSceneAccessory.return_value
            output.register_ios(host)
            controller.registerSceneAccessory.assert_called_once()
            self.assertIs(configuration.delegateClass, delegate)
            factory.alloc.return_value.initWithName.assert_called_with('Logistics comic display',
                sessionRole='UIWindowSceneSessionRoleExternalDisplayNonInteractive')
            other = Mock()
            host.main_window._impl.native.rootViewController = other
            output.register_ios(host)
            controller.unregisterSceneAccessory.assert_called_once_with(first)
            output.dispose()
            other.unregisterSceneAccessory.assert_called_once()
            self.assertIsNone(output.ios_registration)

    def test_older_ios_does_not_require_accessory_class(self):
        output = ExternalComicDisplay(NS())
        with patch.dict(sys.modules, {'rubicon.objc': NS(ObjCClass=Mock(side_effect=NameError))}):
            output.register_ios(NS())
        self.assertIsNone(output.ios_registration)
