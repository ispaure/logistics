"""Supply pypdf's pinned AES interface using installed/system crypto providers.

Desktop already bundles Cryptodome for encrypted archives; mobile uses JCE or
CommonCrypto. No keys/passwords or decrypted PDF bytes are written to disk.
"""
from functools import lru_cache
import secrets
import sys


def aes(key, data, *, iv=None, decrypt=False):
    if len(key) not in (16, 24, 32) or len(data) % 16 or (iv is not None and len(iv) != 16):
        raise ValueError('Invalid AES parameters.')
    if not data:
        return b''
    if sys.platform == 'android' or hasattr(sys, 'getandroidapilevel'):
        from java import jclass, jarray, jbyte
        array = lambda value: jarray(jbyte)([v if v < 128 else v - 256 for v in value])
        cipher = jclass('javax.crypto.Cipher').getInstance('AES/' + ('ECB' if iv is None else 'CBC') + '/NoPadding')
        secret = jclass('javax.crypto.spec.SecretKeySpec')(array(key), 'AES')
        if iv is None:
            cipher.init(2 if decrypt else 1, secret)
        else:
            cipher.init(2 if decrypt else 1, secret, jclass('javax.crypto.spec.IvParameterSpec')(array(iv)))
        return bytes(int(v) & 255 for v in cipher.doFinal(array(data)))
    if sys.platform in ('ios', 'darwin'):
        return apple_aes(key, data, iv=iv, decrypt=decrypt)
    from Cryptodome.Cipher import AES
    cipher = AES.new(key, AES.MODE_ECB) if iv is None else AES.new(key, AES.MODE_CBC, iv)
    return cipher.decrypt(data) if decrypt else cipher.encrypt(data)


def apple_aes(key, data, *, iv=None, decrypt=False):
    import ctypes as c
    # CCCrypt is provided by the OS on macOS and iOS; padding is managed by
    # pypdf's stream wrapper, and the low-level hash/key routines use NoPadding.
    function = _apple_function()
    output, count = c.create_string_buffer(len(data) + 16), c.c_size_t()
    status = function(1 if decrypt else 0, 0, 2 if iv is None else 0,
                      key, len(key), iv, data, len(data), output, len(output), c.byref(count))
    if status:
        raise ValueError('System AES operation failed.')
    return output.raw[:count.value]


@lru_cache(maxsize=1)
def _apple_function():
    import ctypes as c
    function = c.CDLL('/usr/lib/system/libcommonCrypto.dylib').CCCrypt
    function.restype = c.c_int32
    function.argtypes = [c.c_uint32, c.c_uint32, c.c_uint32, c.c_void_p, c.c_size_t,
                         c.c_void_p, c.c_void_p, c.c_size_t, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    return function


class CryptAES:
    def __init__(self, key):
        self.key = key

    def encrypt(self, data):
        iv = secrets.token_bytes(16)
        n = 16 - len(data) % 16
        return iv + aes(self.key, data + bytes([n]) * n, iv=iv)

    def decrypt(self, data, *, strict=True):
        from pypdf.errors import PdfStreamError
        if len(data) < 16:
            raise PdfStreamError('Truncated AES initialization vector.')
        iv, encrypted = data[:16], data[16:]
        if not encrypted:
            return b''
        if len(encrypted) % 16:
            if strict:
                raise PdfStreamError('Truncated AES stream.')
            n = 16 - len(encrypted) % 16
            encrypted += bytes([n]) * n
        decoded = aes(self.key, encrypted, iv=iv, decrypt=True)
        n = decoded[-1]
        if not 1 <= n <= 16 or decoded[-n:] != bytes([n]) * n:
            if strict:
                raise PdfStreamError('Invalid AES padding.')
            return decoded[:-n] if n else b''
        return decoded[:-n]


def enable_aes():
    """Extend only pypdf's missing-AES fallback; leave installed providers alone."""
    from pypdf import _crypt_providers as providers, _encryption as encryption
    if providers.crypt_provider[0] != 'local_crypt_fallback':
        return
    functions = dict(CryptAES=CryptAES,
        aes_ecb_encrypt=lambda key, data: aes(key, data),
        aes_ecb_decrypt=lambda key, data: aes(key, data, decrypt=True),
        aes_cbc_encrypt=lambda key, iv, data: aes(key, data, iv=iv),
        aes_cbc_decrypt=lambda key, iv, data: aes(key, data, iv=iv, decrypt=True))
    for name, value in functions.items():
        setattr(providers, name, value)
        setattr(encryption, name, value)
    providers.crypt_provider = ('system-AES', '1')
