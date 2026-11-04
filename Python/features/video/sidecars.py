"""Bounded matching subtitle discovery without UI or platform dependencies."""

from pathlib import PurePosixPath

from .playback import SubtitleContent
from .subtitles import MAX_SUBTITLE


def discover_sidecars(content, *, cancelled=lambda: False, extensions=None, preferred="", entries=None):
    """Return retained resources; the caller must close every returned resource."""
    extensions = SubtitleContent.extensions if extensions is None else extensions
    folder, _, name = content.path.rpartition('/')
    stem = PurePosixPath(name).stem
    result = []
    try:
        rows = (content.provider.list(folder) if entries is None else entries)[:10000]
        if preferred:
            # Keep a selected same-source subtitle across video/folder renames.
            candidate = next((row['path'] for row in rows
                              if row['name'] == PurePosixPath(preferred).name), preferred)
            rows = [dict(name=PurePosixPath(candidate).name, path=candidate, directory=False), *rows]
        seen = set()
        for row in rows:
            if cancelled() or len(result) >= 32:
                break
            candidate = str(row['name'])
            if row['path'] in seen:
                continue
            seen.add(row['path'])
            if (row['directory'] or PurePosixPath(candidate).suffix.lower() not in extensions
                    or not (preferred and PurePosixPath(candidate).name == PurePosixPath(preferred).name
                            or PurePosixPath(candidate).stem == stem or candidate.startswith(stem + '.'))):
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
