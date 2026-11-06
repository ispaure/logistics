"""Reusable Logistics localcrypt fixtures; no test cases or discovery side effects."""

import base64
import os


class CryptClient:
    generation = 1
    identity = 'a' * 64
    connection = 'b' * 64

    def connection_identity(self, remote):
        return self.connection

    def request(self, action, **values):
        if action == 'crypt_paths':
            return [self.request('crypt_path', **dict(values, **entry, decode=True))['path']
                    for entry in values['entries']]
        if action == 'crypt_path':
            parts = values['path'].split('/') if values['path'] else []
            parts = ([bytes.fromhex(part).decode() for part in parts] if values.get('decode')
                     else [part.encode().hex() for part in parts])
            return dict(identity=self.identity, path='/'.join(parts))
        if action == 'crypt_raw_read':
            data = os.read(values['fd'], 256 * 1024)
            return dict(data=base64.b64encode(data[::-1]).decode())
        raise AssertionError(action)


class ReaderClient(CryptClient):
    def crypt_remotes(self):
        return []

    def cancel(self):
        pass

    def request(self, action, **values):
        if action == 'crypt_decode':
            return dict(name=bytes.fromhex(values['path'].rsplit('/', 1)[-1]).decode(),
                        data=base64.b64encode(os.read(values['fd'], 1024 * 1024)[::-1]).decode())
        return super().request(action, **values)


class CreationClient(ReaderClient):
    def request(self, action, **values):
        if action in {'crypt_encode', 'crypt_write_buffer'}:
            data = base64.b64decode(values['data'])
            os.write(values['fd'], b'cipher:' + data[::-1])
            return {}
        if action == 'crypt_decode':
            data = os.read(values['fd'], 1024 * 1024)
            return dict(name=bytes.fromhex(values['path'].rsplit('/', 1)[-1]).decode(),
                        data=base64.b64encode(data.removeprefix(b'cipher:')[::-1]).decode())
        if action == 'crypt_raw_read':
            data = os.read(values['fd'], 1024 * 1024)
            return dict(data=base64.b64encode(data.removeprefix(b'cipher:')[::-1]).decode())
        return super().request(action, **values)


def seed_offline_copy(copies, data=b'opaque-original'):
    """Seed a pre-existing offline record without a remote download API."""
    import json
    from uuid import uuid4
    key = uuid4().hex
    folder = copies.root / key
    folder.mkdir()
    (folder / 'data').write_bytes(data)
    (folder / 'record.json').write_text(json.dumps(dict(
        remote='Secret', encrypted_path='encoded', identity='a' * 64)))
    return key
