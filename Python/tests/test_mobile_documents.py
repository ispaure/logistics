"""Portable mobile storage and scoped import contracts; no OS impersonation."""
from contextlib import contextmanager
import codecs
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.persistence.text import FileConflictError
from logisticsmobile.documents import DocumentStore, MAX_BYTES
from commonUtils.runtime.document_access import LocalDocuments, IOSDocuments, AndroidDocuments


class MobileDocumentsTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.store = DocumentStore(self.root / 'private')

    def test_unchanged_checkpoint_skips_serialization_and_disk_flushes(self):
        doc = self.store.create(content=b'original')
        with patch('logisticsmobile.documents.atomic_write_json') as write, \
                patch.object(type(doc.snapshot), 'encode', side_effect=AssertionError('Re-encoded unchanged text')):
            self.store.checkpoint(doc)
        write.assert_not_called()

    def test_changed_text_name_and_saved_baseline_are_checkpointed(self):
        from logisticsmobile.documents import atomic_write_json
        doc = self.store.create(content=b'original')
        with patch('logisticsmobile.documents.atomic_write_json', wraps=atomic_write_json) as write:
            doc.text = 'unsaved edits'
            self.store.checkpoint(doc)
            self.store.checkpoint(doc)
            self.assertEqual(write.call_count, 1)
            self.assertEqual(DocumentStore(self.store.root).open(doc.id).text, 'unsaved edits')
            doc.name = 'Renamed.md'
            self.store.checkpoint(doc)
            self.assertEqual(write.call_count, 2)
            self.store.save(doc)
            self.assertEqual(write.call_count, 3)
        recovered = DocumentStore(self.store.root).open(doc.id)
        self.assertEqual(recovered.name, 'Renamed.md')
        self.assertFalse(recovered.modified)

    def test_missing_edited_and_replaced_recovery_files_force_checkpoint(self):
        from logisticsmobile.documents import atomic_write_json
        doc = self.store.create(content=b'original')
        path = self.store.path(doc.id, '.json')
        for change in ('missing', 'edited', 'replaced'):
            with self.subTest(change=change):
                if change == 'missing':
                    path.unlink()
                elif change == 'edited':
                    path.write_text('{}')
                else:
                    replacement = path.with_suffix('.replacement')
                    replacement.write_bytes(path.read_bytes())
                    replacement.replace(path)
                with patch('logisticsmobile.documents.atomic_write_json', wraps=atomic_write_json) as write:
                    self.store.checkpoint(doc)
                write.assert_called_once()
                self.assertEqual(DocumentStore(self.store.root).open(doc.id).text, 'original')

    def test_cached_checkpoint_still_rejects_symbolic_link(self):
        doc = self.store.create(content=b'original')
        path = self.store.path(doc.id, '.json')
        outside = self.root / 'outside.json'
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.store.checkpoint(doc)

    def test_failed_durable_checkpoint_retries_even_after_file_publication(self):
        from logisticsmobile.documents import atomic_write_json
        doc = self.store.create(content=b'original')
        doc.text = 'unsaved edits'
        # Model a late durability failure after real publication. Windows has
        # no directory fsync, so inject at the writer's acknowledgement boundary.
        def fail_after_publication(*args, **kwargs):
            self.assertTrue(kwargs['durable_directory'])
            atomic_write_json(*args, **kwargs)
            self.assertEqual(json.loads(self.store.path(doc.id, '.json').read_text())['text'],
                             'unsaved edits')
            raise OSError('durability acknowledgement failed')
        with patch('logisticsmobile.documents.atomic_write_json', side_effect=fail_after_publication):
            with self.assertRaises(OSError):
                self.store.checkpoint(doc)
        with patch('logisticsmobile.documents.atomic_write_json', wraps=atomic_write_json) as write:
            self.store.checkpoint(doc)
            self.store.checkpoint(doc)
        write.assert_called_once()
        self.assertEqual(DocumentStore(self.store.root).open(doc.id).text, 'unsaved edits')

    def test_recovery_after_process_recreation_preserves_unsaved_text(self):
        doc = self.store.create('Notes.md', b'original\r\n')
        doc.text += 'recovered\n'
        self.store.checkpoint(doc)
        reopened = DocumentStore(self.store.root).open(doc.id)
        self.assertTrue(reopened.modified)
        self.assertEqual(reopened.text, 'original\nrecovered\n')
        self.assertEqual(reopened.snapshot.path.read_bytes(), b'original\r\n')
        self.store.save(reopened)
        self.assertEqual(reopened.snapshot.path.read_bytes(), b'original\r\nrecovered\r\n')
        self.assertFalse(self.store.open(doc.id).modified)

    def test_delete_removes_saved_bytes_and_unsaved_recovery_only_for_target(self):
        doc = self.store.create('Untitled.md')
        doc.text = '# Unsaved draft'
        self.store.checkpoint(doc)
        other = self.store.create('Keep.md', b'keep')
        self.store.delete(doc)
        self.assertFalse(self.store.path(doc.id, '.data').exists())
        self.assertFalse(self.store.path(doc.id, '.json').exists())
        self.assertEqual(self.store.open(other.id).text, 'keep')
        self.assertEqual(self.store.documents()[0][0].id, other.id)

    def test_failed_delete_keeps_recovery_and_never_follows_link(self):
        doc = self.store.create('Untitled.md')
        doc.text = 'Retain draft'
        self.store.checkpoint(doc)
        source = self.store.path(doc.id, '.data')
        source.unlink()
        outside = self.root / 'outside.md'
        outside.write_text('outside')
        source.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.store.delete(doc)
        self.assertTrue(self.store.path(doc.id, '.json').exists())
        self.assertEqual(outside.read_text(), 'outside')

    def test_private_creation_works_without_hard_links_and_hides_incomplete_records(self):
        with patch('logisticsmobile.documents.os.link', side_effect=PermissionError('sandbox forbids links')):
            doc = self.store.create(content=b'original')
            doc.text = 'copy'
            self.assertEqual(self.store.save_copy(doc).text, 'copy')
        existing = set(self.store.root.iterdir())
        with patch('logisticsmobile.documents.os.fsync', side_effect=OSError('flush failed')):
            with self.assertRaises(OSError):
                self.store.create(content=b'incomplete')
        self.assertEqual(set(self.store.root.iterdir()), existing)

    def test_bom_encoding_and_endings_survive_recovery_and_save(self):
        for prefix, encoding in ((codecs.BOM_UTF8, 'utf-8'), (codecs.BOM_UTF16_LE, 'utf-16-le')):
            original = prefix + 'Café\r\n'.encode(encoding)
            doc = self.store.create('Encoded.txt', original)
            doc.text += 'Saved\n'
            self.store.checkpoint(doc)
            recovered = self.store.open(doc.id)
            self.store.save(recovered)
            self.assertEqual(recovered.snapshot.path.read_bytes(),
                             prefix + 'Café\r\nSaved\r\n'.encode(encoding))

    def test_changed_or_deleted_private_file_preserves_draft_and_requires_copy(self):
        doc = self.store.create(content=b'original')
        doc.text = 'recover me'
        self.store.checkpoint(doc)
        for external in (b'changed', None):
            if external is None:
                doc.snapshot.path.unlink()
            else:
                doc.snapshot.path.write_bytes(external)
            recovered = self.store.open(doc.id)
            self.assertTrue(recovered.conflict)
            with self.assertRaises(FileConflictError):
                self.store.save(recovered)
            copy = self.store.save_copy(recovered, 'Recovered.txt')
            self.assertEqual(copy.snapshot.path.read_bytes(), b'recover me')
            self.assertEqual(self.store.open(doc.id).text, 'recover me')

    def test_failed_checkpoint_and_failed_save_keep_original_and_recovery(self):
        doc = self.store.create(content=b'before')
        doc.text = 'after'
        self.store.checkpoint(doc)
        before = self.store.path(doc.id, '.json').read_bytes()
        doc.text = 'latest unsaved edit'
        with patch('logisticsmobile.documents.atomic_write_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.checkpoint(doc)
        self.assertEqual(self.store.path(doc.id, '.json').read_bytes(), before)
        with patch('logisticsmobile.documents.write_text_file', side_effect=OSError('write failure')):
            with self.assertRaises(OSError):
                self.store.save(doc)
        self.assertEqual(doc.snapshot.path.read_bytes(), b'before')
        self.assertEqual(self.store.open(doc.id).text, 'after')

    def test_discard_preserves_external_change_and_deleted_source(self):
        doc = self.store.create(content=b'original')
        doc.text = 'draft'
        self.store.checkpoint(doc)
        doc.snapshot.path.write_bytes(codecs.BOM_UTF8 + b'external\r\n')
        self.store.discard(doc)
        self.assertEqual(doc.text, 'external\n')
        self.assertFalse(self.store.open(doc.id).modified)
        self.assertEqual(doc.snapshot.path.read_bytes(), codecs.BOM_UTF8 + b'external\r\n')
        doc.text = 'another draft'
        self.store.checkpoint(doc)
        doc.snapshot.path.unlink()
        self.store.discard(doc)
        self.assertFalse(doc.snapshot.path.exists())
        self.assertTrue(self.store.open(doc.id).conflict)

    def test_failed_discard_retains_draft_and_baseline(self):
        doc = self.store.create(content=b'original')
        doc.text = 'draft'
        self.store.checkpoint(doc)
        doc.snapshot.path.write_bytes(b'external')
        with patch('logisticsmobile.documents.atomic_write_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.discard(doc)
        self.assertEqual(doc.text, 'draft')
        self.assertEqual(doc.snapshot.original, b'original')
        self.assertEqual(self.store.open(doc.id).text, 'draft')

    def test_invalid_records_names_large_documents_and_links_are_preserved(self):
        with self.assertRaises(ValueError):
            DocumentStore(Path('relative'))
        for name in ('../outside', 'bad\\path', 'line\nbreak', ''):
            with self.assertRaises(ValueError):
                self.store.create(name)
        with self.assertRaises(ValueError):
            self.store.create(content=b'x' * (MAX_BYTES + 1))
        doc = self.store.create()
        with self.assertRaises(ValueError):
            self.store.path(doc.id, '/../../outside')
        path = self.store.path(doc.id, '.json')
        for content in (b'[]', b'{"schema":99}', b'not JSON'):
            path.write_bytes(content)
            documents, failures = self.store.documents()
            self.assertEqual(documents, [])
            self.assertEqual(len(failures), 1)
            self.assertEqual(path.read_bytes(), content)
        path.write_text(json.dumps(dict(schema=1, id=doc.id, name='safe', text='x',
                                       encoding='utf-8', original='invalid!')))
        with self.assertRaises(ValueError):
            self.store.open(doc.id)

    def test_import_consumes_a_scoped_stream_and_never_modifies_source(self):
        source = self.root / 'notes.md'
        source.write_bytes(b'# Imported\r\n')
        doc = self.store.import_document(LocalDocuments(), source)
        self.assertEqual(doc.name, 'notes.md')
        doc.text = '# Edited\n'
        self.store.save(doc)
        self.assertEqual(source.read_bytes(), b'# Imported\r\n')
        closed = []
        class Provider:
            @contextmanager
            def open(self, reference):
                self_reference = reference
                try:
                    self.stream = io.BytesIO(b'x' * (MAX_BYTES + 1))
                    yield self_reference, self.stream
                finally:
                    self.stream.close()
                    closed.append(True)
        with self.assertRaises(ValueError):
            self.store.import_document(Provider(), 'large.txt')
        self.assertEqual(closed, [True])

    def test_ios_adapter_balances_scope_on_success_and_read_failure(self):
        class ScopedURL:
            stopped = 0
            granted = True
            def startAccessingSecurityScopedResource(self):
                return self.granted
            def stopAccessingSecurityScopedResource(self):
                self.stopped += 1
        url = ScopedURL()
        url.path = str(self.root / 'selected.txt')
        Path(url.path).write_bytes(b'imported')
        self.assertEqual(self.store.import_document(IOSDocuments(), url).text, 'imported')
        self.assertEqual(url.stopped, 1)
        Path(url.path).unlink()
        with self.assertRaises(FileNotFoundError):
            self.store.import_document(IOSDocuments(), url)
        self.assertEqual(url.stopped, 2)
        url.granted = False
        with self.assertRaises(PermissionError):
            self.store.import_document(IOSDocuments(), url)
        self.assertEqual(url.stopped, 2)

    def test_android_adapter_closes_cursor_and_stream_on_consumer_failure(self):
        class Cursor:
            closed = False
            def moveToFirst(self): return True
            def getColumnIndexOrThrow(self, name): return 0
            def getString(self, column): return 'Selected.txt'
            def close(self): self.closed = True
        class Stream:
            closed = False
            def close(self): self.closed = True
        class Resolver:
            cursor, stream = Cursor(), Stream()
            def query(self, *args): return self.cursor
            def openInputStream(self, uri): return self.stream
        resolver = Resolver()
        with self.assertRaises(OSError):
            with AndroidDocuments(resolver).open('opaque-uri') as (name, stream):
                self.assertEqual(name, 'Selected.txt')
                raise OSError('consumer failure')
        self.assertTrue(resolver.cursor.closed)
        self.assertTrue(resolver.stream.closed)
