"""The SSH recovery path keeps original files and publishes only complete copies."""
from contextlib import contextmanager
from io import BufferedReader, BytesIO
import json
import os
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from commonUtils.testing.stages import TestStage
from features.notebooks import remarkable_ssh

TEST_STAGE = TestStage.REGRESSION
DOC = '10000000-0000-4000-8000-000000000001'
FOLDER = '10000000-0000-4000-8000-000000000002'
PAGE = '10000000-0000-4000-8000-000000000003'


def tar_stream(entries):
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, data in (entries.items() if isinstance(entries, dict) else entries):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, BytesIO(data))
    buffer.seek(0)
    return BufferedReader(buffer)


class RemarkableSSHTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'The tablet sidecar script uses a POSIX shell and symlinks.')
    def test_exact_sidecars_do_not_enumerate_unselected_documents(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            expected = {DOC + '.metadata': b'{"type":"DocumentType"}', DOC + '.content': b'{}',
                        FOLDER + '.metadata': b'{"type":"CollectionType"}'}
            for name, data in expected.items():
                (root / name).write_bytes(data)
            (root / (PAGE + '.metadata')).write_bytes(b'private unselected record')

            @contextmanager
            def stream(host, command, cancelled, *, port, connection):
                self.assertEqual((host, port, connection), ('synthetic.invalid', 2222, 'owned session'))
                result = subprocess.run(['/bin/sh', '-c', command], cwd=root, capture_output=True,
                                        check=True, timeout=5, env=dict(os.environ, COPYFILE_DISABLE='1'))
                with BufferedReader(BytesIO(result.stdout)) as data:
                    yield data

            with patch.object(remarkable_ssh, 'ssh_stream', stream):
                self.assertEqual(remarkable_ssh.read_sidecars('synthetic.invalid', [DOC, FOLDER],
                                 port=2222, connection='owned session'), expected)
                (root / (DOC + '.metadata')).unlink()
                (root / (DOC + '.metadata')).symlink_to(root / (PAGE + '.metadata'))
                with self.assertRaises(subprocess.CalledProcessError):
                    remarkable_ssh.read_sidecars('synthetic.invalid', [DOC], port=2222, connection='owned session')

    def test_scoped_response_rejects_missing_foreign_duplicate_and_nonfile_records(self):
        for entries in ({}, {PAGE + '.metadata': b'{}'}, [(DOC + '.metadata', b'{}')] * 2,
                        {DOC + '.metadata': b'x' * 101}):
            @contextmanager
            def stream(*_, **__):
                with tar_stream(entries) as data:
                    yield data
            with self.subTest(entries=entries), patch.object(remarkable_ssh, 'ssh_stream', stream), \
                    patch.object(remarkable_ssh, 'MAX_SIDECAR', 100), self.assertRaises(ValueError):
                remarkable_ssh.read_sidecars('synthetic.invalid', [DOC])
        with patch.object(remarkable_ssh, 'ssh_stream') as stream:
            for identities in ([], [DOC, DOC], ['../escape'], [DOC] * 257, [None], [{}]):
                with self.assertRaises(ValueError):
                    remarkable_ssh.read_sidecars('synthetic.invalid', identities)
            stream.assert_not_called()

        @contextmanager
        def oversized(*_, **__):
            with tar_stream({DOC + '.metadata': b'{}', DOC + '.content': b'{}'}) as data:
                yield data
        with patch.object(remarkable_ssh, 'ssh_stream', oversized), \
                patch.object(remarkable_ssh, 'MAX_SCOPED_SIDECARS', 3), self.assertRaises(ValueError):
            remarkable_ssh.read_sidecars('synthetic.invalid', [DOC])

    @unittest.skipUnless(os.name == 'posix', 'The tablet enumeration script uses a POSIX shell.')
    def test_nonfile_first_glob_does_not_hide_later_files_or_read_nested_data(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / (DOC + '.metadata')
            first.mkdir()
            nested = first / 'private-content'
            nested.write_bytes(b'DO NOT READ THIS NESTED CONTENT')
            (root / (FOLDER + '.metadata')).write_bytes(b'{"type":"DocumentType","visibleName":"Visible"}')
            (root / (PAGE + '.metadata')).symlink_to(root / 'absent')
            legacy = 'set -- ./*.metadata\nif [ -f "$1" ]; then exec tar -cf - "$@"; fi'
            self.assertEqual(subprocess.run(['/bin/sh', '-c', legacy], cwd=root,
                capture_output=True, check=True, timeout=5).stdout, b'')

            @contextmanager
            def stream(host, command, cancelled, **__):
                self.assertEqual(host, 'synthetic.invalid')
                result = subprocess.run(['/bin/sh', '-c', command], cwd=root,
                                        capture_output=True, check=True, timeout=5,
                                        env=dict(os.environ, COPYFILE_DISABLE='1'))
                self.assertNotIn(b'DO NOT READ THIS NESTED CONTENT', result.stdout)
                with BufferedReader(BytesIO(result.stdout)) as data:
                    yield data

            with patch.object(remarkable_ssh, 'ssh_stream', stream):
                for kind in ('directory', 'broken symlink'):
                    with self.subTest(first=kind):
                        snapshot = remarkable_ssh.list_snapshot('synthetic.invalid')
                        self.assertEqual(set(snapshot.inventory), {DOC, FOLDER, PAGE})
                        self.assertEqual(snapshot.unidentified_records, 0)
                        self.assertTrue(snapshot.inventory[FOLDER].visible)
                        for identity in (DOC, PAGE):
                            self.assertEqual(snapshot.inventory[identity].read_issues, ('unsupported_entry',))
                        self.assertEqual([item.id for item in remarkable_ssh.list_documents('synthetic.invalid')], [FOLDER])
                    if kind == 'directory':
                        nested.unlink()
                        first.rmdir()
                        first.symlink_to(root / 'absent-first')
                for item in root.iterdir():
                    item.unlink()
                self.assertEqual(dict(remarkable_ssh.list_snapshot('synthetic.invalid').inventory), {})

    def test_inventory_accounts_for_omissions_without_titles_or_filenames(self):
        from dataclasses import asdict
        from features.notebooks.remarkable_store import ROOT
        ids = [f'10000000-0000-4000-8000-{i:012d}' for i in range(1, 9)]
        entries = [(ids[0] + '.metadata', b'{"type":"DocumentType","visibleName":"Private title"}'),
                   (ids[1] + '.metadata', b'{"type":"FuturePrivateType","visibleName":"Private title"}'),
                   (ids[2] + '.metadata', b'{broken private text'),
                   (ids[3] + '.metadata', b'[]'),
                   (ids[4] + '.metadata', b'{"type":"DocumentType","parent":"trash"}'),
                   (ids[5] + '.metadata', b'x' * 101),
                   ('Private filename.metadata', b'{}'),
                   (ids[0] + '.metadata', b'{bad duplicate'),
                   (ids[6] + '.metadata', b'\xff'),
                   (ids[7] + '.metadata', b'{}')]

        @contextmanager
        def stream(*_, **__):
            with tar_stream(entries) as data:
                yield data

        with patch.object(remarkable_ssh, 'ssh_stream', stream), patch.object(remarkable_ssh, 'MAX_SIDECAR', 100):
            snapshot = remarkable_ssh.list_snapshot('synthetic.invalid')
            legacy = remarkable_ssh.list_documents('synthetic.invalid')
        self.assertEqual(set(snapshot.entries), {ROOT, ids[0]})
        self.assertEqual([doc.id for doc in legacy], [ids[0]])
        receipt = {key: asdict(value) for key, value in snapshot.inventory.items()}
        self.assertNotIn('Private', json.dumps(receipt))
        self.assertEqual(sum(item.occurrences for item in snapshot.inventory.values()) + snapshot.unidentified_records,
                         len(entries))
        self.assertEqual(snapshot.unidentified_records, 1)
        self.assertEqual(snapshot.inventory[ids[0]].occurrences, 2)
        self.assertTrue(snapshot.inventory[ids[0]].visible)
        self.assertEqual(snapshot.inventory[ids[0]].read_issues, ('unreadable_metadata',))
        self.assertEqual(snapshot.inventory[ids[1]].reason, 'unsupported_type')
        self.assertEqual(snapshot.inventory[ids[4]].reason, 'deleted_or_trashed')
        self.assertEqual(snapshot.inventory[ids[5]].read_issues, ('metadata_too_large',))
        self.assertEqual(snapshot.inventory[ids[7]].reason, 'unsupported_type')
        for index in (2, 3, 5, 6):
            self.assertEqual(snapshot.inventory[ids[index]].reason, 'unreadable_metadata')
        with self.assertRaises(TypeError):
            snapshot.inventory[ids[0]] = None

    def test_inventory_is_not_returned_after_a_failed_transport(self):
        @contextmanager
        def stream(*_, **__):
            with tar_stream({DOC + '.metadata': b'{}'}) as data:
                yield data
            raise OSError('Incomplete synthetic inventory')

        with patch.object(remarkable_ssh, 'ssh_stream', stream), self.assertRaises(OSError):
            remarkable_ssh.list_snapshot('synthetic.invalid')

    def test_browse_uses_folder_metadata_and_omits_trash(self):
        entries = {
            './' + DOC + '.metadata': json.dumps(dict(
                type='DocumentType', parent=FOLDER, visibleName='Journal')).encode(),
            FOLDER + '.metadata': b'{"type":"CollectionType","visibleName":"Personal"}',
            PAGE + '.metadata': b'{"type":"DocumentType","parent":"trash","visibleName":"Trash"}',
        }

        @contextmanager
        def stream(*_, port):
            self.assertEqual(port, 2222)
            with tar_stream(entries) as data:
                yield data

        with patch.object(remarkable_ssh, 'ssh_stream', stream):
            self.assertEqual(remarkable_ssh.list_documents('tablet', port=2222),
                             [remarkable_ssh.TabletDocument(DOC, 'Journal', 'Personal')])
            snapshot = remarkable_ssh.list_snapshot('tablet', port=2222)
            self.assertEqual(snapshot.children[FOLDER], (DOC,))
            self.assertEqual(snapshot.entries[FOLDER].title, 'Personal')
            self.assertNotIn(PAGE, snapshot.entries)

    def test_export_preserves_nested_images_and_checks_ssh_before_publishing(self):
        entries = {
            DOC + '.metadata': b'{"type":"DocumentType","visibleName":"Journal"}',
            DOC + '.content': b'{"fileType":"pdf"}',
            DOC + '.pdf': b'embedded PDF bytes',
            f'{DOC}/{PAGE}.rm': b'native ink',
            f'{DOC}/{PAGE}/image.png': b'native image',
        }
        failed = False
        owned_connection = object()

        @contextmanager
        def stream(*_, port, connection):
            self.assertEqual(port, 2222)
            self.assertIs(connection, owned_connection)
            with tar_stream(entries) as data:
                yield data
            if failed:
                raise OSError('SSH did not finish')

        with TemporaryDirectory() as directory, patch.object(remarkable_ssh, 'ssh_stream', stream):
            destination = Path(directory) / 'Journal.rmdoc'
            failed = True
            with self.assertRaisesRegex(OSError, 'SSH did not finish'):
                remarkable_ssh.export_document('tablet', DOC, destination, port=2222, connection=owned_connection)
            self.assertEqual(list(destination.parent.iterdir()), [])
            failed = False
            remarkable_ssh.export_document('tablet', DOC, destination, port=2222, connection=owned_connection)
            with ZipFile(destination) as archive:
                self.assertEqual({name: archive.read(name) for name in archive.namelist()}, entries)
            with self.assertRaises(FileExistsError):
                remarkable_ssh.export_document('tablet', DOC, destination)

    def test_unsafe_member_is_rejected(self):
        @contextmanager
        def stream(*_, port):
            with tar_stream({f'{DOC}/../escape.png': b'bad path'}) as data:
                yield data

        with TemporaryDirectory() as directory, patch.object(remarkable_ssh, 'ssh_stream', stream):
            destination = Path(directory) / 'Journal.rmdoc'
            with self.assertRaisesRegex(ValueError, 'invalid archive path'):
                remarkable_ssh.export_document('tablet', DOC, destination)
            self.assertEqual(list(destination.parent.iterdir()), [])


    def test_verified_overwrite_and_failures_preserve_approved_destination(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from commonUtils.runtime.operations import OperationCancelled
        from features.notebooks.notebook import Notebook
        book = Notebook.new('Synthetic checked replacement', template='Blank')
        with ZipFile(BytesIO(book.to_bytes())) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        failure, cancelled = None, False

        @contextmanager
        def stream(*_, port):
            nonlocal cancelled
            payload = dict(entries)
            if failure == 'invalid':
                del payload[book.id + '.content']
            with tar_stream(payload) as data:
                yield data
            if failure == 'disconnect':
                raise OSError('Synthetic disconnect')
            if failure == 'cancel':
                cancelled = True

        with TemporaryDirectory() as folder, patch.object(remarkable_ssh, 'ssh_stream', stream):
            target = Path(folder) / 'copy.rmdoc'
            provider = LocalFiles(folder)
            for failure, expected in (('invalid', KeyError), ('disconnect', OSError), ('cancel', OperationCancelled)):
                with self.subTest(failure=failure):
                    target.write_bytes(b'previous archive')
                    revision = provider.entry(target.name)['revision']
                    cancelled = False
                    with self.assertRaises(expected):
                        remarkable_ssh.export_document('synthetic.invalid', book.id, target,
                            expected_revision=revision, cancelled=lambda: cancelled)
                    self.assertEqual(target.read_bytes(), b'previous archive')
                    self.assertEqual(list(target.parent.glob('.document-export-*')), [])
            failure, cancelled = None, False
            remarkable_ssh.export_document('synthetic.invalid', book.id, target,
                expected_revision=provider.entry(target.name)['revision'])
            self.assertEqual(Notebook.read(target.read_bytes()).name, book.name)
            with ZipFile(target) as archive:
                self.assertEqual({name: archive.read(name) for name in archive.namelist()}, entries)
