"""App cache identity changes when executable permissions or payload change."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from Scripts.ios_backend import bundle_digest


class BundleIdentityTests(unittest.TestCase):
    def test_payload_and_mode_changes_invalidate_the_bundle(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);binary=root/'binary';binary.write_bytes(b'synthetic');binary.chmod(0o644)
            before=bundle_digest(root);mode=binary.stat().st_mode;binary.chmod(0o755)
            if binary.stat().st_mode!=mode:
                self.assertNotEqual(bundle_digest(root),before)
            else:
                self.assertEqual(bundle_digest(root),before)
            before=bundle_digest(root);binary.write_bytes(b'changed')
            self.assertNotEqual(bundle_digest(root),before)
