"""Generate synthetic desktop-rclone ciphertext for native LocalCrypt tests.

Run with the desktop test environment and PYTHONPATH=Python:Python/tests. All
passwords are public fixture values; no user credentials or documents are read.
"""
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from commonUtils.archives.zip_access import open_archive
from features.rclone import executable, session
from local_crypt_fixture import crypt_fixture
from books_fixture import make_book


def generate(destination):
    with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
        settings = dict(session.credentials(fixture.context)['Secret'], remote='Cloud:native-fixture')
        package = BytesIO()
        with ZipFile(package, 'w') as archive:
            archive.writestr('Cloud.txt', '[Cloud]\ntype=memory\n')
            archive.writestr('Secret.txt', '[Secret]\n' + ''.join(f'{key}={value}\n' for key, value in settings.items()))
        identity = sha256(json.dumps(settings, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        fixture.provider.command('rcat', 'text.txt', input_data=b'\xef\xbb\xbfNative text\r\n', limit=0)
        book = BytesIO()
        make_book(book)
        fixture.provider.command('rcat', 'book.epub', input_data=book.getvalue(), limit=0)
        protected = BytesIO()
        with ZipFile(BytesIO(book.getvalue())) as source, open_archive(protected, 'w', password='synthetic-archive-password') as target:
            for member in source.infolist():
                target.writestr(member.filename, source.read(member))
        fixture.provider.command('rcat', 'protected.epub', input_data=protected.getvalue(), limit=0)
        copies = {}
        for index, name in enumerate(('note.md', 'text.txt', 'plain.cbz', 'encrypted.cbz', 'book.epub', 'protected.epub')):
            encrypted = fixture.provider.encrypted_path(name)
            copies[name] = dict(key=f'{index + 1:032x}', ciphertext=base64.b64encode(encrypted.read_bytes()).decode(),
                record=dict(remote='Secret', encrypted_path=encrypted.name, identity=identity))
        destination.write_text(json.dumps(dict(package=base64.b64encode(package.getvalue()).decode(), copies=copies), indent=2) + '\n')


if __name__ == '__main__':
    generate(Path(__file__).parent / 'native_tests/tests/logisticsmobile/localcrypt_fixture.json')
