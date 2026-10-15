"""Device-protected encryption keys; only wrapped keys/metadata live in files.

Native calls are made on a worker thread by CloudUI. There is no plaintext or
password fallback when a protected key is inaccessible.
"""
import base64
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4
from commonUtils.runtime.protected_keys import AndroidKeys, IOSKeys, KeyStoreUnavailable as VaultUnavailable




class ProtectedVault:
    def __init__(self, root, keys, platform):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise VaultUnavailable('Credentials require private device storage.')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.keys, self.platform = keys, platform
        self.record = self.root / 'protected-key.json'
        self.ciphertext = self.root / 'credentials.bin'

    @classmethod
    def for_app(cls, app, *, packages=False):
        from commonUtils.runtime.platform import get_os, OS
        current = get_os()
        folder = 'CredentialPackages' if packages else 'Credentials'
        service = 'io.github.ispaure.logisticsmobile.' + ('packages' if packages else 'credentials')
        if current is OS.ANDROID:
            # noBackupFilesDir is explicitly excluded from Android backup/restore.
            root = Path(str(app._impl.native.getNoBackupFilesDir().getAbsolutePath())) / ('LogisticsCredentialPackages' if packages else 'LogisticsCredentials')
            if app.storage_root is not None:  # Native test fixtures get separate keys/data.
                root = app.private_root / folder
            return cls(root, AndroidKeys(alias_prefix='Logistics.packages.' if packages else 'Logistics.credentials.', aad_prefix='Logistics packages v1:' if packages else 'Logistics credentials v1:'), 'android')
        if current is OS.IOS:
            vault = cls(app.private_root / folder, IOSKeys(service=service,
                label='Logistics — encrypted remote credentials', label_prefix='Logistics — '), 'ios')
            from rubicon.objc import ObjCClass
            url = ObjCClass('NSURL').fileURLWithPath(str(vault.root))
            if not url.setResourceValue(True, forKey='NSURLIsExcludedFromBackupKey', error=None):
                raise VaultUnavailable('Private credential storage could not be excluded from backup.')
            return vault
        raise VaultUnavailable('Protected credentials require Android or iOS.')

    def metadata(self):
        if not self.record.exists():
            if self.record.is_symlink() or self.ciphertext.exists() or self.ciphertext.is_symlink():
                raise VaultUnavailable('The protected-key record is missing. Forget saved credentials before importing again.')
            return None
        if self.record.is_symlink() or getattr(self.record, 'is_junction', lambda: False)():
            raise OSError('Protected-key records cannot use links.')
        before = self.record.lstat()
        descriptor = os.open(self.record, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            import stat
            info = os.fstat(descriptor)
            if ((info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)
                    or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4096):
                raise VaultUnavailable('Invalid protected-key record.')
            with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                try:
                    record = json.loads(stream.read(4097))
                except (ValueError, UnicodeError) as error:
                    raise VaultUnavailable('Invalid protected-key record.') from error
        finally:
            os.close(descriptor)
        identity = record.get('id', '') if isinstance(record, dict) else ''
        if (not isinstance(record, dict) or record.get('schema') != 1 or record.get('platform') != self.platform or not isinstance(identity, str) or len(identity) != 32
                or any(c not in '0123456789abcdef' for c in identity)):
            raise VaultUnavailable('Invalid protected-key record.')
        return record

    def unlock(self, *, create=False):
        record = self.metadata()
        if record is None:
            if not create:
                return None
            identity, key = uuid4().hex, secrets.token_bytes(32)
            created = False
            try:
                wrapped = self.keys.create(identity, key)
                record = dict(schema=1, platform=self.platform, id=identity, **wrapped)
                data = (json.dumps(record) + '\n').encode()
                descriptor = os.open(self.record, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                if created:
                    self.record.unlink(missing_ok=True)
                self.keys.delete(identity)
                raise
        else:
            key = self.keys.load(record['id'], record)
        if not isinstance(key, bytes) or len(key) != 32:
            raise VaultUnavailable('The device encryption key is unavailable.')
        return dict(path=str(self.ciphertext), id=record['id'], key=base64.b64encode(key).decode())

    def set_label(self, label):
        record = self.metadata()
        if record is not None and hasattr(self.keys, 'set_label'):
            self.keys.set_label(record['id'], label)

    def forget(self):
        try:
            record = self.metadata()
        except (ValueError, OSError):
            record = None  # Discard unusable ciphertext without guessing a key alias.
        if record:
            # Erase the protected key before ciphertext; no silent key regeneration.
            self.keys.delete(record['id'])
        self.ciphertext.unlink(missing_ok=True)
        self.record.unlink(missing_ok=True)
