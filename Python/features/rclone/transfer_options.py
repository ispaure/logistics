"""Portable rclone transfer options, independent of UI and execution backend."""
from dataclasses import dataclass
import json
from pathlib import Path


# Cleanup is a separate, narrowly scoped mutation policy. User filters never
# authorize deleting local files, and excluded destination files stay excluded.
CLEANUP_NAMES = frozenset({'.ds_store', 'thumbs.db', 'ehthumbs.db', 'ehthumbs_vista.db'})
DEFAULT_EXCLUDES = ('.DS_Store', '[Tt]humbs.db', '[Ee]hthumbs.db', '[Ee]hthumbs_vista.db', '[Dd]esktop.ini', '._*')


def validate_excludes(values):
    if not isinstance(values, (list, tuple)) or len(values) > 200:
        raise ValueError('Use at most 200 exclusion patterns.')
    result = []
    for value in values:
        if not isinstance(value, str) or len(value) > 1024 or any(ord(c) < 32 for c in value):
            raise ValueError('Each exclusion must be a single pattern, at most 1024 characters.')
        value = value.strip()
        if value and value not in result:
            result.append(value)
    return tuple(result)


@dataclass(frozen=True)
class TransferOptions:
    track_renames: bool = False
    bw_limit: int | None = None
    copy_links: bool = True
    excludes: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.track_renames) is not bool or type(self.copy_links) is not bool:
            raise ValueError('Transfer switches must be true or false.')
        object.__setattr__(self, 'excludes', validate_excludes(self.excludes))
        if self.bw_limit is not None:
            if isinstance(self.bw_limit, bool):
                raise ValueError('Bandwidth limit must be a positive number of MB/s')
            value = int(self.bw_limit)
            if value <= 0:
                raise ValueError('Bandwidth limit must be a positive number of MB/s')
            object.__setattr__(self, 'bw_limit', value)

    def cli_arguments(self):
        arguments = ['--copy-links'] if self.copy_links else []
        if self.track_renames:
            arguments += ['--track-renames']
        if self.bw_limit is not None:
            arguments += ['--bwlimit', f'{self.bw_limit}M']
        for pattern in self.excludes:
            arguments += ['--exclude', pattern]
        return arguments

    def bridge_arguments(self, *, push):
        return dict(track_renames=self.track_renames, bw_limit=self.bw_limit or 0,
                    excludes=list(self.excludes) if push else [])


def load_options(path):
    path = Path(path)
    if not path.exists():
        return TransferOptions(excludes=DEFAULT_EXCLUDES)
    if path.is_symlink() or path.stat().st_size > 256 * 1024:
        raise ValueError('Invalid transfer settings.')
    values = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(values, dict) or set(values) != {'track_renames', 'bw_limit', 'excludes'}:
        raise ValueError('Invalid transfer settings.')
    return TransferOptions(**values)


def save_options(path, options):
    from commonUtils.persistence import atomic_write_json
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Transfer settings cannot be linked.')
    atomic_write_json(path, dict(track_renames=options.track_renames, bw_limit=options.bw_limit,
                               excludes=list(options.excludes)))
