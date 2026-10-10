"""Read download settings and build shell-free yt-dlp arguments."""

from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import shutil
import sys

from commonUtils.runtime.platform import OS, get_os

DEFAULT_ARGUMENTS = (
    '--write-info-json', '--write-thumbnail', '--add-metadata', '--no-overwrites',
    '--ignore-errors', '--restrict-filenames', '-f',
    'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
    '--merge-output-format', 'mp4',
)


def _folder_component(value: str, label: str) -> str:
    value = value.strip()
    if not value or value in ('.', '..') or any(c in value for c in '/\\<>:"|?*'):
        raise ValueError(f'{label} must be a single folder name.')
    if value.endswith('.') or any(ord(c) < 32 for c in value):
        raise ValueError(f'{label} contains unsupported filename characters.')
    if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError(f'{label} is a reserved filename.')
    return value


@dataclass(frozen=True)
class DownloadSettings:
    config_file: Path
    channel: str
    url: str
    season: int
    additional_arguments: tuple[str, ...]

    @classmethod
    def read(cls, path: Path):
        parser = ConfigParser(interpolation=None)
        with Path(path).open(encoding='utf-8-sig') as stream:
            parser.read_file(stream)
        section = parser['Youtube-DL']
        channel = _folder_component(section['channel_name'], 'channel_name')
        url = section['download_url'].strip()
        if not re.match(r'^https?://\S+$', url, re.IGNORECASE):
            raise ValueError('download_url must be an HTTP or HTTPS URL.')
        season = int(section['season_number'])
        if season < 0:
            raise ValueError('season_number must be nonnegative.')
        # INI options use shell-style quotes on every platform; they are parsed,
        # never executed by a shell. Quote Windows paths using forward slashes.
        extra = tuple(shlex.split(section.get('additional_params', '')))
        return cls(Path(path), channel, url, season, extra)

    def destination(self, config_directory: Path) -> Path:
        root = Path(config_directory).resolve().parent
        destination = root / self.channel / f'Season {self.season}'
        if not destination.resolve().is_relative_to(root):
            raise ValueError('The channel destination escapes the download root.')
        return destination


def find_ffmpeg() -> str:
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    platform = get_os()
    bundled = {OS.WIN: ('ffmpeg_win', 'ffmpeg.exe'), OS.MAC: ('ffmpeg_macos', 'ffmpeg')}
    if platform in bundled:
        import config
        candidate = Path(config.LogisticsConfig().path_logistics_software, *bundled[platform])
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError('FFmpeg was not found. Install it on PATH or provide the bundled executable.')


def download_arguments(settings: DownloadSettings, config_directory: Path, ffmpeg: str,
                       playlist_reverse=True, playlist_end=None) -> list[str]:
    destination = settings.destination(config_directory)
    count = 1
    if destination.exists():
        files = [file for file in destination.iterdir()
                 if file.is_file() and file.suffix.lower() == '.mp4' and ' - s' in file.name]
        episodes = []
        for file in files:
            match = re.search(r' - s(\d+)e(\d+)\b', file.name, re.IGNORECASE)
            if match and int(match[1]) == settings.season:
                episodes.append(int(match[2]))
        # Deleted downloads create gaps; count alone can reuse an existing number.
        count = max(episodes, default=len(files)) + 1
    arguments = [sys.executable, '-m', 'yt_dlp', *DEFAULT_ARGUMENTS, *settings.additional_arguments]
    if playlist_reverse:
        arguments.append('--playlist-reverse')
    if playlist_end is not None:
        if isinstance(playlist_end, bool) or int(playlist_end) != float(playlist_end) or int(playlist_end) < 1:
            raise ValueError('playlist_end must be a positive integer.')
        arguments.extend(['--playlist-end', str(int(playlist_end))])
    template = destination / f'%(channel)s - s{settings.season:02d}e%(autonumber)s - %(title).50s.%(ext)s'
    arguments.extend(['--ffmpeg-location', ffmpeg, '--download-archive',
                      str(Path(config_directory) / 'CompleteLists' / f'{settings.config_file.stem}_complete.lst'),
                      '-o', str(template), '--autonumber-start', str(count), '--', settings.url])
    return arguments
