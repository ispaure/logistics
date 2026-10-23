"""Bounded device-encrypted ZIP retention; no ZIP password or decoded settings."""
import base64
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
from copy import deepcopy
from threading import RLock
from weakref import WeakSet
from zipfile import ZipFile, BadZipFile
from commonUtils.persistence import atomic_write_json, atomic_write_bytes
from features.rclone.mobile.cloud import PACKAGE_LIMIT, download_name


_stores = WeakSet()
_store_lock = RLock()


class CredentialPackages:
    def __init__(self, vault, client, *, document_cache_root=None, load=True):
        self.vault, self.client = vault, client
        self.root = vault.root
        self.document_cache_root = Path(document_cache_root) if document_cache_root is not None else self.root / 'document-lists'
        self.index = self.root / 'packages.json'
        with _store_lock:
            self.items = self._read_items() if load else {}
            _stores.add(self)

    def _read_items(self):
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
                        or not isinstance(item, dict) or not {'zip', 'remotes'} <= set(item)
                        or not set(item) <= {'zip', 'remotes', 'aliases', 'crypt_remotes'}
                        or download_name(item['zip']) != item['zip'] or not isinstance(item['remotes'], dict)
                        or len(item['remotes']) > 256 or any(not isinstance(remote, str) or not remote or len(remote) > 80
                            or not isinstance(identity, str) or len(identity) != 64
                            or any(c not in '0123456789abcdef' for c in identity)
                            for remote, identity in item['remotes'].items())):
                    raise ValueError('Invalid retained credential association.')
            for item in items.values():
                crypt = item.get('crypt_remotes', [])
                if not isinstance(crypt, list) or any(not isinstance(name, str) or name not in item['remotes'] for name in crypt):
                    raise ValueError('Invalid retained crypt remote names.')
                aliases = item.get('aliases', {})
                if (not isinstance(aliases, dict) or len(aliases) > 64
                        or any(not isinstance(name, str) or not 0 < len(name) <= 80
                               or not isinstance(alias, str) or alias not in item['remotes']
                               for name, alias in aliases.items())):
                    raise ValueError('Invalid retained credential aliases.')
            return items
        return {}

    def _publish_items(self, items):
        # Other scenes may already hold a read-only metadata view of this root.
        with _store_lock:
            for store in tuple(_stores):
                if store.root == self.root:
                    store.items = deepcopy(items)

    def path(self, key):
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid package identity.')
        path = self.root / (key + '.bin')
        if path.is_symlink():
            raise ValueError('Retained package cannot be linked.')
        return path

    def remember(self, package, remotes, *, aliases=None, crypt_remotes=()):
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
        if aliases:
            next_items[key]['aliases'] = dict(aliases)
        if crypt_remotes:
            next_items[key]['crypt_remotes'] = sorted(set(crypt_remotes) & set(remotes))
        atomic_write_bytes(self.path(key), data)
        atomic_write_json(self.index, next_items, max_bytes=128 * 1024)
        previous = self.items
        self._publish_items(next_items)
        for retired in previous.keys() - next_items.keys():
            from .document_lists import forget_cache
            forget_cache(self.document_cache_root, retired)
            self.path(retired).unlink(missing_ok=True)
        return key

    def aliases(self, key):
        return dict(self.items[key].get('aliases', {}))

    def update_crypt_remotes(self, key, crypt_remotes, *, aliases=None):
        """Repair older type metadata after unlock without retaining secrets."""
        item = self.items[key]
        crypt = set(crypt_remotes)
        known = set() if aliases else set(item['remotes']) & crypt
        # A package can receive different aliases when another account with the
        # same remote names is loaded. Keep the retained index's name namespace.
        previous = item.get('aliases', {})
        for original, loaded in (aliases or {}).items():
            retained = previous.get(original, original)
            if loaded in crypt and retained in item['remotes']:
                known.add(retained)
        names = sorted(known)
        if item.get('crypt_remotes') == names:
            return
        updated = {**self.items, key: {**item, 'crypt_remotes': names}}
        atomic_write_json(self.index, updated, max_bytes=128 * 1024)
        self._publish_items(updated)

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
        from .document_lists import forget_cache
        # Attempt independent erasures even if a key store or a cache unlink
        # fails. Keep the index in memory on failure so retry can finish cleanup.
        operations = [self.vault.forget, lambda: forget_cache(self.document_cache_root)]
        keys = set(self.items)
        keys.update(path.stem for path in self.root.glob('*.bin')
                    if len(path.stem) == 64 and all(c in '0123456789abcdef' for c in path.stem))
        operations.extend(lambda key=key: self.path(key).unlink(missing_ok=True) for key in keys)
        failure = None
        for operation in operations:
            try:
                operation()
            except Exception as error:
                failure = failure or error
        if failure is not None:
            raise failure
        self.index.unlink(missing_ok=True)
        self._publish_items({})
