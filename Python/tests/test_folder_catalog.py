"""Detached folder projection preserves account identity and explicit host grouping."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from services.folders.catalog import FolderCopy, CredentialScope, credential_source, project_catalog, source_category


class FolderCatalogTests(unittest.TestCase):
    def test_equal_remote_names_do_not_merge_across_credential_packages(self):
        copies = [FolderCopy(('a', 'Drive'), 'Drive', credential_source('/a/keys.zip'), 'Cloud', False, True),
                  FolderCopy(('b', 'Drive'), 'Drive', credential_source('/b/keys.zip'), 'Cloud', True, False)]
        groups = project_catalog(copies)
        self.assertEqual(len(groups), 2)
        self.assertNotEqual(groups[0].identity, groups[1].identity)
        self.assertTrue(groups[0].locked)
        self.assertFalse(groups[1].locked)
        self.assertEqual(source_category('rclone', 'Session network shares'), 'Home Server')
        self.assertEqual(source_category('dropbox', 'Session network shares'), 'Cloud')

    def test_local_projection_uses_physical_identity_and_first_context_preference(self):
        copies = [FolderCopy('/copy', 'Drive', ('loaded',), payload='loaded'),
                  FolderCopy('/copy', 'Drive', ('retained',), payload='retained'),
                  FolderCopy('/other', 'Drive', (), payload='local-only')]
        groups = project_catalog(copies, grouping='physical')
        self.assertEqual([group.copies[0].payload for group in groups], ['loaded', 'local-only'])
        scope = CredentialScope({'Drive'}, '/a/keys.zip')
        self.assertEqual(deepcopy(scope).source_identity, scope.source_identity)
        self.assertNotEqual(scope, CredentialScope({'Drive'}, '/b/keys.zip'))

    def test_mobile_adapter_preserves_separate_locked_and_loaded_package_scopes(self):
        from mobile.folder_hub import FolderDiscoverySnapshot, discover_folder_choices, credential_choices
        with TemporaryDirectory() as directory:
            first, second = dict(zip='A.zip', remotes=['Drive']), dict(zip='B.zip', remotes=['Drive'])
            snapshot = FolderDiscoverySnapshot(Path(directory), {}, ('Drive',), (first, second), (), {},
                (dict(package_name='B.zip', remotes=['Drive']),))
            with patch('mobile.folder_hub.hub_entries', return_value=[('Drive', (), [('Remote', ('remote', 'Drive'))])]), \
                 patch('mobile.local_sources.shared_files', return_value=None):
                choices = discover_folder_choices(snapshot).choices
            self.assertEqual(set(choices), {'All files', 'Drive (A)', 'Drive (B)'})
            self.assertTrue(choices['Drive (A)']['locked'])
            self.assertFalse(choices['Drive (B)']['locked'])
            self.assertEqual(set(credential_choices(choices, CredentialScope({'Drive'}, 'A.zip'))), {'Drive (A)'})
