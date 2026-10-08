"""System-folder policy resolves links and remains configurable without banning user volumes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from services import folder_safety


class FolderSafetyTests(unittest.TestCase):
    def test_protected_roots_cover_supported_platforms(self):
        self.assertIn(Path('/Applications'), folder_safety.protected_roots('darwin'))
        self.assertIn(Path('/usr'), folder_safety.protected_roots('linux'))
        roots = folder_safety.protected_roots('win32', {'SystemRoot': 'D:/Windows', 'ProgramFiles': 'D:/Program Files'})
        self.assertIn(Path('D:/Windows'), roots)
        self.assertIn(Path('D:/Program Files'), roots)

    def test_protected_descendants_aliases_and_recursive_ancestors_are_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            reserved = root / 'System'
            reserved.mkdir()
            child = reserved / 'child'; child.mkdir()
            alias = root / 'alias'; alias.symlink_to(reserved, target_is_directory=True)
            policy = root / 'maintenance.ini'; policy.write_text('[FolderSafety]\nprotect_system_folders=true\n')
            with patch.object(folder_safety, 'get_policy_path', return_value=policy), patch.object(folder_safety, 'protected_roots', return_value=[reserved]):
                for path in (reserved, child, alias, root):
                    with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'protected system folder'):
                        folder_safety.require_safe_folder(path)
                self.assertEqual(folder_safety.require_safe_folder(root, recursive=False), root)
                volume = root / 'ExternalDrive'; volume.mkdir()
                self.assertEqual(folder_safety.require_safe_folder(volume), volume)
            policy.write_text(f'[FolderSafety]\nprotect_system_folders=false\nadditional_protected_paths=\n    {reserved}\n')
            with patch.object(folder_safety, 'get_policy_path', return_value=policy):
                with self.assertRaises(ValueError):
                    folder_safety.require_safe_folder(child)

    def test_missing_policy_fails_closed(self):
        with TemporaryDirectory() as root, patch.object(folder_safety, 'get_policy_path', return_value=Path(root) / 'missing.ini'):
            with self.assertRaisesRegex(ValueError, 'missing'):
                folder_safety.require_safe_folder(root)
