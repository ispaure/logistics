"""Portable video controls, preferences and folder queue; no UI or decoder imports."""

from dataclasses import asdict, dataclass
import json
from math import isfinite
from pathlib import Path, PurePosixPath
import re
from threading import RLock

from .formats import VIDEO_EXTENSIONS

RATES = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
ASPECTS = ("fit", "fill", "original")
_lock = RLock()


def parse_time(value):
    parts = str(value).strip().split(":")
    if not 1 <= len(parts) <= 3 or any(
        not re.fullmatch(r"\d+(?:\.\d{1,3})?", p) for p in parts
    ):
        raise ValueError("Enter seconds, MM:SS or HH:MM:SS.")
    if any("." in p for p in parts[:-1]) or any(float(p) >= 60 for p in parts[1:]):
        raise ValueError("Minutes and seconds must be less than 60.")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    if not isfinite(seconds) or seconds > 10**7:
        raise ValueError("That playback time is too large.")
    return round(seconds * 1000)


@dataclass(frozen=True)
class PlaybackSettings:
    rate: float = 1.0
    aspect: str = "fit"
    subtitle_scale: float = 1.0
    subtitle_delay_ms: int = 0
    audio_delay_ms: int = 0
    audio_language: str = ""
    subtitle_language: str = ""
    autoplay_next: bool = False

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Invalid playback preferences.")
        result = cls(**{key: values[key] for key in asdict(cls()) if key in values})
        if (
            type(result.rate) not in (float, int)
            or result.rate not in RATES
            or result.aspect not in ASPECTS
            or type(result.subtitle_scale) not in (float, int)
            or not 0.5 <= result.subtitle_scale <= 3
            or type(result.autoplay_next) is not bool
        ):
            raise ValueError("Invalid playback preferences.")
        for value in (result.subtitle_delay_ms, result.audio_delay_ms):
            if type(value) is not int or abs(value) > 600000:
                raise ValueError("Delay must be within ten minutes.")
        for value in (result.audio_language, result.subtitle_language):
            if not isinstance(value, str) or not re.fullmatch(
                r"[a-zA-Z-]{0,16}", value
            ):
                raise ValueError("Use a language code such as en or fr.")
        return result

    def json(self):
        return json.dumps(asdict(self))


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


def natural_key(value):
    return tuple(
        (1, int(p)) if p.isdecimal() else (0, p.casefold())
        for p in re.split(r"(\d+)", value)
    )


class FolderQueue:
    def __init__(self, path, rows):
        folder = PurePosixPath(path).parent
        self.paths = sorted(
            {
                str(row["path"])
                for row in rows[:10000]
                if not row.get("directory")
                and PurePosixPath(str(row["path"])).suffix.lower() in VIDEO_EXTENSIONS
                and PurePosixPath(str(row["path"])).parent == folder
            }
            | {str(path)},
            key=natural_key,
        )
        self.current = str(path)

    def adjacent(self, offset):
        index = self.paths.index(self.current) + offset
        return self.paths[index] if 0 <= index < len(self.paths) else None

    def rows(self):
        return [
            dict(path=p, name=PurePosixPath(p).name, current=p == self.current)
            for p in self.paths
        ]
