
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from mobile_build.deployment import testflight_external as external


class ExternalDistributionTests(unittest.TestCase):
    config = dict(enabled=True, app_id='6822787800', bundle_id=external.BUNDLE,
                  external_group='Friends', locale='en-US', what_to_test='Try document editing.',
                  processing_timeout_seconds=60, poll_interval_seconds=30)
    group = dict(id='group', attributes={'name': 'Friends', 'isInternalGroup': False})

    def test_configure_saves_private_local_reference_without_key_contents(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / 'key.p8'
            key.write_text('private material never copied into settings')
            auth = root / 'auth.json'
            args = ['testflight_external.py', 'configure', '--key-path', str(key), '--key-id', 'ABCDEFGHIJ',
                    '--issuer-id', '11111111-1111-1111-1111-111111111111']
            with patch.object(external, 'AUTH', auth), patch.object(external, 'token'), patch('sys.argv', args):
                external.main()
            self.assertEqual(auth.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(auth.read_text())['key_path'], str(key.resolve()))
            self.assertNotIn('private material', auth.read_text())

    def client(self, state='READY_FOR_BETA_SUBMISSION', *, linked=False):
        client = Mock()
        def request(method, path, **kwargs):
            if path.endswith('/buildBetaDetail'):
                return {'data': {'id': 'detail', 'attributes': {'externalBuildState': state}}}
            if path == '/v1/apps/6822787800':
                return {'data': {'id': '6822787800', 'attributes': {'bundleId': external.BUNDLE}}}
            return {}
        client.request.side_effect = request
        links = [[{'id': 'build', 'type': 'builds'}]] * 2 if linked else [[], [{'id': 'build', 'type': 'builds'}]]
        def listing(path, **kwargs):
            if path.endswith('/betaBuildLocalizations'):
                return []
            if path.endswith('/relationships/builds'):
                return links.pop(0)
            if path.endswith('/betaGroups'):
                return [self.group]
            return [{'id': 'build', 'attributes': {'processingState': 'VALID'}}]
        client.list.side_effect = listing
        return client

    def workspace(self, directory):
        path = Path(directory)
        (path / 'release.json').write_text(json.dumps({'identity': {'bundle_id': external.BUNDLE},
            'build': {'version': '0.1.5', 'build_number': '202610144'}}))
        return path

    def test_signed_jwt_has_valid_es256_signature_and_short_lifetime(self):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        with TemporaryDirectory() as directory:
            key = ec.generate_private_key(ec.SECP256R1())
            path = Path(directory) / 'key.p8'
            path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
            auth = dict(key_path=str(path), key_id='ABCDEFGHIJ', issuer_id='11111111-1111-1111-1111-111111111111')
            result = external.token(auth, now=1000)
            h, p, s = result.split('.')
            decode = lambda value: base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
            self.assertEqual(json.loads(decode(h)), {'alg': 'ES256', 'kid': 'ABCDEFGHIJ', 'typ': 'JWT'})
            claims = json.loads(decode(p))
            self.assertEqual(claims['aud'], 'appstoreconnect-v1')
            self.assertEqual(claims['iss'], auth['issuer_id'])
            self.assertLessEqual(claims['exp'] - claims['iat'], 1200)
            raw = decode(s)
            signature = utils.encode_dss_signature(int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big'))
            key.public_key().verify(signature, (h + '.' + p).encode(), ec.ECDSA(hashes.SHA256()))
            with self.assertRaises(Exception):
                key.public_key().verify(signature, (h + '.tampered').encode(), ec.ECDSA(hashes.SHA256()))

    def test_target_rejects_other_app_internal_missing_and_ambiguous_group(self):
        client = self.client()
        self.assertEqual(external.target(client, self.config)['id'], 'group')
        for groups in [[], [dict(self.group, attributes={'name': 'Friends', 'isInternalGroup': True})],
                       [self.group, self.group]]:
            client.list.side_effect = None
            client.list.return_value = groups
            with self.assertRaises(ValueError):
                external.target(client, self.config)
        client.request.side_effect = None
        client.request.return_value = {'data': {'attributes': {'bundleId': 'other.app'}}}
        with self.assertRaisesRegex(ValueError, 'different bundle'):
            external.target(client, self.config)

    def test_wait_selects_exact_version_platform_and_number_and_times_out(self):
        client = Mock()
        client.list.side_effect = [[], [{'id': 'build', 'attributes': {'processingState': 'PROCESSING'}}],
                                  [{'id': 'build', 'attributes': {'processingState': 'VALID'}}]]
        sleep = Mock()
        self.assertEqual(external.wait_for_build(client, self.config, '144', '0.1.5', sleep=sleep,
                         clock=Mock(side_effect=[0, 0, 30]))['id'], 'build')
        filters = client.list.call_args.kwargs
        self.assertEqual(filters['filter[version]'], '144')
        self.assertEqual(filters['filter[preReleaseVersion.version]'], '0.1.5')
        self.assertEqual(filters['filter[preReleaseVersion.platform]'], 'IOS')
        client.list.side_effect = None
        client.list.return_value = []
        with self.assertRaisesRegex(RuntimeError, 'do not re-upload'):
            external.wait_for_build(client, self.config, '144', '0.1.5', sleep=sleep,
                                    clock=Mock(side_effect=[0, 61]))

    def test_failed_expired_internal_only_and_ambiguous_builds_rejected(self):
        for builds in [[{'attributes': {'processingState': 'FAILED'}}],
                       [{'attributes': {'processingState': 'VALID', 'expired': True}}],
                       [{'attributes': {'processingState': 'VALID', 'buildAudienceType': 'INTERNAL_ONLY'}}],
                       [{'id': 'a'}, {'id': 'b'}]]:
            client = Mock(); client.list.return_value = builds
            with self.assertRaises(ValueError):
                external.wait_for_build(client, self.config, '144', '0.1.5')

    def test_distribution_submits_review_enables_notification_and_adds_without_replacing(self):
        with TemporaryDirectory() as directory:
            workspace = self.workspace(directory)
            client = self.client()
            external.distribute(workspace, (client, self.config, self.group))
            writes = [(c.args, c.kwargs) for c in client.request.call_args_list if c.args[0] != 'GET']
            self.assertTrue(any(args == ('POST', '/v1/betaAppReviewSubmissions') for args, kw in writes))
            notification = next(kw['body'] for args, kw in writes if args[1] == '/v1/buildBetaDetails/detail')
            self.assertEqual(notification['data']['attributes'], {'autoNotifyEnabled': True})
            relationship = next(kw['body'] for args, kw in writes if args[1].endswith('/relationships/builds'))
            self.assertEqual(relationship, {'data': [{'type': 'builds', 'id': 'build'}]})
            self.assertFalse(any(args[0] in {'DELETE', 'PUT'} for args, kw in writes))
            self.assertEqual(json.loads((workspace / 'external-distribution.json').read_text())['status'], 'assigned')

    def test_known_review_conflict_keeps_confirmed_group_and_reports_deferred_review(self):
        with TemporaryDirectory() as directory:
            workspace = self.workspace(directory)
            client = self.client()
            original = client.request.side_effect
            def request(method, path, **kwargs):
                if path == '/v1/betaAppReviewSubmissions':
                    saved = json.loads((workspace / 'external-distribution.json').read_text())
                    self.assertTrue(saved['group_assignment_confirmed'])
                    raise RuntimeError('App Store Connect HTTP 422: Another build in the same train is already in beta review. '
                                       'Please submit it again once it gets completed.')
                return original(method, path, **kwargs)
            client.request.side_effect = request
            external.distribute(workspace, (client, self.config, self.group))
            report = json.loads((workspace / 'external-distribution.json').read_text())
            self.assertEqual(report['status'], 'assigned')
            self.assertEqual(report['review_status'], 'blocked_by_existing_review')
            self.assertFalse(report['review_submitted'])
            self.assertTrue(report['group_assignment_confirmed'])
            writes = [c.args for c in client.request.call_args_list if c.args[0] == 'POST']
            self.assertLess(writes.index(('POST', '/v1/betaGroups/group/relationships/builds')),
                            writes.index(('POST', '/v1/betaAppReviewSubmissions')))

    def test_other_review_errors_still_fail_with_confirmed_group_receipt(self):
        for message in ['App Store Connect HTTP 422: Invalid review information',
                        'App Store Connect HTTP 401: Unauthorized', 'Outcome unknown; reconcile first']:
            with self.subTest(message=message), TemporaryDirectory() as directory:
                workspace = self.workspace(directory)
                client = self.client()
                original = client.request.side_effect
                def request(method, path, **kwargs):
                    if path == '/v1/betaAppReviewSubmissions':
                        raise RuntimeError(message)
                    return original(method, path, **kwargs)
                client.request.side_effect = request
                with self.assertRaisesRegex(RuntimeError, message):
                    external.distribute(workspace, (client, self.config, self.group))
                report = json.loads((workspace / 'external-distribution.json').read_text())
                self.assertEqual(report['status'], 'needs_attention')
                self.assertTrue(report['group_assignment_confirmed'])
                self.assertFalse(report['review_submitted'])

    def test_retries_do_not_resubmit_review_relink_or_overwrite_existing_notes(self):
        for state in ['WAITING_FOR_BETA_REVIEW', 'IN_BETA_REVIEW', 'BETA_APPROVED', 'IN_BETA_TESTING']:
            with TemporaryDirectory() as directory:
                client = self.client(state, linked=True)
                original_listing = client.list.side_effect
                client.list.side_effect = lambda path, **kw: ([{'id': 'notes', 'attributes': {
                    'locale': 'en-US', 'whatsNew': 'Owner notes'}}] if path.endswith('/betaBuildLocalizations')
                    else original_listing(path, **kw))
                external.distribute(self.workspace(directory), (client, self.config, self.group))
                self.assertEqual([c.args[0] for c in client.request.call_args_list], ['GET', 'PATCH'])

    def test_compliance_rejection_and_unknown_states_stop_before_mutation(self):
        for state in ['MISSING_EXPORT_COMPLIANCE', 'IN_EXPORT_COMPLIANCE_REVIEW', 'BETA_REJECTED', 'NOT_APPLICABLE', 'UNKNOWN']:
            with TemporaryDirectory() as directory:
                client = self.client(state)
                path = self.workspace(directory)
                with self.assertRaisesRegex(ValueError, state):
                    external.distribute(path, (client, self.config, self.group))
                self.assertEqual([c.args[0] for c in client.request.call_args_list], ['GET'])
                self.assertEqual(json.loads((path / 'external-distribution.json').read_text())['status'], 'needs_attention')

    def test_unconfirmed_relationship_is_reported_as_failure(self):
        with TemporaryDirectory() as directory:
            client = self.client('BETA_APPROVED')
            original = client.list.side_effect
            client.list.side_effect = lambda path, **kw: [] if path.endswith('/relationships/builds') else original(path, **kw)
            with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
                external.distribute(self.workspace(directory), (client, self.config, self.group))

    def test_api_rejects_foreign_pagination_urls_before_authorization(self):
        client = object.__new__(external.Client)
        with self.assertRaises(ValueError):
            client.request('GET', 'https://example.com/v1/apps')
        with self.assertRaises(ValueError):
            client.request('GET', 'https://api.appstoreconnect.apple.com@evil.example/v1/apps')


if __name__ == '__main__':
    unittest.main()
