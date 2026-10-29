"""Host persistence for nonsecret playback preferences; schemas stay with the feature."""

from dataclasses import asdict
import json
from pathlib import Path
from threading import RLock

from features.video.session import PlaybackSettings

_lock = RLock()


class SettingsStore:
    def __init__(self, root):
        self.path = Path(root) / "playback-settings.json"

    def load(self):
        with _lock:
            try:
                if self.path.is_symlink() or self.path.stat().st_size > 4096:
                    return PlaybackSettings()
                with self.path.open(encoding="utf-8") as stream:
                    raw = stream.read(4097)
                if len(raw) > 4096:
                    return PlaybackSettings()
                return PlaybackSettings.from_dict(json.loads(raw))
            except (OSError, ValueError, TypeError):
                return PlaybackSettings()

    def save(self, values):
        settings = PlaybackSettings.from_dict(values)
        from commonUtils.persistence import atomic_write_json

        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.path.is_symlink():
                raise ValueError("Linked video preferences are not supported.")
            atomic_write_json(self.path, asdict(settings), max_bytes=4096)
        return settings

