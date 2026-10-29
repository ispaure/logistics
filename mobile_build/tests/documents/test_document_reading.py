"""Reader session capabilities preserve privacy independently of encryption labels."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from commonUtils.runtime.resources.local import LocalFiles
from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
from features.rclone.mobile.remote_readers import RemoteReaders
from services.documents.mobile_reading import (
    DocumentReadCapabilities, reading_capabilities, close_document_reader,
)
from services.documents.mobile_storage import TextDocumentCopies


class DocumentReadingTests(unittest.TestCase):
    def test_remote_declaration_alone_enforces_private_credential_bound_readonly_access(self):
        source = NS(document_capabilities=DocumentReadCapabilities(
            private=False, writable=True, credential_bound=False, offline=False, remote=True))
        self.assertEqual(reading_capabilities(source), DocumentReadCapabilities(
            private=True, writable=False, credential_bound=True, offline=False, remote=True))

    def test_private_session_does_not_imply_a_credential_dependency(self):
        source = NS(document_capabilities=DocumentReadCapabilities(
            private=True, writable=False, credential_bound=False, offline=True))
        self.assertTrue(reading_capabilities(source).private)
        self.assertFalse(reading_capabilities(source).credential_bound)

    def test_ordinary_text_remains_available_without_credentials(self):
        with TemporaryDirectory() as folder:
            copies = TextDocumentCopies(LocalFiles(Path(folder)))
            self.assertEqual(reading_capabilities(copies), DocumentReadCapabilities(
                private=False, writable=True, credential_bound=False, offline=True))

    def test_encryption_flag_cannot_determine_remote_lifetime_or_writes(self):
        source = NS(document_capabilities=RemoteReaders.document_capabilities,
                    encrypted=False, remote_storage=True)
        capabilities = reading_capabilities(source)
        self.assertTrue(capabilities.private)
        self.assertTrue(capabilities.credential_bound)
        self.assertTrue(capabilities.remote)
        self.assertFalse(capabilities.writable)
        self.assertFalse(capabilities.offline)

    def test_localcrypt_declares_offline_access_without_persistent_plaintext(self):
        source = NS(document_capabilities=LocalCryptCopies.document_capabilities)
        self.assertEqual(reading_capabilities(source), DocumentReadCapabilities(
            private=True, writable=True, credential_bound=True, offline=True, required_feature='rclone'))

    def test_adapter_declaration_cannot_hide_wrapped_remote_policy(self):
        with TemporaryDirectory() as folder:
            provider = LocalFiles(Path(folder))
            provider.remote_storage = True
            source = NS(provider=provider, document_capabilities=DocumentReadCapabilities(
                private=False, writable=True, credential_bound=False, offline=False))
            capabilities = reading_capabilities(source)
            self.assertTrue(capabilities.private)
            self.assertTrue(capabilities.credential_bound)
            self.assertFalse(capabilities.writable)
            self.assertTrue(capabilities.remote)

    def test_password_is_retired_even_when_source_close_fails(self):
        reader = NS(pdf=Mock(), source=NS(close=Mock(side_effect=OSError('close failed'))), password='secret')
        with self.assertRaisesRegex(OSError, 'close failed'):
            close_document_reader(reader)
        reader.pdf.close.assert_called_once_with()
        self.assertEqual(reader.password, '')
