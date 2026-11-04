"""Behavioral regressions owned by this feature."""
import unittest
from commonUtils.testing.stages import TestStage
from unittest.mock import patch
from types import ModuleType
from features.discovery import load_named_features

TEST_STAGE = TestStage.REGRESSION


class OptionalFeatureDiscoveryTests(unittest.TestCase):
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
