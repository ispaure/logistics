"""The SSH recovery path keeps original files and publishes only complete copies."""
from contextlib import contextmanager
from io import BufferedReader, BytesIO
import json
from pathlib import Path
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
        for name, data in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, BytesIO(data))
    buffer.seek(0)
    return BufferedReader(buffer)


class RemarkableSSHTests(unittest.TestCase):
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

    def test_export_preserves_nested_images_and_checks_ssh_before_publishing(self):
        entries = {
            DOC + '.metadata': b'{"type":"DocumentType","visibleName":"Journal"}',
            DOC + '.content': b'{"fileType":"pdf"}',
            DOC + '.pdf': b'embedded PDF bytes',
            f'{DOC}/{PAGE}.rm': b'native ink',
            f'{DOC}/{PAGE}/image.png': b'native image',
        }
        failed = False

        @contextmanager
        def stream(*_, port):
            self.assertEqual(port, 2222)
            with tar_stream(entries) as data:
                yield data
            if failed:
                raise OSError('SSH did not finish')

        with TemporaryDirectory() as directory, patch.object(remarkable_ssh, 'ssh_stream', stream):
            destination = Path(directory) / 'Journal.rmdoc'
            failed = True
            with self.assertRaisesRegex(OSError, 'SSH did not finish'):
                remarkable_ssh.export_document('tablet', DOC, destination, port=2222)
            self.assertEqual(list(destination.parent.iterdir()), [])
            failed = False
            remarkable_ssh.export_document('tablet', DOC, destination, port=2222)
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
