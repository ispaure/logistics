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


class VaultUnavailable(ValueError):
    pass


def _bytes(value):
    return bytes(int(item) & 255 for item in value)


class AndroidKeys:
    def __init__(self):
        from java import jclass
        self.jclass = jclass
        self.store = jclass('java.security.KeyStore').getInstance('AndroidKeyStore')
        self.store.load(None, None)

    def alias(self, identity):
        return 'Logistics.credentials.' + identity

    def create(self, identity, key):
        from java import jarray, jbyte
        String = self.jclass('java.lang.String')
        Properties = self.jclass('android.security.keystore.KeyProperties')
        Builder = self.jclass('android.security.keystore.KeyGenParameterSpec$Builder')
        specification = (Builder(self.alias(identity), Properties.PURPOSE_ENCRYPT | Properties.PURPOSE_DECRYPT)
                         .setBlockModes(jarray(String)(['GCM']))
                         .setEncryptionPaddings(jarray(String)(['NoPadding']))
                         .setKeySize(256).setRandomizedEncryptionRequired(True).build())
        generator = self.jclass('javax.crypto.KeyGenerator').getInstance('AES', 'AndroidKeyStore')
        generator.init(specification)
        native_key = generator.generateKey()
        cipher = self.jclass('javax.crypto.Cipher').getInstance('AES/GCM/NoPadding')
        cipher.init(1, native_key)
        aad = ('Logistics credentials v1:' + identity).encode()
        cipher.updateAAD(jarray(jbyte)([v if v < 128 else v - 256 for v in aad]))
        wrapped = cipher.doFinal(jarray(jbyte)([v if v < 128 else v - 256 for v in key]))
        return {'nonce': base64.b64encode(_bytes(cipher.getIV())).decode(),
                'wrapped': base64.b64encode(_bytes(wrapped)).decode()}

    def load(self, identity, record):
        from java import jarray, jbyte
        key = self.store.getKey(self.alias(identity), None)
        if key is None:
            raise VaultUnavailable('The device encryption key is missing.')
        nonce = base64.b64decode(record['nonce'], validate=True)
        wrapped = base64.b64decode(record['wrapped'], validate=True)
        if len(nonce) != 12 or len(wrapped) != 48:
            raise VaultUnavailable('Invalid protected-key record.')
        array = lambda data: jarray(jbyte)([v if v < 128 else v - 256 for v in data])
        cipher = self.jclass('javax.crypto.Cipher').getInstance('AES/GCM/NoPadding')
        cipher.init(2, key, self.jclass('javax.crypto.spec.GCMParameterSpec')(128, array(nonce)))
        cipher.updateAAD(array(('Logistics credentials v1:' + identity).encode()))
        return _bytes(cipher.doFinal(array(wrapped)))

    def delete(self, identity):
        self.store.deleteEntry(self.alias(identity))


