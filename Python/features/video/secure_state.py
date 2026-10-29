"""Encrypted remote resume records. Device key adapters and crypto stay at host edges."""

import base64
from hashlib import sha256
import json
import secrets
from pathlib import Path
from threading import RLock


def desktop_key(content):
    from features.rclone import desktop_session
    session = desktop_session()
    from services.documents.storage import document_sources

    for source in document_sources(content.provider):
        context = getattr(source, "context", None)
        values = session.credentials(context) if context is not None else None
        if values:
            return sha256(
                b"Logistics video resume v1\0"
                + json.dumps(values, sort_keys=True).encode()
            ).digest()
    raise ValueError("Encrypted resume credentials are unavailable.")


class DesktopCipher:
    def __init__(self, content):
        self.content = content

    def transform(self, data, identity, decode=False):
        from Cryptodome.Cipher import AES

        key = desktop_key(self.content)
        if decode:
            if len(data) < 28:
                raise ValueError("Invalid encrypted video progress.")
            cipher = AES.new(key, AES.MODE_GCM, nonce=data[:12])
            cipher.update(identity.encode())
            return cipher.decrypt_and_verify(data[28:], data[12:28])
        cipher = AES.new(key, AES.MODE_GCM, nonce=secrets.token_bytes(12))
        cipher.update(identity.encode())
        ciphertext, tag = cipher.encrypt_and_digest(data)
        return cipher.nonce + tag + ciphertext


class MobileCipher:
    def __init__(self, app):
        self.app, self.vault, self.lock = app, None, RLock()

    def transform(self, data, identity, decode=False):
        with self.lock:
            return self._transform(data, identity, decode)

    def _transform(self, data, identity, decode=False):
        if self.vault is None:
            from features.rclone.mobile.credential_vault import ProtectedVault
            from commonUtils.runtime.protected_keys import AndroidKeys, IOSKeys
            from commonUtils.runtime.platform import get_os, OS

            if get_os() is OS.ANDROID:
                keys = AndroidKeys(
                    alias_prefix="Logistics.video.", aad_prefix="Logistics video v1:"
                )
                root = (
                    Path(
                        str(
                            self.app._impl.native.getNoBackupFilesDir().getAbsolutePath()
                        )
                    )
                    / "LogisticsVideoState"
                )
                platform = "android"
            else:
                keys = IOSKeys(
                    service="io.github.ispaure.logisticsmobile.video",
                    label="Logistics — video progress",
                    label_prefix="Logistics — ",
                )
                root, platform = Path(self.app.private_root) / "VideoState", "ios"
            self.vault = ProtectedVault(root, keys, platform)
            if platform == "ios":
                from rubicon.objc import ObjCClass

                if (
                    not ObjCClass("NSURL")
                    .fileURLWithPath(str(root))
                    .setResourceValue(
                        True, forKey="NSURLIsExcludedFromBackupKey", error=None
                    )
                ):
                    raise ValueError("Video state could not be excluded from backup.")
        key = self.vault.unlock(create=not decode)
        if key is None:
            raise ValueError("Video state key is unavailable.")
        # Reuse the bounded native AES-GCM primitive with a separate device key
        # and domain-specific identity; no credential package bytes are involved.
        result = self.app.cloud_client.request(
            "unprotect_package" if decode else "protect_package",
            key=key["key"],
            id=identity,
            data=base64.b64encode(data).decode(),
        )
        return base64.b64decode(result, validate=True)


class RemoteProgress:
    def __init__(self, content, root, cipher=None):
        self.content, self.root, self.cipher = (
            content,
            Path(root) / "Remote",
            cipher or DesktopCipher(content),
        )
        provider = content.provider
        namespace = getattr(provider, "identity", None) or str(
            getattr(provider, "config_path", getattr(provider, "root", ""))
        )
        if isinstance(self.cipher, DesktopCipher):
            try:
                # Credential imports use ephemeral session paths. Bind the
                # namespace to the same secret settings as encryption instead.
                namespace = sha256(desktop_key(content)).hexdigest()
            except ValueError:
                pass  # An unavailable resume key must not block the movie.
        identity = [str(namespace), getattr(provider, "remote", ""), content.path]
        self.identity = sha256(
            ("Logistics video progress v1:" + json.dumps(identity)).encode()
        ).hexdigest()
        self.path = self.root / (self.identity + ".bin")
        self.revision = json.dumps(content.source.expected, sort_keys=True)

    def load(self):
        self.content.check_access()
        try:
            if (
                self.root.is_symlink()
                or self.path.is_symlink()
                or self.path.stat().st_size > 8192
            ):
                return 0
            with self.path.open("rb") as stream:
                encrypted = stream.read(8193)
            if len(encrypted) > 8192:
                return 0
            raw = self.cipher.transform(encrypted, self.identity, True)
            record = json.loads(raw)
            if record.get("version") != 1 or record.get("revision") != self.revision:
                return 0
            value = record.get("position", 0)
            return value if type(value) is int and 0 <= value <= 10**10 else 0
        except (OSError, ValueError, TypeError, KeyError):
            return 0

    def save(self, position):
        self.content.check_access()
        data = json.dumps(
            dict(version=1, revision=self.revision, position=position)
        ).encode()
        encrypted = self.cipher.transform(data, self.identity)
        self.content.check_access()
        from commonUtils.persistence import atomic_write_bytes

        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or self.path.is_symlink():
            raise ValueError("Linked video progress is unsupported.")
        atomic_write_bytes(self.path, encrypted)
