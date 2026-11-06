"""Behavioral regressions owned by this feature."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from commonUtils.testing.stages import TestStage
from unittest.mock import patch
from types import ModuleType
from features.discovery import get_feature_names, load_named_features

TEST_STAGE = TestStage.REGRESSION


class OptionalFeatureDiscoveryTests(unittest.TestCase):
    def test_discovery_separates_infrastructure_from_legacy_feature_packages(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('zebra', 'runtime', '_private', 'alpha'):
                package = root / name
                package.mkdir()
                # Discovery must not import packages or require register().
                (package / '__init__.py').write_text('raise AssertionError("not imported")\n')
            (root / 'assets').mkdir()
            (root / 'helper.py').write_text('')
            self.assertEqual(get_feature_names(root), ['alpha', 'zebra'])

    def test_application_discovery_does_not_expose_runtime_as_a_feature(self):
        from features.feature_runtime import FeatureRegistry
        names = FeatureRegistry().get_feature_names()
        self.assertNotIn('runtime', names)
        self.assertIn('books', names)
        self.assertIn('comics', names)

    def test_broken_optional_feature_does_not_hide_healthy_feature(self):
        healthy = ModuleType('features.good')
        def load(name):
            if name.endswith('.bad'):
                raise ImportError('missing optional dependency')
            return healthy
        with patch('features.discovery.importlib.import_module', side_effect=load):
            broken, good = load_named_features(['bad', 'good'], 'features')
        self.assertIn('missing optional dependency', broken.FEATURE_LOAD_ERROR)
        self.assertIs(good, healthy)
