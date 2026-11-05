"""Android AES bridge bytes follow Chaquopy's documented buffer contract."""
from array import array
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS, ModuleType
import unittest
from unittest.mock import patch

from Cryptodome.Cipher import AES
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
SOURCE = Path(__file__).resolve().parents[2] / 'features/notebooks/pdf_crypto.py'


def load_crypto(source=SOURCE):
    spec = importlib.util.spec_from_file_location('notebook_crypto_under_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BufferBytes(array):
    """Java primitive arrays expose a buffer; no per-element JNI is needed."""
    def __iter__(self):
        raise AssertionError('The AES bridge must not iterate Java byte[] elements')


def java_fixture():
    converted = []
    def jarray(element):
        def create(value):
            if not isinstance(value, (bytes, bytearray)):
                raise AssertionError('Pass bytes directly, not a Python signed-integer list')
            converted.append(bytes(value))
            result = BufferBytes('b')
            result.frombytes(value)  # Same signed buffer layout as Java byte[].
            return result
        return create
    class Cipher:
        @staticmethod
        def getInstance(transformation):
            return Cipher(transformation)
        def __init__(self, transformation):
            self.transformation = transformation
        def init(self, direction, key, iv=None):
            self.decrypt = direction == 2
            self.cipher = AES.new(key.key, AES.MODE_ECB) if iv is None else AES.new(key.key, AES.MODE_CBC, iv.iv)
        def doFinal(self, data):
            result = self.cipher.decrypt(bytes(data)) if self.decrypt else self.cipher.encrypt(bytes(data))
            buffer = BufferBytes('b')
            buffer.frombytes(result)
            return buffer
    classes = {
        'javax.crypto.Cipher': Cipher,
        'javax.crypto.spec.SecretKeySpec': lambda key, algorithm: NS(key=bytes(key)),
        'javax.crypto.spec.IvParameterSpec': lambda iv: NS(iv=bytes(iv)),
    }
    module = ModuleType('java')
    module.jclass = classes.__getitem__
    module.jarray = jarray
    module.jbyte = object()
    return module, converted


class AndroidCryptoBridgeTests(unittest.TestCase):
    def setUp(self):
        self.crypto = load_crypto()
        self.crypto.sys = NS(platform='android')
        self.java, self.converted = java_fixture()
        self.bridge = patch.dict(sys.modules, java=self.java)
        self.bridge.start()
        self.addCleanup(self.bridge.stop)

    def test_nist_ecb_and_cbc_vectors_use_bulk_buffers_both_directions(self):
        key = bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')
        plain = bytes.fromhex('6bc1bee22e409f96e93d7e117393172a')
        for iv, expected in ((None, '3ad77bb40d7a3660a89ecaf32466ef97'),
                (bytes(range(16)), '7649abac8119b246cee98e9b12e9197d')):
            with self.subTest(iv=iv):
                encrypted = self.crypto.aes(key, plain, iv=iv)
                self.assertEqual(encrypted.hex(), expected)
                self.assertEqual(self.crypto.aes(key, encrypted, iv=iv, decrypt=True), plain)

    def test_all_unsigned_bytes_and_aes_key_lengths_roundtrip_without_iteration(self):
        plain = bytes(range(256)) * 32
        for length in (16, 24, 32):
            key = bytes(range(length))
            for iv in (None, bytes(range(16))):
                with self.subTest(length=length, cbc=iv is not None):
                    encrypted = self.crypto.aes(key, plain, iv=iv)
                    self.assertIsInstance(encrypted, bytes)
                    self.assertEqual(len(encrypted), len(plain))
                    self.assertEqual(self.crypto.aes(key, encrypted, iv=iv, decrypt=True), plain)
        self.assertIn(plain, self.converted)

    def test_actual_r6_fixture_wrong_retry_unlock_and_ciphertext_preservation(self):
        from contextlib import ExitStack
        from io import BytesIO
        from pypdf import PdfReader
        from pypdf import _encryption as encryption
        from features.notebooks.editor import Editor
        from features.notebooks.notebook import Notebook
        from features.notebooks.pdf_crypto import enable_aes
        enable_aes()  # Initialize the pinned fallback before scoped bridge hooks.
        fixture = Path(__file__).resolve().parents[3] / 'mobile_build/native_tests/tests/logisticsmobile/notebook-image-fixture.rmdoc'
        book = Notebook.read(fixture.read_bytes())
        original = book.members[book.id + '.pdf']
        editor = Editor(book)
        crypto = self.crypto
        hooks = dict(CryptAES=crypto.CryptAES,
            aes_ecb_encrypt=lambda key, data: crypto.aes(key, data),
            aes_ecb_decrypt=lambda key, data: crypto.aes(key, data, decrypt=True),
            aes_cbc_encrypt=lambda key, iv, data: crypto.aes(key, data, iv=iv),
            aes_cbc_decrypt=lambda key, iv, data: crypto.aes(key, data, iv=iv, decrypt=True))
        with ExitStack() as stack:
            for name, function in hooks.items():
                stack.enter_context(patch.object(encryption, name, function))
            self.assertIsNone(editor.pdf_data())
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'Incorrect PDF password'):
                    editor.pdf_data('wrong-password')
                self.assertIsNone(editor.pdf_data())
            unlocked = editor.pdf_data('image-qa-password')
            reader = PdfReader(BytesIO(unlocked))
            self.assertFalse(reader.is_encrypted)
            self.assertEqual(reader.pages[0].get_contents().get_data(), b'.9 .3 .15 rg 0 0 420 560 re f')
            self.assertEqual(book.members[book.id + '.pdf'], original)
            saved = Notebook.read(book.to_bytes())
            self.assertEqual(saved.members[saved.id + '.pdf'], original)
            self.assertIsNone(Editor(saved).pdf_data())
            self.assertGreater(len(self.converted), 100, 'Actual R6 hashing must use the scoped Android bridge')

    def test_empty_and_invalid_inputs_do_not_enter_java_cipher(self):
        self.assertEqual(self.crypto.aes(bytes(16), b''), b'')
        for key, data, iv in ((bytes(15), bytes(16), None), (bytes(16), b'partial', None),
                (bytes(16), bytes(16), bytes(15))):
            with self.assertRaises(ValueError):
                self.crypto.aes(key, data, iv=iv)
        self.assertEqual(self.converted, [])


if __name__ == '__main__':
    unittest.main()
