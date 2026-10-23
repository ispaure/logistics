"""Regression coverage for failed feature discovery and numerical boundaries."""
import unittest
from unittest.mock import patch
from types import ModuleType

from features.discovery import load_named_features
from features.aviation_tools.mathUtils.flightUtils import (
    Coordinate, MagneticDeviation, distance_from_coords, magnetic_course,
)


class MaintenanceSafetyTests(unittest.TestCase):
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

    def test_distance_and_course_boundaries(self):
        point = Coordinate(42.12, -73.23)
        self.assertAlmostEqual(distance_from_coords(point, point), 0, places=3)
        self.assertEqual(magnetic_course(355, MagneticDeviation(10, 'west')), 5)
        for coordinates in ((91, 0), (0, 181), (float('nan'), 0)):
            with self.assertRaises(ValueError):
                Coordinate(*coordinates)

    def test_duplicate_local_names_are_preserved_and_remote_match_is_explicit(self):
        from models.local_folder import LocalFolder
        from services.folders.entries import get_folder_entries
        folders = [LocalFolder('/first/Books'), LocalFolder('/second/Books')]
        with patch('services.folders.entries._get_excluded_remote_names', return_value=set()), patch('services.folders.entries._get_excluded_folder_name_suffixes', return_value=()):
            entries = get_folder_entries(local_folders=folders)
            self.assertEqual({entry.local.path for entry in entries}, {folder.path for folder in folders})
            with self.assertRaises(ValueError):
                get_folder_entries(['Books'], local_folders=folders)
