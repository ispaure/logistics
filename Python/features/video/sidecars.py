"""Bounded matching subtitle discovery without UI or platform dependencies."""

from pathlib import PurePosixPath

from .playback import SubtitleContent
from .subtitles import MAX_SUBTITLE


def discover_sidecars(content, *, cancelled=lambda: False, extensions=None):
    """Return retained resources; the caller must close every returned resource."""
    extensions = SubtitleContent.extensions if extensions is None else extensions
    folder, _, name = content.path.rpartition('/')
    stem = PurePosixPath(name).stem
    result = []
    try:
        for row in content.provider.list(folder)[:10000]:
            if cancelled() or len(result) >= 32:
                break
            candidate = str(row['name'])
            if (row['directory'] or PurePosixPath(candidate).suffix.lower() not in extensions
                    or not (PurePosixPath(candidate).stem == stem or candidate.startswith(stem + '.'))):
                continue
            subtitle = None
            try:
                subtitle = SubtitleContent(content.provider, row['path'])
                if subtitle.size <= MAX_SUBTITLE:
                    result.append(subtitle)
                    subtitle = None
            except (OSError, ValueError):
                continue  # Optional subtitles must not prevent video playback.
            finally:
                if subtitle is not None:
                    subtitle.close()
        return result
    except BaseException:
        for subtitle in result:
            subtitle.close()
        raise
