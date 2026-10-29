"""Build identity works in release ZIPs without requiring Git or a network."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from services.build_version import installed_build


class BuildVersionTests(unittest.TestCase):
    def test_release_identity_and_legacy_marker_work_without_git(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('services.build_version.subprocess.run') as git:
                (root / '.app-install.json').write_text(json.dumps({'revision': 'a' * 40}))
                self.assertEqual(installed_build(root).label, 'Source build · aaaaaaaaaa')
                (root / '.app-version.json').write_text(json.dumps(dict(
                    tag='v0.1.1-alpha.30', revision='b' * 40, committed_at='2026-10-13T22:00:00-04:00')))
                identity = installed_build(root)
                self.assertEqual(identity.label.splitlines()[0], 'v0.1.1-alpha.30 · bbbbbbbbbb')
                self.assertRegex(identity.label.splitlines()[1], r'2026-10-1[34] \d\d:\d\d')
                self.assertIn('2026-10-13T22:00:00-04:00', identity.details)
                git.assert_not_called()

    def test_invalid_or_missing_identity_does_not_break_launch(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for value in (None, [], {'revision': '../oops'}, {'revision': 'a' * 40, 'tag': 'bad\nlabel'}):
                (root / '.app-version.json').write_text(json.dumps(value))
                self.assertEqual(installed_build(root).label, 'Development build')

