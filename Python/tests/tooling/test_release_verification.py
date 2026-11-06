"""Actual ZIP bytes prove published source/dependency and digest checks."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import hashlib
from io import BytesIO
import json
from threading import Event
import unittest
from unittest.mock import patch
import zipfile

from logistics_build.release_verification import verify_asset


class ReleaseVerificationTests(unittest.TestCase):
    def asset(self, *, dependency='shared', corrupt=False, tag='v1.2.3-alpha.4', members=None,
              corrupt_member=None):
        stream=BytesIO()
        version=json.dumps(dict(revision='commit',tag=tag)).encode()
        members = {'.app-version.json': version, **(members or {})}
        manifest=dict(revision='commit', commonUtils_revision=dependency,
                      files={name: hashlib.sha256(content).hexdigest() for name, content in members.items()})
        if corrupt_member:
            manifest['files'][corrupt_member] = '0' * 64
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in members.items():
                archive.writestr('Logistics/'+name,content)
            archive.writestr('Logistics/.app-install.json',json.dumps(manifest))
        data=stream.getvalue()
        return dict(browser_download_url='https://example.invalid/release.zip',
                    digest='sha256:'+('0'*64 if corrupt else hashlib.sha256(data).hexdigest())), data

    def test_downloaded_zip_must_match_digest_source_and_shared_pin(self):
        asset,data=self.asset()
        result=verify_asset(asset,'commit','shared',Event(),opener=lambda *a,**k:BytesIO(data))
        self.assertEqual(result['sha256'],hashlib.sha256(data).hexdigest())
        for options, message in [({'corrupt':True},'SHA-256'),({'dependency':'wrong'},'dependency')]:
            asset,data=self.asset(**options)
            with self.assertRaisesRegex(ValueError,message):
                verify_asset(asset,'commit','shared',Event(),opener=lambda *a,**k:BytesIO(data))

    def test_same_source_under_wrong_release_tag_is_rejected(self):
        asset,data=self.asset()
        verify_asset(asset,'commit','shared',Event(),tag='v1.2.3-alpha.4',opener=lambda *a,**k:BytesIO(data))
        with self.assertRaisesRegex(ValueError,'release tag'):
            verify_asset(asset,'commit','shared',Event(),tag='v1.2.3-beta.1',opener=lambda *a,**k:BytesIO(data))

    def test_large_compressed_member_is_hashed_in_bounded_reads(self):
        asset, data = self.asset(members={'large.bin': b'payload' * 600000})
        original_read = zipfile.ZipExtFile.read
        reads = []
        def read(member, count=-1):
            if member.name == 'Logistics/large.bin':
                self.assertGreater(count, 0)
                self.assertLessEqual(count, 1024 * 1024)
                reads.append(count)
            return original_read(member, count)
        with patch.object(zipfile.ZipExtFile, 'read', read):
            result = verify_asset(asset, 'commit', 'shared', Event(), opener=lambda *a, **k: BytesIO(data))
        self.assertGreater(len(reads), 1)
        self.assertEqual(result['bytes'], len(data))
        self.assertEqual(result['sha256'], hashlib.sha256(data).hexdigest())

    def test_member_cancellation_stops_before_next_read_and_closes_stream(self):
        asset, data = self.asset(members={'large.bin': b'payload' * 600000})
        cancelled = Event()
        original_read = zipfile.ZipExtFile.read
        streams = []
        def read(member, count=-1):
            value = original_read(member, count)
            if member.name == 'Logistics/large.bin':
                streams.append(member)
                cancelled.set()
            return value
        with patch.object(zipfile.ZipExtFile, 'read', read):
            with self.assertRaisesRegex(RuntimeError, 'Public ZIP verification cancelled; no completion recorded'):
                verify_asset(asset, 'commit', 'shared', cancelled, opener=lambda *a, **k: BytesIO(data))
        self.assertEqual(len(streams), 1)
        self.assertTrue(streams[0].closed)

    def test_streamed_member_still_requires_manifest_digest_and_safe_path(self):
        for options, message in [
            ({'members': {'payload.bin': b'content'}, 'corrupt_member': 'payload.bin'}, 'differs from its manifest'),
            ({'members': {'../escape': b'content'}}, 'Invalid release manifest member'),
        ]:
            with self.subTest(options=options):
                asset, data = self.asset(**options)
                with self.assertRaisesRegex(ValueError, message):
                    verify_asset(asset, 'commit', 'shared', Event(), opener=lambda *a, **k: BytesIO(data))
