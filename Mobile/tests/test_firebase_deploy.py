import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from Mobile import firebase_deploy as beta
from Mobile import deploy_all as all_deploy


class FirebaseDeployTests(unittest.TestCase):
    def test_group_display_name_resolves_to_actual_alias_without_guessing(self):
        groups = [dict(name='projects/123/groups/friends-beta', displayName='Friends')]
        self.assertEqual(beta.resolve_group(groups, 'FRIENDS'), 'friends-beta')
        self.assertEqual(beta.resolve_group(groups, 'friends-beta'), 'friends-beta')
        with self.assertRaises(ValueError):
            beta.resolve_group(groups, 'Family')
        with self.assertRaises(ValueError):
            beta.resolve_group(groups * 2, 'Friends')

    def test_preflight_verifies_package_before_group_or_build(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'firebase-distribution.json').write_text(json.dumps(dict(
                app_id='1:123:android:abc', bundle_id=beta.android.BUNDLE, group='Friends')))
            answers = [[{}], [dict(projectId='project', projectNumber='123')],
                       [dict(appId='1:123:android:abc', packageName='wrong.package')]]
            with patch.object(beta, 'ROOT', root), patch.object(beta, 'firebase_json', side_effect=answers) as query:
                with self.assertRaisesRegex(ValueError, 'package'):
                    beta.preflight('firebase')
            self.assertEqual(query.call_count, 3)

    def test_missing_signing_key_never_creates_replacement(self):
        with TemporaryDirectory() as directory:
            private = Path(directory)
            (private / 'signing.json').write_text('{"password":"test"}')
            with patch.object(beta, 'PRIVATE', private), patch.object(beta.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Restore'):
                    beta.signing({})
            run.assert_not_called()

    def test_build_counter_never_reuses_reserved_or_existing_build(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'; private.mkdir()
            (private / 'build.json').write_text('{"last_build":2090000000}')
            (root / 'build/firebase/2090000005').mkdir(parents=True)
            with patch.object(beta, 'ROOT', root), patch.object(beta, 'PRIVATE', private):
                self.assertEqual(beta.reserve_build(), 2090000006)
                self.assertEqual(beta.reserve_build(), 2090000007)

    def test_declining_upload_keeps_build_and_does_not_distribute(self):
        with TemporaryDirectory() as directory:
            with patch.object(beta, 'PRIVATE', Path(directory)), \
                    patch.object(beta, 'firebase_cli', return_value='firebase'), \
                    patch.object(beta, 'preflight', return_value=({'app_id': 'test'}, 'friends')), \
                    patch.object(beta, 'build', return_value=(Path('beta.apk'), Path('notes.txt'))), \
                    patch('builtins.input', return_value='n'), \
                    patch.object(beta.subprocess, 'run') as run, patch.object(beta.sys, 'argv', ['beta']):
                beta.main()
            run.assert_not_called()

    def test_all_deployments_stop_or_continue_after_failure(self):
        result = type('Result', (), {'returncode': 1})()
        with patch.object(all_deploy.subprocess, 'run', return_value=result) as run:
            self.assertEqual(all_deploy.deploy_all(ask=lambda _: 'n'), 1)
            self.assertEqual(run.call_count, 1)
        with patch.object(all_deploy.subprocess, 'run', return_value=result) as run:
            self.assertEqual(all_deploy.deploy_all(ask=lambda _: 'y'), 1)
            self.assertEqual(run.call_count, 4)
