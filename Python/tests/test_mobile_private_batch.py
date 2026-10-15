"""Private recursive batching never keeps archive bodies and preflights all files."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from commonUtils.runtime.local_files import LocalFiles
from commonUtils.runtime.operations import OperationCancelled
from features.comics.comicinfo import ComicInfoXML
from features.comics.mobile.private_batch import PrivateCollectionBatch


class PrivateBatchTests(unittest.TestCase):
    def test_published_but_unreadable_revision_blocks_unsafe_retry(self):
        from commonUtils.runtime.operations import MutationIncomplete, MutationResult
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'one.cbz').write_bytes(b'comic')
            plan, active, opened, saves = self.plan(root)
            def incomplete(*args, **kwargs):
                raise MutationIncomplete('Synthetic post-publication failure', MutationResult(destination_published=True))
            plan.publish = incomplete
            self.assertEqual(len(plan.apply({'Title': 'Edited'})[1]), 1)
            self.assertTrue(plan.requires_reopen)
            with self.assertRaises(ValueError):
                plan.apply({'Title': 'Retry'})
            plan.close()

    def plan(self, root):
        provider = LocalFiles(root)
        active, opened, saves = [True], [], []
        info = ComicInfoXML.from_bytes(b'<ComicInfo><Title>Private title</Title></ComicInfo>')
        def document():
            return SimpleNamespace(info=ComicInfoXML.from_bytes(info.to_bytes()), prepare_metadata=lambda changes: None)
        @contextmanager
        def read(path):
            opened.append(path)
            reader = SimpleNamespace(comic=document(), path=path)
            yield reader
            reader.comic = None
        plan = PrivateCollectionBatch(valid=lambda: active[0], open_reader=read,
            revision=lambda p: provider.entry(p)['revision'],
            publish=lambda reader, changes, **kw: (saves.append(reader.path) or SimpleNamespace(comic=document())))
        plan.prepare(provider, '')
        return plan, active, opened, saves

    def test_preflight_rejects_changed_second_file_without_publishing_first(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '1.cbz').write_bytes(b'one')
            (root / '2.cbz').write_bytes(b'two')
            plan, active, opened, saves = self.plan(root)
            self.assertTrue(all(not hasattr(doc, 'source') for doc in plan.documents))
            (root / '2.cbz').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                plan.apply({'Title': 'Edited'})
            self.assertEqual(saves, [])
            active[0] = False
            with self.assertRaises(OperationCancelled):
                plan.apply({'Title': 'Edited'})
            plan.close()
            self.assertEqual(plan.documents, [])
            self.assertEqual(plan.entries, [])

    def test_cancel_after_current_file_retains_retry_baselines(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['1.cbz', '2.cbz']:
                (root / name).write_bytes(b'comic')
            plan, active, opened, saves = self.plan(root)
            publish = plan.publish
            def one(reader, changes, **kw):
                result = publish(reader, changes, **kw)
                plan.cancel.set()
                return result
            plan.publish = one
            self.assertEqual(plan.apply({'Title': 'Edited'})[0], ['1.cbz'])
            plan.cancel.clear()
            plan.publish = publish
            self.assertEqual(len(plan.apply({'Title': 'Retry'})[0]), 2)
            plan.close()
