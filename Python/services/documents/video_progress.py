"""Adapt playback time and per-title options to the shared document checkpoint."""

from dataclasses import asdict
from hashlib import sha256
from math import isfinite
from pathlib import Path
from threading import RLock

from features.video.session import PlaybackSettings
from services.documents.storage import DocumentPolicy, document_remote

LOCKED_HISTORY = 'Saved video progress is locked. Use Reader History to migrate it with the previous ZIP password.'


class VideoProgress:
    def __init__(self, content, root, *, remote_cipher=None, app=None):
        self.content, self.root = content, Path(root)
        self.duration = 0
        self._settings = None
        self.setting_overrides = {}
        self.position = 0
        self.lock = RLock()
        self.private = not DocumentPolicy.for_provider(content.provider).persistent
        self.remote = document_remote(content.provider)
        self.resume_notice = None
        self.remote_cipher = remote_cipher
        self.app = app
        self.state = None
        self.fingerprint = None
        if not self.remote and hasattr(content, 'open') and hasattr(content, 'size'):
            # Preserve the existing sampled fingerprint, including decoded
            # LocalCrypt bytes. Computing it requires at most 192 KiB of reads.
            digest = sha256(('Logistics video samples v1:' + str(content.size)).encode())
            with content.open() as stream:
                for offset in sorted({0, max(0, content.size // 2 - 32768), max(0, content.size - 65536)}):
                    stream.seek(offset)
                    digest.update(stream.read(65536))
            content.check()
            self.fingerprint = digest.hexdigest()

    def _check(self):
        if self.remote:
            self.content.check_access()
        else:
            self.content.check()

    def _open(self):
        from .progress import open_progress

        content = self.content
        self.state = open_progress(
            content.provider, content.path, self.root.parent, kind='video',
            revision=self.fingerprint or content.source.expected, app=self.app, check=self._check,
            legacy_path=self.fingerprint or content.path,
            follow_local_rename=bool(self.fingerprint and not self.private),
        )

    def load(self):
        with self.lock:
            self._check()
            if self.state is None:
                self._open()
            record = self.state.load()
            from .video_migration import legacy_protected_path_record, legacy_record

            try:
                previous = {}
                if self.state.can_import_legacy:
                    previous = legacy_record(self)
                elif (self.state.load_status == 'incompatible' and self.state.mode == 'encrypted'
                      and self.fingerprint and not self.state.generation):
                    previous = legacy_protected_path_record(self)
                if previous and self.state.save(previous) == 'saved':
                    record = previous
            except (OSError, ValueError):
                self.resume_notice = 'Older video progress could not be upgraded. Playback can continue.'
            if self.state.load_status == 'locked':
                self.resume_notice = LOCKED_HISTORY
            elif self.state.mode == 'session-memory' and self.resume_notice is None:
                self.resume_notice = 'Video progress is available for this session.'
            self.restore_settings(record)
            self.duration = self.valid_duration(record.get('duration', 0))
            self.position = self.valid_duration(record.get('position', 0))
            return self.position

    @property
    def settings(self):
        return self._settings

    @settings.setter
    def settings(self, value):
        self._settings = value
        self.setting_overrides = asdict(value) if value is not None else {}

    def restore_settings(self, record):
        from .video_settings import SettingsStore

        defaults = asdict(SettingsStore(self.root).load())
        try:
            overrides = record.get('settings', {})
            self._settings = PlaybackSettings.from_dict({**defaults, **overrides})
            self.setting_overrides = {key: overrides[key] for key in defaults if key in overrides}
        except (TypeError, ValueError):
            self._settings = PlaybackSettings.from_dict(defaults)
            self.setting_overrides = {}

    def apply_settings(self, settings, defaults, *, explicit=()):
        """Store deliberate title choices even if they equal today's defaults."""
        values = asdict(settings)
        previous = asdict(self.settings or defaults)
        self.setting_overrides.update({key: value for key, value in values.items()
                                       if key in explicit or value != previous[key]})
        self._settings = settings

    @staticmethod
    def valid_duration(value):
        return value if type(value) is int and 0 <= value <= 10**10 else 0

    def observe(self, milliseconds, *, completed=False):
        with self.lock:
            if type(milliseconds) not in (int, float) or not isfinite(milliseconds) or not 0 <= milliseconds <= 10**10:
                raise ValueError('Invalid video position.')
            settings, overrides, duration = self.settings, self.setting_overrides, self.duration
            if self.state is None:
                self.load()
                if settings is not None:
                    self._settings = settings
                    self.setting_overrides = overrides
                self.duration = duration or self.duration
            self.position = 0 if completed else int(milliseconds)
            return self.state.observe(dict(
                position=self.position, duration=self.valid_duration(self.duration),
                settings=self.setting_overrides,
            ))

    def flush(self, observation=None):
        if self.state is not None:
            status = self.state.flush(observation)
            if status == 'locked':
                self.resume_notice = LOCKED_HISTORY
            if status == 'write-failed':
                raise OSError('Could not save the video position or playback settings.')
            return status

    def save(self, milliseconds, *, completed=False):
        observation = self.observe(milliseconds, completed=completed)
        if observation is not None:
            return self.flush(observation)

    def retire(self):
        if self.state is not None:
            self.state.retire()
