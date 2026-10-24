"""Credential display grouping preserves identity and persistence boundaries."""
import unittest

from features.rclone.mobile.credential_catalog import CredentialCatalog, remember_association


class CredentialCatalogTests(unittest.TestCase):
    def package(self, name, remotes=('Cloud',), saved=False, **extra):
        return dict(package_name=name, remotes=list(remotes), saved=saved, **extra)

    def test_equal_basenames_keep_distinct_package_scopes(self):
        catalog = CredentialCatalog([self.package('/one/Account.zip'), self.package('/two/Account.zip')])
        groups = catalog.groups({'Cloud'}, visible=lambda _: True)
        self.assertEqual(list(groups), ['All', 'Account', 'Account (2)'])
        self.assertEqual(groups['Account'].source_identity[1], '/one/Account.zip')
        self.assertEqual(groups['Account (2)'].source_identity[1], '/two/Account.zip')

    def test_explicit_folder_snapshot_limits_remotes_but_keeps_loaded_group(self):
        catalog = CredentialCatalog([self.package('Loaded.zip')])
        groups = catalog.groups(set(), visible=lambda _: True)
        self.assertEqual(list(groups), ['All', 'Loaded'])
        self.assertEqual(set(groups['Loaded']), set())

    def test_loaded_snapshot_replaces_retained_names_without_merging_packages(self):
        catalog = CredentialCatalog([self.package('Account.zip', ('Fresh',))])
        groups = catalog.groups({'Fresh', 'Stale'}, visible=lambda _: True)
        self.assertEqual(set(groups['Account']), {'Fresh'})

    def test_alias_exclusions_use_original_name_and_snapshot_is_detached(self):
        record = self.package('Account.zip', aliases={'Secret': 'Secret @ Account'})
        catalog = CredentialCatalog([record])
        record['aliases'].clear()
        record['remotes'].append('Later')
        names = catalog.visible_remotes(['Secret @ Account', 'Public'], (frozenset({'secret'}), ()))
        self.assertEqual(names, ['Public'])
        self.assertEqual(catalog.packages[0].remotes, ('Cloud',))

    def test_session_association_never_enters_saved_projection(self):
        previous = [dict(zip='Saved.zip', remotes=['Cloud'], session_only=False)]
        update = remember_association(previous, [], 'Private.zip', ['Secret'], session_only=True)
        self.assertEqual(update.saved, previous)
        self.assertEqual(update.sessions, [dict(zip='Private.zip', remotes=['Secret'], session_only=True)])
        promoted = remember_association(update.saved, update.sessions, 'Private.zip', ['Secret'], session_only=False)
        self.assertEqual(promoted.sessions, [])
        self.assertTrue(all(not item['session_only'] for item in promoted.saved))

    def test_saved_history_is_bounded_and_inputs_are_not_mutated(self):
        previous = [dict(zip=f'{i}.zip', remotes=[], session_only=False) for i in range(32)]
        update = remember_association(previous, [], 'New.zip', [], session_only=False)
        self.assertEqual(len(update.saved), 32)
        self.assertEqual(update.saved[0]['zip'], '1.zip')
        self.assertEqual(previous[0]['zip'], '0.zip')
