"""Collection forms retire private metadata on host navigation and suspension."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from mobile.app import LogisticsMobile
from features.comics.comicinfo import ComicInfoXML
from features.comics.mobile.metadata import batch_form
from features.comics.mobile.private_batch import PrivateCollectionBatch
from services.session_auth import ResumePassword


class CollectionPrivacyUITests(unittest.TestCase):
    def test_navigation_suspend_and_credentials_retire_private_forms_and_callbacks(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            try:
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            finally:
                LogisticsMobile.storage_root = None
            async def exercise():
                for retirement in ['navigate', 'suspend', 'credentials']:
                    doc = SimpleNamespace(info=ComicInfoXML.from_bytes(b'<ComicInfo><Writer>Private writer</Writer></ComicInfo>'))
                    valid = [True]
                    plan = PrivateCollectionBatch(valid=lambda: valid[0], open_reader=None, revision=None, publish=None)
                    plan.privacy_gate = ResumePassword('synthetic-session-password')
                    plan.documents = [doc]
                    async def save(changes):
                        self.fail('A retired form must not publish')
                    view = batch_form([doc], save=save, back=lambda w: None, cancel=lambda w: None,
                                      choices={'Writer': ['Private suggestion']}, width=300)
                    plan.view = view
                    app.private_comic_batch = plan
                    app.show_view(view, destination='files', route='private-comic-batch')
                    field = view.metadata_inputs['Writer']
                    stale_apply = view.metadata_apply
                    self.assertIn('Private writer', field.value)
                    self.assertTrue(app.screen_privacy.sensitive())
                    if retirement == 'navigate':
                        app.show_settings()
                    elif retirement == 'suspend':
                        app.release_disposable_resources()
                    else:
                        valid[0] = False
                        app.screen_privacy.retire_stale()
                    self.assertTrue(plan.closed)
                    self.assertEqual(field.value, '')
                    self.assertEqual(view.metadata_inputs, {})
                    self.assertEqual(plan.documents, [])
                    await stale_apply(None)
                    self.assertNotIn('Private writer', (app.private_root / 'workspace.json').read_text())
            try:
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()
