"""Tracked version edits keep both platforms and locked dependency metadata aligned."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logistics_build.app_version import set_version
from mobile_build.deployment.manager_settings import app_version


class AppVersionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'Python').mkdir()
        (self.root / 'mobile_build').mkdir()
        self.desktop = self.root / 'Python/pyproject.toml'
        self.mobile = self.root / 'mobile_build/pyproject.toml'
        self.lock = self.root / 'Python/uv.lock'
        self.desktop.write_text('[project]\nname = "logistics"\nversion = "0.1.15"\n')
        self.mobile.write_text('[tool.briefcase]\nversion = "0.1.9"\nbundle = "io.github.ispaure"\n')
        self.lock.write_text('version = 1\n[[package]]\nname = "logistics"\nversion = "0.1.15"\n'
                             '[[package]]\nname = "dependency"\nversion = "4.5.6"\n')

    def contents(self):
        return {p: p.read_bytes() for p in (self.desktop, self.mobile, self.lock)}

    def test_unified_edit_repairs_drift_without_touching_identity_or_dependencies(self):
        with self.assertRaisesRegex(ValueError, 'versions differ'):
            app_version(self.mobile.parent)
        result = set_version(self.root, '0.1.16')
        self.assertEqual(result['version'], '0.1.16')
        self.assertEqual(app_version(self.mobile.parent), '0.1.16')
        self.assertIn('version = "0.1.16"', self.desktop.read_text())
        self.assertIn('name = "logistics"\nversion = "0.1.16"', self.lock.read_text())
        self.assertIn('name = "dependency"\nversion = "4.5.6"', self.lock.read_text())
        self.assertIn('bundle = "io.github.ispaure"', self.mobile.read_text())

    def test_invalid_version_or_ambiguous_metadata_changes_nothing(self):
        before = self.contents()
        for version in ('0.1', '../other', '0.1.16\ncommand'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                set_version(self.root, version)
            self.assertEqual(self.contents(), before)
        self.lock.write_text('version = 1\npackage = []\n')
        before = self.contents()
        with self.assertRaisesRegex(ValueError, 'uniquely'):
            set_version(self.root, '0.1.16')
        self.assertEqual(self.contents(), before)

    def test_partial_write_failure_restores_previous_metadata(self):
        before = self.contents()
        original = Path.write_text
        def write(path, text, *args, **kwargs):
            if path == self.mobile and '0.1.16' in text:
                original(path, '[partially truncated')
                raise OSError('synthetic write refusal')
            return original(path, text, *args, **kwargs)
        with patch.object(Path, 'write_text', write), self.assertRaisesRegex(OSError, 'write refusal'):
            set_version(self.root, '0.1.16')
        self.assertEqual(self.contents(), before)

    def test_version_display_can_expose_drift_for_explicit_repair(self):
        self.assertEqual(app_version(self.mobile.parent, check_project=False), '0.1.9')


if __name__ == '__main__':
    unittest.main()
