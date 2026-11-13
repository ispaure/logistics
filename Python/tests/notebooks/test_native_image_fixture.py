"""Public native fixture bytes, password/scene contents and real test-source staging."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from pypdf import PdfReader
from features.notebooks.notebook import Notebook
from features.notebooks.pdf_crypto import enable_aes
from .native_image_fixture import FIXTURE, PASSWORD, generate
from mobile_build.native_tests.tests.logisticsmobile.notebook_image_checks import IMAGE_FIXTURE_SHA256

TEST_STAGE = TestStage.REGRESSION


class NativeImageFixtureTests(unittest.TestCase):
    def test_regeneration_is_byte_exact_and_scoped_entropy_is_restored(self):
        import secrets
        original=secrets.token_bytes
        data=FIXTURE.read_bytes()
        self.assertEqual(generate(),data)
        self.assertEqual(generate(),data)
        self.assertIs(secrets.token_bytes,original)
        self.assertEqual(sha256(data).hexdigest(),IMAGE_FIXTURE_SHA256)
        self.assertEqual(len(data),2746)

    def test_public_aes256_fixture_rejects_wrong_password_and_preserves_native_scene(self):
        enable_aes()
        book=Notebook.read(FIXTURE.read_bytes())
        encrypted=book.members[book.id+'.pdf']
        reader=PdfReader(BytesIO(encrypted))
        self.assertTrue(reader.is_encrypted)
        self.assertEqual(int(reader.trailer['/Encrypt']['/V']),5)
        self.assertEqual(int(reader.trailer['/Encrypt']['/R']),6)
        self.assertEqual(int(reader.trailer['/Encrypt']['/Length']),256)
        self.assertFalse(reader.decrypt('wrong-password'))
        self.assertTrue(reader.decrypt(PASSWORD))
        self.assertEqual(reader.pages[0].get_contents().get_data(),b'.9 .3 .15 rg 0 0 420 560 re f')
        self.assertEqual(len(book.page(0).images),1)
        self.assertEqual(len(book.page(0).strokes),1)
        self.assertEqual(Notebook.read(book.to_bytes()).members[book.id+'.pdf'],encrypted)

    def test_normal_workspace_copies_fixture_through_declared_test_sources(self):
        from mobile_build.deployment.deployment_paths import prepare_workspace
        mobile=FIXTURE.parents[3]
        self.assertIn('test_sources = ["native_tests/tests"]',(mobile/'pyproject.toml').read_text())
        with TemporaryDirectory() as directory:
            target=Path(directory)/'owned-workspace'
            with patch('mobile_build.deployment.deployment_paths.output_root',return_value=target):
                prepare_workspace(mobile)
            staged=target/'native_tests/tests/logisticsmobile/notebook-image-fixture.rmdoc'
            self.assertEqual(staged.read_bytes(),FIXTURE.read_bytes())
