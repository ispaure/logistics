"""Folder pull publication, containment and cancellation contracts."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.folder_download import pull_folder


class Client:
    generation = 1
    def entries(self, remote, path):
        return ({'photos': [dict(path='photos/empty', directory=True), dict(path='photos/note.txt', directory=False)],
                 'photos/empty': []})[path]
    def download_into(self, remote, path, descriptor):
        os.write(descriptor, b'ordinary bytes')
    def download_decrypted_into(self, remote, path, descriptor):
        os.write(descriptor, b'decrypted bytes')


class FolderPullTests(unittest.TestCase):
    def test_nested_empty_folders_and_repeat_pulls_preserve_local_edits(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'LocalFiles'
            first = pull_folder(Client(), 'remote', 'photos', root)
            self.assertTrue((first / 'empty').is_dir())
            (first / 'note.txt').write_bytes(b'local edits')
            second = pull_folder(Client(), 'remote', 'photos', root, decrypted=True)
            self.assertNotEqual(first, second)
            self.assertEqual((first / 'note.txt').read_bytes(), b'local edits')
            self.assertEqual((second / 'note.txt').read_bytes(), b'decrypted bytes')

    def test_failure_and_cancellation_never_publish_partial_folders(self):
        for mode in ('failure', 'cancel', 'generation'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                root = Path(directory) / 'LocalFiles'
                client = Client()
                cancelled = [False]
                def transfer(remote, path, descriptor):
                    os.write(descriptor, b'partial')
                    if mode == 'failure':
                        raise ValueError('Network failed')
                    if mode == 'cancel':
                        cancelled[0] = True
                    if mode == 'generation':
                        client.generation += 1
                client.download_into = transfer
                with self.assertRaises(ValueError):
                    pull_folder(client, 'remote', 'photos', root, cancelled=lambda: cancelled[0])
                self.assertEqual(list(root.iterdir()), [])
                self.assertEqual(list(Path(directory).iterdir()), [root])

    def test_remote_paths_cannot_escape_or_repeat(self):
        for path in ('photos/../escape', 'elsewhere/file', 'photos/sub/file', 'photos/evil\\file'):
            with self.subTest(path=path), TemporaryDirectory() as directory:
                root = Path(directory) / 'LocalFiles'
                client = Client()
                client.entries = lambda remote, folder: [dict(path=path, directory=False)]
                with self.assertRaises(ValueError):
                    pull_folder(client, 'remote', 'photos', root)
                self.assertEqual(list(root.iterdir()), [])
