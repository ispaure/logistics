"""Real password encryption, locked clearing, migration and overwrite guards."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from features.rclone import session
from services.documents.credential_state import CredentialState
from services.documents.history_controls import (
    clear_saved_positions,
    clear_recent_files,
)
from services.documents.state_migration import migrate


class CredentialReaderStateTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.context = self.root / "credentials.session"
        self.addCleanup(session.forget, self.context)
        self.settings = {
            "Secret": dict(
                type="crypt", password="synthetic-crypt-key", remote="Drive:folder"
            ),
            "Drive": dict(type="memory"),
        }
        self.unlock("old-password")

    def unlock(self, password, *, settings=None):
        session.remember(
            self.context,
            settings or self.settings,
            state_password=password,
            state_identity="a" * 64,
        )
        self.provider = SimpleNamespace(
            context=self.context, remote="Secret", private=True, session_only=True
        )

    def state(self, kind="epub"):
        return CredentialState(
            self.provider, "private-title." + kind, self.root, kind=kind, revision=(1,)
        )

    def test_formats_are_password_encrypted_and_not_crypt_or_device_key_only(self):
        import pyzipper

        for kind in ("epub", "comic", "pdf", "video", "md"):
            with self.subTest(kind=kind):
                store = self.state(kind)
                store.save(dict(page=17, private_marker="secret-location"))
                path = store.root / (store.binding() + ".zip")
                raw = path.read_bytes()
                self.assertNotIn(b"secret-location", raw)
                self.assertNotIn(b"private-title", raw)
                with pyzipper.AESZipFile(path) as archive:
                    archive.setpassword(b"synthetic-crypt-key")
                    with self.assertRaises(RuntimeError):
                        archive.read("state.json")
                self.assertEqual(self.state(kind).load()["page"], 17)
        session.forget(self.context)
        # Keys are removed, not recoverable from the stored remote settings.
        self.assertIsNone(session.registry.state_credentials(self.context))
        for path in (self.root / "ReaderPositions").glob("*.zip"):
            self.assertTrue(path.exists())

    def test_password_change_preserves_old_state_until_explicit_verified_migration(
        self,
    ):
        store = self.state("video")
        store.save(dict(position=123456))
        path = store.root / (store.binding() + ".zip")
        original = path.read_bytes()
        self.unlock("new-password")
        changed = self.state("video")
        self.assertEqual(changed.load(), {})
        self.assertTrue(changed.locked_state)
        with self.assertRaises(PermissionError):
            changed.save(dict(position=0))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(
            migrate(self.root, "wrong-password"), dict(migrated=0, preserved=2)
        )
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(
            migrate(self.root, "old-password"), dict(migrated=2, preserved=0)
        )
        self.assertEqual(self.state("video").load(), dict(position=123456))
        self.assertNotEqual(path.read_bytes(), original)

    def test_migration_will_not_assign_another_accounts_history(self):
        store = self.state()
        store.save(dict(page=8))
        self.unlock("new-password", settings={"Other": dict(type="memory")})
        self.assertEqual(
            migrate(self.root, "old-password"), dict(migrated=0, preserved=2)
        )

    def test_clear_positions_while_locked_retains_bookmarks_and_recents_and_fences_old_readers(
        self,
    ):
        store = self.state()
        store.save(dict(page=8, bookmarks=[2, 7]))
        (self.root / "Readers").mkdir()
        recent = self.root / "Readers/recent.json"
        recent.write_text('["ordinary.epub"]')
        session.forget(self.context)
        clear_saved_positions(self.root)
        self.assertFalse(list((self.root / "ReaderPositions").glob("*.zip")))
        self.assertTrue(list((self.root / "ReaderBookmarks").glob("*.zip")))
        self.assertEqual(recent.read_text(), '["ordinary.epub"]')
        self.unlock("old-password")
        store.save(dict(page=99))
        self.assertFalse(list((self.root / "ReaderPositions").glob("*.zip")))
        self.assertEqual(self.state().load(), dict(bookmarks=[2, 7]))

    def test_lost_previous_password_can_reset_positions_without_erasing_old_bookmarks(
        self,
    ):
        self.state().save(dict(page=8, bookmarks=[2, 7]))
        self.unlock("replacement-password")
        clear_saved_positions(self.root)
        fresh = self.state()
        fresh.save(dict(page=3, bookmarks=[]))
        self.assertEqual(self.state().load().get("page"), 3)
        self.assertTrue(list((self.root / "ReaderBookmarks").glob("*.zip")))
        self.assertEqual(
            migrate(self.root, "old-password"), dict(migrated=2, preserved=2)
        )
        self.assertEqual(self.state().load(), dict(page=3, bookmarks=[2, 7]))

    def test_clear_recents_does_not_clear_positions(self):
        store = self.state()
        store.save(dict(page=8))
        (self.root / "Readers").mkdir()
        (self.root / "Readers/recent.json").write_text('["ordinary.epub"]')
        clear_recent_files(self.root)
        self.assertEqual((self.root / "Readers/recent.json").read_text(), "[]")
        self.assertEqual(self.state().load()["page"], 8)

    def test_passwordless_session_has_ram_only_state(self):
        session.remember(self.context, self.settings)
        store = self.state()
        store.save(dict(page=8))
        self.assertEqual(store.load(), dict(page=8))
        self.assertFalse((self.root / "ReaderPositions").exists())

    def test_tampered_ciphertext_is_preserved_and_cannot_be_overwritten(self):
        store = self.state()
        store.save(dict(page=8))
        path = store.root / (store.binding() + ".zip")
        raw = path.read_bytes()
        path.write_bytes(raw[: len(raw) // 2])
        self.assertEqual(store.load(), {})
        with self.assertRaises((ValueError, PermissionError)):
            store.save(dict(page=0))
        self.assertEqual(path.read_bytes(), raw[: len(raw) // 2])
