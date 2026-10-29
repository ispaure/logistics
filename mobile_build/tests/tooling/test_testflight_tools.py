
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from mobile_build.deployment.testflight_tools import BUNDLE, build_number, export_options, export_release, keychain_groups_match, release_identity, validate_profile


class TestFlightWorkflowTests(unittest.TestCase):
    identity = dict(bundle_id=BUNDLE, team_id='ABCDEFGHIJ', application_identifier='ABCDEFGHIJ.' + BUNDLE,
                    keychain_access_groups=[])

    def test_archive_lock_does_not_precreate_release_directory(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from build_manager.locking import workspace_lock
        from mobile_build.deployment import testflight_tools as tools
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'pyproject.toml').write_text('[tool.briefcase]\nbundle="io.github.ispaure"\nversion="0.1.9"\n')
            workspace = root / 'build/testflight/123'

            def archive(args, destination, identity, env):
                self.assertEqual(destination, workspace)
                self.assertFalse(destination.exists())
                with self.assertRaises(RuntimeError):
                    with workspace_lock(destination.parent / '.123.retention.lock'):
                        pass
                destination.mkdir()

            with patch.object(tools, 'ROOT', root), \
                    patch.object(tools, 'release_identity', return_value=self.identity), \
                    patch.object(tools, 'installed', return_value=[]), \
                    patch.object(tools, 'choose', return_value=('/Applications/Xcode.app', 'sdk')), \
                    patch.object(tools, 'archive_release', side_effect=archive) as build, \
                    patch('logistics_build.build_retention.clean_builds'), \
                    patch.dict('os.environ'), \
                    patch('sys.argv', ['testflight_tools', 'archive', '--build-number', '123']):
                tools.main()
                build.assert_called_once()
            self.assertTrue(workspace.is_dir())

    def test_distribute_existing_workspace_checks_uploaded_identity_without_build_or_upload(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from mobile_build.deployment import testflight_tools as tools
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'pyproject.toml').write_text('[tool.briefcase]\nbundle="io.github.ispaure"\nversion="0.1.16"\n')
            workspace = root / 'retained' / '123'
            workspace.mkdir(parents=True)
            build = dict(build_number='123', bundle_id=BUNDLE, signed=True, version='0.1.16')
            (workspace / 'release.json').write_text(json.dumps(dict(identity=self.identity, build=build)))
            uploaded = workspace / 'upload-result.json'
            uploaded.write_text(json.dumps(dict(status='uploaded', build=build)))
            with patch.object(tools, 'ROOT', root), \
                    patch.object(tools, 'release_identity', return_value=self.identity), \
                    patch.object(tools, 'distribute_external') as distribute, \
                    patch.object(tools, 'export_release') as export, \
                    patch('logistics_build.build_retention.clean_builds'), \
                    patch('sys.argv', ['testflight_tools', 'distribute', '--build-number', '123',
                                       '--workspace', str(workspace)]):
                tools.main()
                distribute.assert_called_once_with(workspace.resolve())
                export.assert_not_called()
                uploaded.write_text(json.dumps(dict(status='uploaded', build=dict(build, build_number='999'))))
                with self.assertRaisesRegex(ValueError, 'identity/build'):
                    tools.main()
                self.assertEqual(distribute.call_count, 1)

    def test_xcode_uses_saved_api_key_and_rejects_partial_environment_override(self):
        from mobile_build.deployment.testflight_tools import auth_args
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            key = Path(directory) / 'key.p8'; key.touch()
            saved = dict(key_path=str(key), key_id='ABCDEFGHIJ', issuer_id='issuer')
            with patch.dict('os.environ', {}, clear=True), patch('mobile_build.deployment.testflight_tools.EXTERNAL_AUTH') as local, \
                    patch('mobile_build.deployment.testflight_tools.external_credentials', return_value=saved):
                local.exists.return_value = True
                self.assertEqual(auth_args(), ['-authenticationKeyPath', str(key), '-authenticationKeyID',
                                               'ABCDEFGHIJ', '-authenticationKeyIssuerID', 'issuer'])
                local.exists.return_value = False
                self.assertEqual(auth_args(), [])
                with patch.dict('os.environ', {'ASC_KEY_ID': 'ABCDEFGHIJ'}):
                    with self.assertRaisesRegex(ValueError, 'Set all'):
                        auth_args()

    def test_release_never_defaults_to_upload_or_renumbers_the_build(self):
        options = export_options('ABCDEFGHIJ')
        self.assertEqual(options['destination'], 'export')
        self.assertEqual(options['method'], 'app-store-connect')
        self.assertFalse(options['manageAppVersionAndBuildNumber'])
        self.assertEqual(export_options('ABCDEFGHIJ', {'UUID': 'profile'})['provisioningProfiles'], {BUNDLE: 'profile'})
        self.assertEqual(export_options('ABCDEFGHIJ', upload=True)['destination'], 'upload')
        paired = export_options('ABCDEFGHIJ', {'UUID':'main'}, inbox_profile={'UUID':'inbox'})
        self.assertEqual(paired['provisioningProfiles'], {BUNDLE:'main', BUNDLE + '.inbox':'inbox'})
        with self.assertRaises(ValueError):
            export_options('ABCDEFGHIJ', inbox_profile={'UUID':'inbox'})

    def test_retained_manual_export_keeps_all_extension_profile_mappings(self):
        import json
        import plistlib
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from mobile_build.deployment import testflight_tools as tools
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            extensions = {'.inbox': 'inbox', '.widgets': 'widgets', '.widget-actions': 'actions',
                          '.watchkitapp': 'watch', '.watchkitapp.widgets': 'watch-widget'}
            record = dict(identity=self.identity, build={'signed': True, 'build_number': '123'},
                          profile_uuid='main', extension_profile_uuids=extensions)
            (workspace / 'release.json').write_text(json.dumps(record))
            with patch.object(tools, 'release_identity', return_value=self.identity), \
                    patch.object(tools, 'inspect_app'), patch.object(tools, 'auth_args', return_value=[]), \
                    patch.object(tools, 'run', side_effect=RuntimeError('stop before external tools')):
                with self.assertRaisesRegex(RuntimeError, 'stop before external tools'):
                    tools.export_release(workspace, {})
            options = plistlib.loads((workspace / 'ExportOptions.plist').read_bytes())
            self.assertEqual(options['provisioningProfiles'],
                {BUNDLE: 'main', **{BUNDLE + suffix: uuid for suffix, uuid in extensions.items()}})

    def test_baseline_rejects_changed_team_bundle_or_prefix(self):
        baseline = dict(bundle_id=BUNDLE, team_id='ABCDEFGHIJ', signing_identity=self.identity)
        with patch('mobile_build.deployment.testflight_tools.CONFIG') as config:
            config.exists.return_value = True
            import json
            config.read_text.return_value = json.dumps(baseline)
            self.assertEqual(release_identity(), self.identity)
            with self.assertRaises(ValueError):
                release_identity('OTHERTEAM1X', self.identity['application_identifier'])
            with self.assertRaises(ValueError):
                release_identity('ABCDEFGHIJ', 'OTHERTEAM1X.' + BUNDLE)
            with self.assertRaises(ValueError):
                release_identity('ABCDEFGHIJ', 'ABCDEFGHIJ.other.app')

    def test_default_keychain_access_can_be_explicit_but_not_changed(self):
        self.assertTrue(keychain_groups_match([], self.identity))
        self.assertTrue(keychain_groups_match([self.identity['application_identifier']], self.identity))
        self.assertFalse(keychain_groups_match(['different.group'], self.identity))
        self.assertFalse(keychain_groups_match([self.identity['application_identifier'], 'extra.group'], self.identity))

    def test_development_ad_hoc_wrong_identity_and_expired_profiles_rejected(self):
        profile = dict(TeamIdentifier=['ABCDEFGHIJ'], ExpirationDate=datetime.now() + timedelta(days=5),
                       Entitlements={'application-identifier': self.identity['application_identifier'],
                                     'get-task-allow': False, 'beta-reports-active': True})
        validate_profile(profile, self.identity)
        validate_profile(dict(profile, Entitlements=dict(profile['Entitlements'],
                         **{'keychain-access-groups': ['ABCDEFGHIJ.*']})), self.identity)
        for changes in ({'ProvisionedDevices': ['phone']}, {'ProvisionsAllDevices': True},
                        {'TeamIdentifier': ['OTHERTEAM1X']}, {'ExpirationDate': datetime.now() - timedelta(days=1)},
                        {'Entitlements': dict(profile['Entitlements'], **{'get-task-allow': True})},
                        {'Entitlements': dict(profile['Entitlements'], **{'keychain-access-groups': ['other.group']})}):
            with self.assertRaises(ValueError):
                validate_profile(dict(profile, **changes), self.identity)

    def test_build_numbers_are_positive_and_explicit(self):
        self.assertEqual(build_number('202610131'), '202610131')
        for invalid in ('0', '-1', '01', '1.0', '1234567890', 'upload'):
            with self.assertRaises(ValueError):
                build_number(invalid)

    def test_unsigned_archive_cannot_export_or_upload(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory, patch('mobile_build.deployment.testflight_tools.run') as run:
            workspace = Path(directory)
            for dirty, signed in ((False, False), (True, False)):
                (workspace / 'release.json').write_text(json.dumps({'source': {'dirty': dirty}, 'build': {'signed': signed}}))
                for upload in (False, True):
                    with self.assertRaises(ValueError):
                        export_release(workspace, {}, upload=upload)
            run.assert_not_called()

    def test_upload_requires_reviewed_export_explicit_opt_in_and_unchanged_artifacts(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from hashlib import sha256
        from mobile_build.deployment.testflight_tools import archive_fingerprint

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            app = workspace / 'Logistics.xcarchive/Products/Applications/Logistics Mobile.app'
            app.mkdir(parents=True)
            executable = app / 'LogisticsMobile'
            executable.write_bytes(b'archived executable')
            (workspace / 'export').mkdir()
            ipa = workspace / 'export/Logistics.ipa'
            ipa.write_bytes(b'reviewed ipa')
            record = dict(identity=self.identity, source={'dirty': True},
                          build={'signed': True, 'build_number': '202610144'}, profile_uuid=None)
            (workspace / 'release.json').write_text(json.dumps(record))
            verified = dict(archive_sha256=archive_fingerprint(app),
                            ipa_sha256=sha256(ipa.read_bytes()).hexdigest())
            with patch('mobile_build.deployment.testflight_tools.release_identity', return_value=self.identity), \
                    patch('mobile_build.deployment.testflight_tools.inspect_app'), \
                    patch('mobile_build.deployment.testflight_tools.auth_args', return_value=[]), \
                    patch('mobile_build.deployment.testflight_tools.prepare_external', return_value=None) as prepare, \
                    patch('mobile_build.deployment.testflight_tools.run') as run, \
                    patch.dict('os.environ', {'TESTFLIGHT_UPLOAD': ''}):
                with self.assertRaisesRegex(ValueError, 'Export and verify'):
                    export_release(workspace, {}, upload=True)
                (workspace / 'export-verified.json').write_text(json.dumps(verified))
                with self.assertRaisesRegex(ValueError, 'Uploading is explicit'):
                    export_release(workspace, {}, upload=True)
                with patch.dict('os.environ', {'TESTFLIGHT_UPLOAD': '1'}):
                    executable.write_bytes(b'changed executable')
                    with self.assertRaisesRegex(ValueError, 'has changed'):
                        export_release(workspace, {}, upload=True)
                    executable.write_bytes(b'archived executable')
                    ipa.write_bytes(b'changed ipa')
                    with self.assertRaisesRegex(ValueError, 'has changed'):
                        export_release(workspace, {}, upload=True)
                    run.assert_not_called()
                    ipa.write_bytes(b'reviewed ipa')
                    export_release(workspace, {}, upload=True)
                    run.assert_called_once()
                    import plistlib
                    options = plistlib.loads((workspace / 'UploadOptions.plist').read_bytes())
                    self.assertEqual(options['destination'], 'upload')
                    self.assertFalse(options['manageAppVersionAndBuildNumber'])
                    run.reset_mock()
                    prepare.side_effect = ValueError('Missing API key')
                    with self.assertRaisesRegex(ValueError, 'Missing API key'):
                        export_release(workspace, {}, upload=True)
                    run.assert_not_called()
                    prepare.side_effect = None
                    prepared = object()
                    prepare.return_value = prepared
                    events = []
                    run.side_effect = lambda *a, **kw: events.append('upload')
                    with patch('mobile_build.deployment.testflight_tools.distribute_external',
                               side_effect=lambda *a: events.append('distribute')) as distribute:
                        export_release(workspace, {}, upload=True)
                        distribute.assert_called_once_with(workspace, prepared)
                    self.assertEqual(events, ['upload', 'distribute'])
                    run.reset_mock()
                    run.side_effect = RuntimeError('Upload failed')
                    with patch('mobile_build.deployment.testflight_tools.distribute_external') as distribute:
                        with self.assertRaisesRegex(RuntimeError, 'Upload failed'):
                            export_release(workspace, {}, upload=True)
                        distribute.assert_not_called()
