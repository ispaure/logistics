"""Pinned official packages; feature policy stays outside commonUtils."""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re

from commonUtils.configuration.layered import effective_settings
from commonUtils.runtime.platform import Arch, OS, get_arch, get_os
from commonUtils.runtime.streams.downloads import DownloadSpec

CONFIG_PATH = Path(__file__).with_name('config.ini')


def platform_key():
    system = {OS.WIN: 'windows', OS.MAC: 'macos', OS.LINUX: 'linux'}.get(get_os())
    arch = {Arch.X86_64: 'x64', Arch.ARM_64: 'arm64'}.get(get_arch())
    return f'{system}-{arch}'


def relative_path(value):
    path = PurePosixPath(value)
    if not value or '\\' in value or ':' in value or path.is_absolute() or '..' in path.parts:
        raise ValueError('Expected a relative package path')
    return Path(*path.parts)


@dataclass(frozen=True)
class Release:
    version: str
    platform: str
    url: str
    sha256: str
    format: str
    bundle: str
    executable: str

    def __post_init__(self):
        if not re.fullmatch(r'\d+\.\d+\.\d+', self.version):
            raise ValueError('Blender releases require an exact major.minor.patch version')
        if self.format not in ('zip', 'tar.xz', 'dmg'):
            raise ValueError(f'Unsupported Blender package format: {self.format}')
        relative_path(self.bundle)
        relative_path(self.executable)
        self.download_spec()  # Reuse shared HTTPS/hash validation.

    def download_spec(self):
        # Provision the verified archive as a file, then install its full bundle.
        return DownloadSpec('Blender', self.version, self.url, self.sha256, self.sha256)


def load_releases(path=CONFIG_PATH, platform=None):
    settings = effective_settings(path, case_sensitive=False)
    platform = platform or platform_key()
    releases = []
    for section in settings.sections():
        if settings.get(section, 'platform_str', fallback='') != platform:
            continue
        values = {field: settings.get(section, field + '_str') for field in
                  ('version', 'platform', 'url', 'sha256', 'format', 'bundle', 'executable')}
        releases.append(Release(**values))
    versions = [release.version for release in releases]
    if len(set(versions)) != len(versions):
        raise ValueError('Duplicate Blender versions for this platform')
    return sorted(releases, key=lambda release: tuple(map(int, release.version.split('.'))), reverse=True)