class IOSKeys:
    """Security.framework generic-password item, unlocked/device-only, no sync."""
    def __init__(self):
        import ctypes as c
        self.c = c
        self.security = c.CDLL('/System/Library/Frameworks/Security.framework/Security')
        self.cf = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        signatures = {
            'CFStringCreateWithCString': (c.c_void_p, [c.c_void_p, c.c_char_p, c.c_uint32]),
            'CFDataCreate': (c.c_void_p, [c.c_void_p, c.c_void_p, c.c_long]),
            'CFDataGetLength': (c.c_long, [c.c_void_p]),
            'CFDataGetBytePtr': (c.c_void_p, [c.c_void_p]),
            'CFDictionaryCreateMutable': (c.c_void_p, [c.c_void_p, c.c_long, c.c_void_p, c.c_void_p]),
            'CFDictionarySetValue': (None, [c.c_void_p, c.c_void_p, c.c_void_p]),
            'CFRelease': (None, [c.c_void_p]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.cf, name)
            function.restype, function.argtypes = result, arguments
        for name, arguments in {'SecItemAdd': [c.c_void_p, c.c_void_p],
                                'SecItemCopyMatching': [c.c_void_p, c.POINTER(c.c_void_p)],
                                'SecItemDelete': [c.c_void_p],
                                'SecItemUpdate': [c.c_void_p, c.c_void_p]}.items():
            function = getattr(self.security, name)
            function.restype, function.argtypes = c.c_int32, arguments

    def constant(self, name):
        library = self.cf if name.startswith('kCF') else self.security
        return self.c.c_void_p.in_dll(library, name).value

    def perform(self, operation, identity, key=None):
        c = self.c
        owned = []
        def string(value):
            pointer = self.cf.CFStringCreateWithCString(None, value.encode(), 0x08000100)
            owned.append(pointer)
            return pointer
        dictionary = self.cf.CFDictionaryCreateMutable(None, 0, None, None)
        owned.append(dictionary)
        def put(name, value):
            self.cf.CFDictionarySetValue(dictionary, self.constant(name), value)
        put('kSecClass', self.constant('kSecClassGenericPassword'))
        put('kSecAttrService', string('io.github.ispaure.logisticsmobile.credentials'))
        put('kSecAttrAccount', string(identity))
        put('kSecAttrSynchronizable', self.constant('kCFBooleanFalse'))
        result = c.c_void_p()
        try:
            if operation == 'create':
                put('kSecAttrLabel', string('Logistics — encrypted remote credentials'))
                put('kSecAttrAccessible', self.constant('kSecAttrAccessibleWhenUnlockedThisDeviceOnly'))
                buffer = c.create_string_buffer(key)
                data = self.cf.CFDataCreate(None, c.cast(buffer, c.c_void_p), len(key))
                owned.append(data)
                put('kSecValueData', data)
                status = self.security.SecItemAdd(dictionary, None)
            elif operation == 'load':
                put('kSecReturnData', self.constant('kCFBooleanTrue'))
                put('kSecMatchLimit', self.constant('kSecMatchLimitOne'))
                status = self.security.SecItemCopyMatching(dictionary, c.byref(result))
            elif operation == 'label':
                attributes = self.cf.CFDictionaryCreateMutable(None, 0, None, None)
                owned.append(attributes)
                self.cf.CFDictionarySetValue(attributes, self.constant('kSecAttrLabel'), string('Logistics — ' + key))
                status = self.security.SecItemUpdate(dictionary, attributes)
            else:
                status = self.security.SecItemDelete(dictionary)
            if operation == 'delete' and status == -25300:  # Already absent.
                return None
            if status:
                raise VaultUnavailable('Logistics could not access the device Keychain. Unlock the device and retry.')
            if operation == 'load':
                length = self.cf.CFDataGetLength(result)
                if length != 32:
                    raise VaultUnavailable('Invalid device encryption key.')
                return c.string_at(self.cf.CFDataGetBytePtr(result), length)
            return None
        finally:
            if result.value:
                self.cf.CFRelease(result)
            for pointer in reversed(owned):
                self.cf.CFRelease(pointer)

    def create(self, identity, key):
        self.perform('create', identity, key)
        return {}

    def load(self, identity, record):
        return self.perform('load', identity)

    def delete(self, identity):
        self.perform('delete', identity)

    def set_label(self, identity, label):
        self.perform('label', identity, label)


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
    def for_app(cls, app):
        from commonUtils.runtime.platform import get_os, OS
        current = get_os()
        if current is OS.ANDROID:
            # noBackupFilesDir is explicitly excluded from Android backup/restore.
            root = Path(str(app._impl.native.getNoBackupFilesDir().getAbsolutePath())) / 'LogisticsCredentials'
            if app.storage_root is not None:  # Native test fixtures get separate keys/data.
                root = app.private_root / 'Credentials'
            return cls(root, AndroidKeys(), 'android')
        if current is OS.IOS:
            vault = cls(app.private_root / 'Credentials', IOSKeys(), 'ios')
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
        descriptor = os.open(self.record, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            import stat
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4096:
                raise VaultUnavailable('Invalid protected-key record.')
            with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                record = json.loads(stream.read(4097))
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
