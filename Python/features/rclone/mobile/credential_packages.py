"""Bounded device-encrypted ZIP retention; no ZIP password or decoded settings."""
import base64
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile, BadZipFile
from commonUtils.persistence import atomic_write_json, atomic_write_bytes
from features.rclone.mobile.cloud import PACKAGE_LIMIT, download_name


class CredentialPackages:
    def __init__(self, vault, client):
        self.vault, self.client = vault, client
        self.root = vault.root
        self.index = self.root / 'packages.json'
        self.items = {}
        if self.index.is_symlink():
            raise ValueError('Retained package index cannot be linked.')
        if self.index.exists():
            if self.index.stat().st_size > 128 * 1024:
                raise ValueError('Retained package index is too large.')
            items = json.loads(self.index.read_text())
            if not isinstance(items, dict) or len(items) > 32:
                raise ValueError('Invalid retained credential packages.')
            for key, item in items.items():
                if (len(key) != 64 or any(c not in '0123456789abcdef' for c in key)
                        or not isinstance(item, dict) or set(item) != {'zip', 'remotes'}
                        or download_name(item['zip']) != item['zip'] or not isinstance(item['remotes'], dict)
                        or len(item['remotes']) > 256 or any(not isinstance(remote, str) or not remote or len(remote) > 80
                            or not isinstance(identity, str) or len(identity) != 64
                            or any(c not in '0123456789abcdef' for c in identity)
                            for remote, identity in item['remotes'].items())):
                    raise ValueError('Invalid retained credential association.')
            self.items = items

    def path(self, key):
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid package identity.')
        path = self.root / (key + '.bin')
        if path.is_symlink():
            raise ValueError('Retained package cannot be linked.')
        return path

    def remember(self, package, remotes):
        if len(package.data) > PACKAGE_LIMIT:
            raise ValueError('Credential ZIP exceeds the limit.')
        # The device key alone must never recover decoded session credentials.
        # Retain only original ZIPs that still require their own password.
        try:
            with ZipFile(BytesIO(package.data)) as archive:
                files = [entry for entry in archive.infolist() if not entry.is_dir()]
                if not files or len(files) > 64 or any(not entry.flag_bits & 1 for entry in files):
                    raise ValueError('Only password-protected credential ZIPs can be retained for session unlocking.')
        except BadZipFile as error:
            raise ValueError('Only password-protected credential ZIPs can be retained for session unlocking.') from error
        key = sha256(package.name.encode() + b'\0' + package.data).hexdigest()
        values = self.vault.unlock(create=True)
        encrypted = self.client.request('protect_package', key=values['key'], id=key,
            data=base64.b64encode(package.data).decode())
        data = base64.b64decode(encrypted, validate=True)
        if len(data) > PACKAGE_LIMIT + 64:
            raise ValueError('Retained package exceeds the limit.')
        next_items = {identity: item for identity, item in self.items.items() if item['zip'] != package.name}
        if len(next_items) >= 32:
            raise ValueError('Retained credential package limit reached.')
        next_items[key] = dict(zip=package.name, remotes=remotes)
        atomic_write_bytes(self.path(key), data)
        atomic_write_json(self.index, next_items, max_bytes=128 * 1024)
        previous = self.items
        self.items = next_items
        for retired in previous.keys() - next_items.keys():
            self.path(retired).unlink(missing_ok=True)
        return key

    @contextmanager
    def open(self, key):
        path = self.path(key)
        if path.stat().st_size > PACKAGE_LIMIT + 64:
            raise ValueError('Retained package exceeds the limit.')
        values = self.vault.unlock()
        if values is None:
            raise ValueError('The retained package key is unavailable.')
        data = self.client.request('unprotect_package', key=values['key'], id=key,
                                  data=base64.b64encode(path.read_bytes()).decode())
        decoded = base64.b64decode(data, validate=True)
        if len(decoded) > PACKAGE_LIMIT:
            raise ValueError('Retained ZIP exceeds the limit.')
        with BytesIO(decoded) as stream:
            yield self.items[key]['zip'], stream

    def matching(self, remote, identity=None):
        return [(key, item) for key, item in self.items.items()
                if remote in item['remotes'] and (identity is None or item['remotes'][remote] == identity)]

    def forget(self):
        self.vault.forget()
        for key in self.items:
            self.path(key).unlink(missing_ok=True)
        self.index.unlink(missing_ok=True)
        self.items = {}
