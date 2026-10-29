"""Document baselines, failure preservation and provider policy across formats."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from contextlib import contextmanager
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.provider import ResourceCapabilities
from services.documents.storage import DocumentPolicy, DocumentResource


class DocumentStorageTests(unittest.TestCase):
    def test_save_reopens_after_replacement_metadata_is_refreshed_by_first_open(self):
        class CachedReplacement(LocalFiles):
            stale = None

            def replace_created(self, staged, path, expected_revision):
                before = super().entry(path)
                super().replace_created(staged, path, expected_revision)
                self.stale = before

            def entry(self, path):
                if self.stale is not None and path == 'document.bin':
                    return self.stale
                return super().entry(path)

            @contextmanager
            def open(self, path):
                with super().open(path) as stream:
                    if path == 'document.bin':
                        self.stale = None
                    yield stream

        provider = CachedReplacement(self.root)
        with DocumentResource(provider, 'document.bin', max_bytes=32) as resource:
            self.assertEqual(resource.read(), b'original')
            for data in (b'first replacement', b'second replacement'):
                resource.save(data)
                self.assertEqual(resource.read(), data)
                self.assertEqual(resource.revision, provider.entry('document.bin')['revision'])

    def test_reopen_retry_still_rejects_external_bytes_and_retains_old_baseline(self):
        from commonUtils.runtime.operations import MutationIncomplete
        resource = self.resource()
        resource.read()
        baseline = resource.revision
        original_open = self.provider.open
        changed = False

        @contextmanager
        def external_change(path):
            nonlocal changed
            with original_open(path) as stream:
                yield stream
            if path == 'document.bin' and not changed:
                changed = True
                (self.root / path).write_bytes(b'external writer')

        with patch.object(self.provider, 'open', external_change):
            with self.assertRaises(MutationIncomplete) as caught:
                resource.save(b'my new bytes')
        self.assertTrue(caught.exception.result.destination_published)
        self.assertEqual(resource.revision, baseline)
        self.assertEqual((self.root / 'document.bin').read_bytes(), b'external writer')

    def test_ordinary_read_still_rejects_a_revision_change(self):
        resource = self.resource()
        original_open = self.provider.open

        @contextmanager
        def external_change(path):
            with original_open(path) as stream:
                yield stream
            (self.root / path).write_bytes(b'external writer')

        with patch.object(self.provider, 'open', external_change):
            with self.assertRaisesRegex(ValueError, 'changed while opening'):
                resource.read()
        self.assertIsNone(resource.revision)

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.provider = LocalFiles(self.root)
        (self.root / 'document.bin').write_bytes(b'original')

    def resource(self):
        resource = DocumentResource(self.provider, 'document.bin', max_bytes=32)
        self.addCleanup(resource.close)
        return resource

    def test_save_retains_revision_conflicts_and_advances_successful_baseline(self):
        resource = self.resource()
        self.assertEqual(resource.read(), b'original')
        resource.save(b'first')
        resource.save(b'second')
        (self.root / 'document.bin').write_bytes(b'external')
        with self.assertRaisesRegex(ValueError, 'changed'):
            resource.save(b'overwrite')
        self.assertEqual((self.root / 'document.bin').read_bytes(), b'external')

    def test_cancel_and_invalid_format_leave_original_and_no_staging(self):
        resource = self.resource()
        resource.read()
        for kwargs in ({'cancelled': lambda: True}, {'validate': lambda data: (_ for _ in ()).throw(ValueError('invalid format'))}):
            with self.subTest(kwargs=kwargs), self.assertRaises(Exception):
                resource.save(b'new', **kwargs)
            self.assertEqual((self.root / 'document.bin').read_bytes(), b'original')
            self.assertEqual(list(self.root.iterdir()), [self.root / 'document.bin'])

    def test_failed_publication_retains_original_and_baseline(self):
        resource = self.resource()
        resource.read()
        baseline = resource.revision
        with patch.object(self.provider, 'replace_created', side_effect=OSError('full disk')):
            with self.assertRaisesRegex(OSError, 'full disk'):
                resource.save(b'new')
        self.assertEqual(resource.revision, baseline)
        self.assertEqual((self.root / 'document.bin').read_bytes(), b'original')
        self.assertEqual(list(self.root.iterdir()), [self.root / 'document.bin'])

    def test_create_never_replaces_and_format_bounds_apply_before_publication(self):
        with self.assertRaises(FileExistsError):
            DocumentResource.publish(self.provider, 'document.bin', b'new', max_bytes=32)
        with self.assertRaisesRegex(ValueError, 'size limit'):
            DocumentResource.publish(self.provider, 'large.bin', b'x' * 33, max_bytes=32)
        self.assertFalse((self.root / 'large.bin').exists())

    def test_remote_policy_remains_readonly_even_with_mutating_methods(self):
        self.provider.remote_storage = True
        self.provider.capabilities = ResourceCapabilities(True, True, True, True)
        resource = self.resource()
        self.assertFalse(resource.policy.persistent)
        self.assertFalse(resource.policy.writable)
        resource.read()
        with self.assertRaisesRegex(PermissionError, 'read-only'):
            resource.save(b'new')
        with self.assertRaises(PermissionError):
            DocumentResource.publish(self.provider, 'new.bin', b'new', max_bytes=32)
        self.assertEqual((self.root / 'document.bin').read_bytes(), b'original')

    def test_closed_and_oversize_reads_fail_without_advancing_baseline(self):
        resource = self.resource()
        (self.root / 'document.bin').write_bytes(b'x' * 33)
        with self.assertRaisesRegex(ValueError, 'size limit'):
            resource.read()
        self.assertIsNone(resource.revision)
        resource.close()
        resource.close()
        with self.assertRaisesRegex(ValueError, 'closed'):
            resource.read()

    def test_private_policy_requires_confirmation_only_when_publishing_plaintext(self):
        local = DocumentPolicy.for_provider(self.provider)
        self.provider.private = True
        private = DocumentPolicy.for_provider(self.provider)
        self.assertTrue(private.confirm_plaintext(local))
        self.assertFalse(local.confirm_plaintext(private))
        self.assertFalse(private.confirm_plaintext(private))
