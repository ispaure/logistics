"""Actual ZIP bytes prove published source/dependency and digest checks."""
import hashlib
from io import BytesIO
import json
from threading import Event
import unittest
import zipfile

from logistics_build.release_verification import verify_asset


class ReleaseVerificationTests(unittest.TestCase):
    def asset(self, *, dependency='shared', corrupt=False, tag='v1.2.3-alpha.4'):
        stream=BytesIO()
        version=json.dumps(dict(revision='commit',tag=tag)).encode()
        manifest=dict(revision='commit', commonUtils_revision=dependency,
                      files={'.app-version.json':hashlib.sha256(version).hexdigest()})
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('Logistics/.app-version.json',version)
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
