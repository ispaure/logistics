"""Host video resume storage; private records are encrypted by their provider."""

from hashlib import sha256
from io import BytesIO
import json
from math import isfinite
from pathlib import Path
from threading import RLock
from dataclasses import asdict

from features.video.session import PlaybackSettings

from services.documents.storage import (
    DocumentPolicy,
    document_writable,
    document_remote,
)


class VideoProgress:
    def __init__(self, content, root, *, remote_cipher=None, app=None):
        self.content, self.root = content, Path(root)
        self.duration = 0
        self.settings = None
        self.position = 0
        self.lock = RLock()
        self.private = not DocumentPolicy.for_provider(content.provider).persistent
        from services.documents.history_controls import PositionLease

        self._position_lease = PositionLease(Path(root).parent)
        self.memory = {}
        self.remote = document_remote(content.provider)
        from services.access_policy import session_only

        # Local content identity is independent of filename, provider root and
        # inode. Read bounded samples through the decoded source (LocalCrypt too).
        self.fingerprint = None
        if not self.remote and hasattr(content, 'open') and hasattr(content, 'size'):
            digest = sha256(('Logistics video samples v1:' + str(content.size)).encode())
            with content.open() as stream:
                for offset in sorted({0, max(0, content.size // 2 - 32768), max(0, content.size - 65536)}):
                    stream.seek(offset)
                    digest.update(stream.read(65536))
            content.check()
            self.fingerprint = digest.hexdigest()
        self.legacy_credential_state = None
        self.credential_state = None
        self.legacy_retired = False
        self.resume_notice = None
        self.remote_cipher = remote_cipher
        if session_only(content.provider):
            from services.documents.credential_state import CredentialState

            self.credential_state = CredentialState(
                content.provider,
                self.fingerprint or content.path,
                Path(root).parent,
                kind="video",
                revision=self.fingerprint or content.source.expected,
                app=app,
                check=content.check_access,
            )
            if self.fingerprint:
                self.legacy_credential_state = CredentialState(
                    content.provider, content.path, Path(root).parent, kind='video',
                    revision=content.source.expected, app=app, check=content.check_access)
            return
        if self.remote:
            from .video_state import RemoteProgress

            self.remote_store = RemoteProgress(content, root, remote_cipher)
            return
        self.revision = json.dumps(self.fingerprint or content.source.expected, sort_keys=True)
        identity = [
            content.provider.storage_id,
            getattr(content.provider, "storage_namespace", ""),
            content.path,
        ]
        self.legacy_key = sha256(json.dumps(identity).encode()).hexdigest() + ".json"
        self.key = (self.fingerprint or sha256(json.dumps(identity).encode()).hexdigest()) + ".json"
        # In LocalCrypt this folder, filename AND payload pass through the
        # provider's encryption. No private identity is written into app state.
        self.path = ".logistics-video/" + self.key
        self.memory = {}

    def load(self):
        with self.lock:
            self.position = self._load()
            return self.position

    def restore_settings(self, record):
        try:
            self.settings = PlaybackSettings.from_dict(record['settings'])
        except (KeyError, TypeError, ValueError):
            self.settings = None

    def _load(self):
        self.duration = 0
        if not self._position_lease.valid():
            return 0
        self.content.check_access() if self.remote else self.content.check()
        if self.credential_state is not None:
            if not self.legacy_retired:
                from .video_migration import retire_legacy

                try:
                    retire_legacy(
                        self.content,
                        self.root,
                        self.credential_state,
                        cleared=bool(self._position_lease.generation),
                        remote_cipher=self.remote_cipher,
                    )
                except (OSError, ValueError):
                    self.resume_notice = "Older saved position could not be upgraded; it was preserved. Playback can continue."
                self.legacy_retired = True
            record = self.credential_state.load()
            if not record and self.legacy_credential_state is not None:
                record = self.legacy_credential_state.load()
                if record:
                    self.credential_state.save(record)
            self.restore_settings(record)
            self.duration = self.valid_duration(record.get("duration", 0))
            value = record.get("position", 0)
            return value if type(value) is int and 0 <= value <= 10**10 else 0
        if self.remote:
            position = self.remote_store.load()
            self.settings = self.remote_store.settings
            self.duration = self.remote_store.duration
            return position
        try:
            legacy = False
            if self.private:
                from commonUtils.runtime.resources.content import ProviderContent

                state_path = self.path
                try:
                    self.content.provider.entry(state_path)
                except FileNotFoundError:
                    state_path = '.logistics-video/' + self.legacy_key
                    legacy = True
                source = ProviderContent(self.content.provider, state_path)
                try:
                    with source.open(state_path) as stream:
                        raw = stream.read(4097)
                finally:
                    source.close()
            else:
                path = self.root / self.key
                if not path.exists() and not path.is_symlink():
                    path = self.root / self.legacy_key
                    legacy = True
                if path.is_symlink():
                    raise ValueError("Linked video resume state is not supported.")
                with path.open("rb") as stream:
                    raw = stream.read(4097)
            if len(raw) > 4096:
                return 0
            record = json.loads(raw)
            if record.get("generation", "") != self._position_lease.generation:
                if self.private:
                    from commonUtils.runtime.resources.mutations import delete_resource

                    try:
                        delete_resource(self.content.provider, self.path)
                    except (OSError, ValueError):
                        self.resume_notice = "An old encrypted checkpoint was ignored; its source does not allow cleanup."
                return 0
            position = record.get("position", 0)
            if (
                record.get("schema") == 1
                and record.get("revision") == (json.dumps(self.content.source.expected, sort_keys=True) if legacy else self.revision)
                and type(position) in (int, float)
                and isfinite(position)
                and 0 <= position <= 10**10
            ):
                self.restore_settings(record)
                self.duration = self.valid_duration(record.get("duration", 0))
                return int(position)
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return 0

    @staticmethod
    def valid_duration(value):
        return value if type(value) is int and 0 <= value <= 10**10 else 0

    def save(self, milliseconds, *, completed=False):
        with self.lock:
            return self._position_lease.publish(
                lambda: self._save(milliseconds, completed=completed)
            )

    def _save(self, milliseconds, *, completed=False):
        if not self._position_lease.valid():
            return
        self.content.check_access() if self.remote else self.content.check()
        if (
            type(milliseconds) not in (int, float)
            or not isfinite(milliseconds)
            or milliseconds < 0
        ):
            raise ValueError("Invalid video position.")
        position = 0 if completed else int(milliseconds)
        self.position = position
        settings = asdict(self.settings) if self.settings is not None else {}
        if self.credential_state is not None:
            self.credential_state.save(dict(position=position, duration=self.valid_duration(self.duration), settings=settings))
            return
        if self.remote:
            self.memory = dict(position=position)
            self.remote_store.settings = self.settings
            self.remote_store.duration = self.valid_duration(self.duration)
            self.remote_store.save(position)
            return
        record = dict(
            settings=settings,
            schema=1,
            revision=self.revision,
            position=position,
            duration=self.valid_duration(self.duration),
            generation=self._position_lease.generation,
        )
        self.memory = record
        if self.private:
            provider = self.content.provider
            if not document_writable(provider):
                raise PermissionError(
                    "Resume is available only for this session on read-only storage."
                )
            try:
                provider.mkdir(".logistics-video")
            except FileExistsError:
                pass
            raw = json.dumps(record).encode()
            try:
                revision = provider.entry(self.path)["revision"]
            except FileNotFoundError:
                provider.create_file(self.path, BytesIO(raw))
            else:
                if hasattr(provider, "replace_bytes"):
                    provider.replace_bytes(self.path, raw, expected_revision=revision)
                else:
                    provider.replace_stream(
                        self.path,
                        lambda stream: stream.write(raw),
                        expected_revision=revision,
                    )
        else:
            from commonUtils.persistence import atomic_write_json

            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write_json(self.root / self.key, record, max_bytes=4096)
