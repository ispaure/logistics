"""Explicit old-password migration; preserve unrecognized or inaccessible files."""

import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile, BadZipFile

from commonUtils.persistence import atomic_write_bytes
from .credential_state import LIMIT, DesktopCredentialCipher, _io_lock


def _member(data):
    if len(data) > LIMIT + 2048:
        raise ValueError("Reader state exceeds limits.")
    with ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) != 1 or entries[0].filename not in (
            "state.json",
            "entries.json",
        ):
            raise ValueError("Not a reader-state archive.")
        member = entries[0]
        if member.file_size > LIMIT or not member.flag_bits & 1:
            raise ValueError("Invalid encrypted reader state.")
        extra, strength = member.extra, None
        while len(extra) >= 4:
            tag, size = (
                int.from_bytes(extra[:2], "little"),
                int.from_bytes(extra[2:4], "little"),
            )
            if size > len(extra) - 4:
                raise ValueError("Invalid encrypted reader state.")
            value, extra = extra[4 : 4 + size], extra[4 + size :]
            if tag == 0x9901 and len(value) == 7:
                strength = value[4]
        if strength != 3:
            raise ValueError("Reader state must use AES-256 ZIP encryption.")
        return member.filename


def _desktop_open(data, password, member):
    import pyzipper

    try:
        with pyzipper.AESZipFile(BytesIO(data)) as archive:
            archive.setpassword(password.encode())
            raw = archive.read(member)
            if len(raw) > LIMIT:
                raise ValueError("Reader state exceeds limits.")
            return raw
    except pyzipper.BadZipFile as error:
        raise ValueError("Unreadable reader state was preserved.") from error


def migrate(root, previous_password, *, app=None):
    """Re-encrypt only state matching currently unlocked credential sources."""
    if not previous_password:
        raise ValueError("Enter the previous credential ZIP password.")
    root = Path(root)
    candidates = []
    if app is None:
        from features.rclone import desktop_session

        session = desktop_session()

        for context in session.paths():
            cipher = DesktopCredentialCipher(SimpleNamespace(context=context))
            try:
                cipher.identity
                settings = session.credentials(context)
                authority = sha256(
                    json.dumps(settings, sort_keys=True).encode()
                ).hexdigest()
                candidates.append(
                    (cipher, {authority}, session.revocation_check(context))
                )
            except (OSError, ValueError):
                continue
    else:
        from .credential_state import MobileCredentialCipher

        client = getattr(app, "cloud_client", None)
        generation = getattr(client, "generation", None)
        for record in getattr(client, "package_records", ()):
            if record.get("saved") or not record.get("document_cache_id"):
                continue
            identities = dict(
                record.get("identities", {}), **record.get("crypt_identities", {})
            )
            if not identities:
                continue
            remote, identity = next(iter(identities.items()))
            cipher = MobileCredentialCipher(
                SimpleNamespace(client=client, remote=remote, identity=identity), app
            )
            candidates.append(
                (
                    cipher,
                    set(identities.values()),
                    lambda: client is not app.cloud_client
                    or generation != client.generation,
                )
            )
    if not candidates:
        raise ValueError("Unlock the updated password-protected credential ZIP first.")
    migrated, preserved = 0, 0
    files = [
        *(root / "ReaderKeys" / "positions").glob("*.zip"),
        *(root / "ReaderKeys" / "bookmarks").glob("*.zip"),
        *(root / "ReaderPositions").glob("*.zip"),
        *(root / "ReaderBookmarks").glob("*.zip"),
    ]
    if app is not None:
        files += list((root / "CredentialDocumentLists").glob("*/*.zip"))
    from features.rclone.mobile.document_lists import _cache_io_lock

    with _io_lock, _cache_io_lock:
        for path in files:
            try:
                if path.is_symlink() or path.parent.is_symlink():
                    raise ValueError("Linked reader state was preserved.")
                with path.open("rb") as stream:
                    data = stream.read(LIMIT + 2049)
                try:
                    member = _member(data)
                except BadZipFile as error:
                    raise ValueError(
                        "Invalid encrypted history was preserved."
                    ) from error
                if app is None:
                    raw = _desktop_open(data, previous_password, member)
                else:
                    with path.open("rb") as stream:
                        result = app.cloud_client.request(
                            "file_archive",
                            fd=stream.fileno(),
                            password=previous_password,
                            member=member,
                        )
                    raw = base64.b64decode(result["data"], validate=True)
                    if len(raw) > LIMIT:
                        raise ValueError("Reader state exceeds limits.")
                record = json.loads(raw)
                if not isinstance(record, dict):
                    raise ValueError("Invalid reader state was preserved.")
                chosen = None
                for cipher, authorities, revoked in candidates:
                    if record.get("authority") in authorities:
                        chosen = cipher, revoked
                        break
                    if record.get("version") == 1 and set(record) == {
                        "version",
                        "credential",
                        "open",
                        "recent",
                    }:
                        if not all(isinstance(record[field], list) for field in ("open", "recent")):
                            raise ValueError("Invalid document history was preserved.")
                        entries = [*record["open"], *record["recent"]]
                        if entries and all(
                            isinstance(item, dict)
                            and isinstance(item.get("source"), dict)
                            and item["source"].get("identity") in authorities
                            for item in entries
                        ):
                            chosen = cipher, revoked
                            break
                if chosen is None:
                    raise ValueError("Matching credential source is not unlocked.")
                cipher, revoked = chosen
                target = path
                if "credential" in record:
                    record["credential"] = cipher.identity
                    target = path.parent.parent / cipher.identity / path.name
                    if target != path and target.exists():
                        if target.is_symlink():
                            raise ValueError("Linked history target was preserved.")
                        with target.open("rb") as stream:
                            current = json.loads(
                                cipher.transform(stream.read(LIMIT + 2049), True)
                            )
                        if current.get("credential") != cipher.identity:
                            raise ValueError(
                                "History target belongs to different credentials."
                            )
                        for field, limit in (("open", 32), ("recent", 10)):
                            merged, seen = [], set()
                            for item in sorted(
                                [*current[field], *record[field]],
                                key=lambda value: value.get("opened", 0),
                                reverse=True,
                            ):
                                identity = item["resource"]
                                if identity not in seen:
                                    merged.append(item)
                                    seen.add(identity)
                            record[field] = merged[:limit]
                encrypted = cipher.transform(json.dumps(record).encode())
                if json.loads(cipher.transform(encrypted, True)) != record:
                    raise ValueError("Migrated state verification failed.")
                if revoked():
                    raise PermissionError("Credentials changed during migration.")
                if path.read_bytes() != data:
                    raise ValueError("Reader state changed during migration.")
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if target.is_symlink() or target.parent.is_symlink():
                    raise ValueError("Linked target was preserved.")
                atomic_write_bytes(target, encrypted)
                if target != path:
                    path.unlink()
                migrated += 1
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                preserved += 1
    return dict(migrated=migrated, preserved=preserved)
