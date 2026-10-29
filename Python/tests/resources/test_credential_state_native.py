"""Real native password-backed metadata and explicit old-password migration."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from commonUtils.runtime.resources.documents import LocalDocuments
from features.rclone.mobile.cloud import CloudClient
from services.documents.credential_state import CredentialState
from services.documents.state_migration import migrate
from services.documents.history_controls import (
    clear_saved_positions,
    clear_recent_files,
)


@unittest.skipUnless(
    os.environ.get("LOGISTICS_MOBILE_BRIDGE"), "Host mobile bridge required"
)
class NativeCredentialStateTests(unittest.TestCase):
    def test_password_change_migrates_positions_bookmarks_and_recent_with_real_native_crypto(
        self,
    ):
        import pyzipper

        with TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / "Credentials.zip"
            client = CloudClient(library=os.environ["LOGISTICS_MOBILE_BRIDGE"])
            client.clear()
            self.addCleanup(client.clear)
            app = SimpleNamespace(private_root=root, cloud_client=client)

            def load(password):
                with pyzipper.AESZipFile(
                    package, "w", encryption=pyzipper.WZ_AES
                ) as archive:
                    archive.setpassword(password.encode())
                    archive.writestr("Drive.txt", "[Drive]\ntype=memory\n")
                client.import_package(
                    LocalDocuments(), package, password, remember=False
                )
                return SimpleNamespace(
                    client=client,
                    remote="Drive",
                    identity=client.connection_identity("Drive"),
                )

            provider = load("previous-password")
            state = CredentialState(
                provider, "Private book.epub", root, kind="epub", app=app
            )
            state.save(dict(page=12, bookmarks=[4, 8]))
            self.assertEqual(state.load(), dict(page=12, bookmarks=[4, 8]))
            old_key = client.package_records[0]["document_cache_id"]
            history = dict(
                version=1,
                credential=old_key,
                open=[],
                recent=[
                    dict(
                        provider="file-reference",
                        resource="x",
                        kind="epub",
                        title="Private book",
                        source=dict(
                            type="remote",
                            identity=provider.identity,
                            remote="Drive",
                            key="Private book.epub",
                        ),
                    )
                ],
            )
            import base64

            encoded = client.request(
                "document_lists_seal",
                id=old_key,
                data=base64.b64encode(json.dumps(history).encode()).decode(),
            )
            cached = root / "CredentialDocumentLists" / old_key / ("a" * 64 + ".zip")
            cached.parent.mkdir(parents=True)
            cached.write_bytes(base64.b64decode(encoded))
            provider = load("updated-password")
            current = CredentialState(
                provider, "Private book.epub", root, kind="epub", app=app
            )
            self.assertEqual(current.load(), {})
            with self.assertRaises(PermissionError):
                current.save(dict(page=0))
            result = migrate(root, "wrong-password", app=app)
            self.assertEqual(result, dict(migrated=0, preserved=5))
            result = migrate(root, "previous-password", app=app)
            self.assertEqual(result, dict(migrated=5, preserved=0))
            self.assertEqual(current.load(), dict(page=12, bookmarks=[4, 8]))
            new_key = client.package_records[0]["document_cache_id"]
            self.assertNotEqual(old_key, new_key)
            self.assertFalse(cached.exists())
            migrated = root / "CredentialDocumentLists" / new_key / cached.name
            decoded = client.request(
                "document_lists_open",
                id=new_key,
                data=base64.b64encode(migrated.read_bytes()).decode(),
            )
            self.assertEqual(
                json.loads(base64.b64decode(decoded))["recent"][0]["title"],
                "Private book",
            )
            client.clear()
            clear_recent_files(root, mobile=True)
            self.assertFalse(list((root / "CredentialDocumentLists").glob("*/*.zip")))
            self.assertTrue(list((root / "ReaderPositions").glob("*.zip")))
            clear_saved_positions(root, mobile=True)
            self.assertFalse(list((root / "ReaderPositions").glob("*.zip")))
            self.assertTrue(list((root / "ReaderBookmarks").glob("*.zip")))
            for path in root.rglob("*.zip"):
                if path == package:
                    continue
                self.assertNotIn(b"Private book", path.read_bytes())
