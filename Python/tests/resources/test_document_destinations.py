"""Captured destinations preserve conflict and publication outcomes without UI."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.operations import MutationIncomplete
from services.documents.destinations import DestinationRequest


class DestinationRequestTests(unittest.TestCase):
    def test_resource_delete_refuses_changed_revision_before_removing_source(self):
        from services.documents.storage import DocumentResource
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'example.txt'
            path.write_bytes(b'original')
            with DocumentResource(LocalFiles(Path(folder)), path.name, max_bytes=32) as resource:
                resource.read()
                path.write_bytes(b'changed elsewhere')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    resource.delete()
                self.assertTrue(path.exists())
                resource.read()
                resource.delete()
                self.assertFalse(path.exists())

    def request(self, provider, *, creating=False, data=b'captured draft'):
        return DestinationRequest.capture(provider, '', 'example.txt', data, ('.txt',),
            notebook=False, creating=creating, session_count=0, session_limit=32,
            store=Mock(), source_document=None)

    def test_request_captures_bytes_and_duplicate_creation_never_replaces(self):
        with TemporaryDirectory() as folder:
            provider = LocalFiles(Path(folder))
            data = bytearray(b'captured draft')
            request = self.request(provider, creating=True, data=data)
            data[:] = b'edited later'
            destination, revision = request.resolve(cancelled=lambda: False)
            outcome = request.publish(destination, revision, cancelled=lambda: False)
            self.assertEqual(outcome.status, 'published')
            self.assertEqual((Path(folder) / 'example.txt').read_bytes(), b'captured draft')
            with self.assertRaises(FileExistsError):
                request.resolve(cancelled=lambda: False)

    def test_conflict_preserves_external_change_and_reports_unchanged(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'example.txt'
            target.write_bytes(b'original')
            request = self.request(LocalFiles(Path(folder)))
            destination, revision = request.resolve(cancelled=lambda: False)
            target.write_bytes(b'external change')
            outcome = request.publish(destination, revision, cancelled=lambda: False)
            self.assertEqual(outcome.status, 'unchanged')
            self.assertEqual(target.read_bytes(), b'external change')
            with self.assertRaises(Exception):
                outcome.require_reopened()

    def test_failed_reopen_distinguishes_published_bytes_and_retains_error(self):
        with TemporaryDirectory() as folder:
            request = self.request(LocalFiles(Path(folder)))
            destination, revision = request.resolve(cancelled=lambda: False)
            with patch('services.documents.mobile_storage.document_copies') as copies:
                copies.return_value.open.side_effect = ValueError('reader refused saved file')
                outcome = request.publish(destination, revision, cancelled=lambda: False)
            self.assertEqual(outcome.status, 'published-not-reopened')
            self.assertEqual((Path(folder) / 'example.txt').read_bytes(), request.data)
            with self.assertRaises(MutationIncomplete) as caught:
                outcome.require_reopened()
            self.assertIn('reader refused', str(caught.exception.__cause__))

    def test_cancelled_publication_leaves_no_file(self):
        with TemporaryDirectory() as folder:
            request = self.request(LocalFiles(Path(folder)))
            destination, revision = request.resolve(cancelled=lambda: False)
            outcome = request.publish(destination, revision, cancelled=lambda: True)
            self.assertEqual(outcome.status, 'unchanged')
            self.assertFalse((Path(folder) / 'example.txt').exists())
