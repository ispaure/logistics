"""Password-bound private reader state. No plaintext or device-key fallback.

The credential service owns unlocked ZIP passwords. This layer owns only bounded
ciphertext files and document/source binding, shared by every reader format.
"""

import base64
from hashlib import sha256
from io import BytesIO
import json
import hmac
import secrets
from pathlib import Path
from threading import RLock

from services.documents.storage import document_sources


class PreviousPasswordRequired(PermissionError):
    """Existing protected state needs migration; do not fall back or overwrite it."""


LIMIT = 128 * 1024
_io_lock = RLock()


def _revision_value(value):
    if isinstance(value, bytes):
        # Offline copy revisions include the original record bytes. Bind to
        # their content without retaining those bytes in the state envelope.
        return {"bytes_sha256": sha256(value).hexdigest()}
    raise TypeError(f"Unsupported reader revision value: {type(value).__name__}")


def sources(provider):
    seen = set()
    pending = [provider]
    while pending:
        source = pending.pop()
        if source is None or id(source) in seen:
            continue
        seen.add(id(source))
        yield source
        pending.extend(getattr(source, key, None) for key in ("provider", "resource"))


class DesktopCredentialCipher:
    def __init__(self, provider):
        self.provider = provider

    def credentials(self):
        from features.rclone import desktop_session

        session = desktop_session()

        for source in sources(self.provider):
            context = getattr(source, "context", None) or getattr(
                source, "config_path", None
            )
            if context is not None:
                values = session.registry.state_credentials(context)
                if values is not None:
                    return values
        raise PermissionError(
            "Unlock the password-protected credential ZIP to save reader state."
        )

    @property
    def identity(self):
        identity, secret = self.credentials()
        try:
            return identity
        finally:
            secret[:] = b"\0" * len(secret)

    def transform(self, data, decode=False):
        import pyzipper

        _, secret = self.credentials()
        try:
            buffer = BytesIO(data if decode else b"")
            if decode:
                with pyzipper.AESZipFile(buffer) as archive:
                    entries = archive.infolist()
                    if (
                        len(entries) != 1
                        or entries[0].filename != "state.json"
                        or entries[0].file_size > LIMIT
                        or not entries[0].flag_bits & 1
                        or getattr(entries[0], "wz_aes_strength", None) != 3
                    ):
                        raise ValueError("Invalid encrypted reader state.")
                    archive.setpassword(bytes(secret))
                    raw = archive.read(entries[0])
                    if len(raw) > LIMIT:
                        raise ValueError("Reader state is too large.")
                    return raw
            if len(data) > LIMIT:
                raise ValueError("Reader state is too large.")
            with pyzipper.AESZipFile(
                buffer, "w", encryption=pyzipper.WZ_AES
            ) as archive:
                archive.setpassword(bytes(secret))
                archive.writestr("state.json", data)
            return buffer.getvalue()
        except (pyzipper.BadZipFile, RuntimeError, EOFError) as error:
            raise ValueError(
                "Reader state authentication failed; the original was preserved."
            ) from error
        finally:
            secret[:] = b"\0" * len(secret)


class MobileCredentialCipher:
    def __init__(self, provider, app):
        self.provider, self.app = provider, app

    def credentials(self):
        for source in sources(self.provider):
            client = getattr(source, "client", None)
            remote = getattr(source, "remote", None)
            identity = getattr(source, "identity", None)
            if client is None or remote is None:
                continue
            if identity is None:
                identity = client.connection_identity(remote)
            if client is not getattr(self.app, "cloud_client", None):
                continue
            for record in getattr(client, "package_records", ()):
                if (
                    not record.get("saved")
                    and record.get("document_cache_id")
                    and identity
                    in (
                        *record.get("identities", {}).values(),
                        *record.get("crypt_identities", {}).values(),
                    )
                ):
                    return client, record["document_cache_id"]
        raise PermissionError(
            "Unlock the password-protected credential ZIP to save reader state."
        )

    @property
    def identity(self):
        return self.credentials()[1]

    def transform(self, data, decode=False):
        client, identity = self.credentials()
        value = client.request(
            "document_lists_open" if decode else "document_lists_seal",
            id=identity,
            data=base64.b64encode(data).decode(),
        )
        return base64.b64decode(value, validate=True)


class CredentialState:
    def __init__(
        self,
        provider,
        path,
        root,
        *,
        kind,
        revision=None,
        app=None,
        check=None,
        section="positions",
    ):
        self.base = Path(root)
        self.provider, self.document, self.root = (
            provider,
            str(path),
            Path(root)
            / ("ReaderPositions" if section == "positions" else "ReaderBookmarks"),
        )
        self.section, self.memory, self.locked_state = section, {}, False
        self.bookmarks = (
            CredentialState(
                provider,
                path,
                root,
                kind=kind,
                revision=revision,
                app=app,
                check=check,
                section="bookmarks",
            )
            if section == "positions"
            else None
        )
        self.kind, self.revision = kind, json.dumps(revision, sort_keys=True, default=_revision_value)
        self.check = check or (lambda: self._check())
        self.cipher = (
            MobileCredentialCipher(provider, app)
            if app is not None
            else DesktopCredentialCipher(provider)
        )
        self.generation = self._generation()

    def _check(self):
        for source in sources(self.provider):
            check = getattr(source, "check", None) or getattr(
                source, "_check_active", None
            )
            if check is not None:
                check()

    def _generation(self):
        try:
            return (self.root / "generation").read_text()[:64]
        except FileNotFoundError:
            return ""

    def authority(self):
        for source in sources(self.provider):
            client, remote = (
                getattr(source, "client", None),
                getattr(source, "remote", None),
            )
            if client is not None and remote is not None:
                return client.connection_identity(remote)
            context = getattr(source, "context", None) or getattr(
                source, "config_path", None
            )
            if context is None:
                continue
            from features.rclone import desktop_session

            session = desktop_session()

            authority = (
                session.registry.state_authority(context)
                if context is not None
                else None
            )
            if authority is not None:
                return authority
            values = session.credentials(context) if context is not None else None
            if values:
                return sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        raise PermissionError("The credential source is unavailable.")

    def locator_key(self, *, create=False):
        authority = self.authority()
        directory = self.base / "ReaderKeys" / self.section
        key_id = sha256(json.dumps([authority, self.generation]).encode()).hexdigest()
        path = directory / (key_id + ".zip")
        if directory.is_symlink() or path.is_symlink():
            raise ValueError("Linked private reader keys are not supported.")
        try:
            with path.open("rb") as stream:
                encrypted = stream.read(LIMIT + 2049)
        except FileNotFoundError:
            if not create:
                raise
            record = dict(
                version=1,
                authority=authority,
                key=base64.b64encode(secrets.token_bytes(32)).decode(),
            )
            encrypted = self.cipher.transform(json.dumps(record).encode())
            self.check()
            from commonUtils.persistence import atomic_write_bytes

            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write_bytes(path, encrypted, overwrite=False)
        try:
            if len(encrypted) > LIMIT + 2048:
                raise ValueError("Private reader key record exceeds limits.")
            record = json.loads(self.cipher.transform(encrypted, True))
            if (
                not isinstance(record, dict)
                or record.get("version") != 1
                or record.get("authority") != authority
            ):
                raise ValueError("Invalid private reader key record.")
            key = base64.b64decode(record["key"], validate=True)
            if len(key) != 32:
                raise ValueError("Invalid private reader key length.")
            return bytearray(key)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            raise PreviousPasswordRequired(
                "Protected reader history needs the previous ZIP password. Use Settings → Reader history migration."
            ) from error

    def binding(self, *, create=False):
        self.cipher.identity
        source = next(
            (
                getattr(s, "storage_namespace", None)
                for s in sources(self.provider)
                if getattr(s, "storage_namespace", None)
            ),
            "",
        )
        remote = next(
            (
                getattr(s, "remote", None)
                for s in sources(self.provider)
                if getattr(s, "remote", None)
            ),
            "",
        )
        key = self.locator_key(create=create)
        try:
            payload = json.dumps(
                [
                    self.authority(),
                    str(source),
                    remote,
                    self.document,
                    self.kind,
                    self.section,
                ]
            ).encode()
            return hmac.new(key, payload, "sha256").hexdigest()
        finally:
            key[:] = b"\0" * len(key)

    def load(self):
        state = self._load()
        if self.bookmarks is not None:
            state.update(self.bookmarks.load())
            self.locked_state = self.locked_state or self.bookmarks.locked_state
        return state

    def _load(self):
        self.check()
        with _io_lock:
            if self.generation != self._generation():
                return {}
            try:
                identity = self.binding()
                path = self.root / (identity + ".zip")
                if self.root.is_symlink() or path.is_symlink():
                    raise ValueError("Linked reader state is not supported.")
                with path.open("rb") as stream:
                    encrypted = stream.read(LIMIT + 2049)
                if len(encrypted) > LIMIT + 2048:
                    raise ValueError("Encrypted reader state exceeds limits.")
                record = json.loads(self.cipher.transform(encrypted, True))
                if not isinstance(record, dict):
                    raise ValueError("Invalid reader state.")
                self.check()
                if (
                    record.get("version") != 1
                    or record.get("identity") != identity
                    or record.get("revision") != self.revision
                    or not isinstance(record.get("state"), dict)
                ):
                    return {}
                self.locked_state = False
                return record["state"]
            except FileNotFoundError:
                return dict(self.memory)
            except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                self.locked_state = True
                return dict(self.memory)

    def save(self, state):
        if self.bookmarks is not None:
            marked = {
                key: state[key]
                for key in ("bookmarks", "epub_bookmarks")
                if key in state
            }
            if marked:
                try:
                    self.bookmarks.save(marked)
                except PreviousPasswordRequired:
                    self.locked_state = (
                        True  # Keep old bookmarks, but permit a newly reset position.
                    )

            state = {
                key: value
                for key, value in state.items()
                if key not in ("bookmarks", "epub_bookmarks")
            }
        self.check()
        with _io_lock:
            if self.generation != self._generation():
                return  # A reader opened before Clear must not resurrect its checkpoint.
            try:
                identity = self.binding(create=True)
            except PreviousPasswordRequired:
                self.locked_state = True
                raise
            except PermissionError:
                self.memory = dict(state)
                return  # Passwordless credentials have no persistent fallback.
            path = self.root / (identity + ".zip")
            if path.exists():
                try:
                    with path.open("rb") as stream:
                        existing = stream.read(LIMIT + 2049)
                    if len(existing) > LIMIT + 2048:
                        raise ValueError("Reader state exceeds limits.")
                    original = json.loads(self.cipher.transform(existing, True))
                    if (
                        not isinstance(original, dict)
                        or original.get("identity") != identity
                        or original.get("version") != 1
                    ):
                        raise ValueError(
                            "Saved reader state belongs to a different document."
                        )
                except (ValueError, RuntimeError, OSError) as error:
                    self.locked_state = True
                    raise PermissionError(
                        "Saved reader state needs the previous ZIP password. Use Settings → Reader history migration."
                    ) from error
            raw = json.dumps(
                dict(
                    version=1,
                    identity=identity,
                    authority=self.authority(),
                    revision=self.revision,
                    state=state,
                )
            ).encode()
            if len(raw) > LIMIT:
                raise ValueError("Reader state exceeds limits.")
            encrypted = self.cipher.transform(raw)
            self.check()
            from commonUtils.persistence import atomic_write_bytes

            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = self.root / (identity + ".zip")
            if self.root.is_symlink() or path.is_symlink():
                raise ValueError("Linked reader state is not supported.")
            atomic_write_bytes(path, encrypted)


def clear_positions(root):
    """Delete ciphertext without any credential; fence off in-flight/old readers."""
    from secrets import token_hex
    from commonUtils.persistence import atomic_write_bytes

    directory = Path(root) / "ReaderPositions"
    with _io_lock:
        if directory.is_symlink():
            raise ValueError("Linked reader state is not supported.")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write_bytes(directory / "generation", token_hex(32).encode())
        key_directory = Path(root) / "ReaderKeys" / "positions"
        if key_directory.is_symlink() or key_directory.parent.is_symlink():
            raise ValueError("Linked reader keys were preserved.")
        for path in key_directory.glob("*.zip"):
            if (
                path.is_symlink()
                or len(path.stem) != 64
                or any(c not in "0123456789abcdef" for c in path.stem)
            ):
                raise ValueError("Unexpected reader key file was preserved.")
            path.unlink()
        for path in directory.glob("*.zip"):
            if (
                path.is_symlink()
                or len(path.stem) != 64
                or any(c not in "0123456789abcdef" for c in path.stem)
            ):
                raise ValueError("Unexpected reader state file; it was preserved.")
            path.unlink()
