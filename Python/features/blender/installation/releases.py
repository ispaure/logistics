"""Pinned official packages; feature policy stays outside commonUtils."""
from dataclasses import dataclass
from configparser import Error
from pathlib import Path, PurePosixPath
import re

from commonUtils.configuration.layered import effective_settings
from commonUtils.runtime.platform import Arch, OS, get_arch, get_os
from commonUtils.runtime.streams.downloads import DownloadSpec

CONFIG_DIR = Path(__file__).parents[1]
VERSION_FILE = re.compile(r'config-(\d+\.\d+\.\d+)\.ini')
RELEASE_FIELDS = ('url', 'sha256', 'format', 'bundle', 'executable')


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


def release_config_paths(directory=None):
    directory = Path(directory) if directory is not None else CONFIG_DIR
    return sorted((path for path in directory.glob('config-*.ini') if VERSION_FILE.fullmatch(path.name)),
                  key=lambda path: tuple(map(int, VERSION_FILE.fullmatch(path.name)[1].split('.'))), reverse=True)


def version_from_path(path):
    match = VERSION_FILE.fullmatch(Path(path).name)
    if match is None:
        raise ValueError('Use config-<major.minor.patch>.ini for Blender release metadata')
    return match[1]


def releases_from_values(path, values):
    version = version_from_path(path)
    platforms = dict.fromkeys(section for section, key in values)
    releases = []
    for platform in platforms:
        if platform not in {f'{system}-{arch}' for system in ('macos', 'windows', 'linux') for arch in ('x64', 'arm64')}:
            raise ValueError(f'Unknown Blender platform: {platform}')
        fields = {field: values.get((platform, field + '_str'), '') for field in RELEASE_FIELDS}
        releases.append(Release(version=version, platform=platform, **fields))
    return releases


def load_releases(path=None, platform=None):
    platform = platform or platform_key()
    paths = release_config_paths() if path is None else (release_config_paths(path) if Path(path).is_dir() else [Path(path)])
    releases = []
    for config in paths:
        if VERSION_FILE.fullmatch(config.name):
            from features.settings import settings_store
            settings = settings_store(config).values()
            releases.extend(build for build in releases_from_values(config, settings) if build.platform == platform)
        else:
            # Explicit legacy files remain readable for existing external callers.
            settings = effective_settings(config, case_sensitive=False)
            for section in settings.sections():
                if settings.get(section, 'platform_str', fallback='') == platform:
                    fields = {field: settings.get(section, field + '_str') for field in
                              ('version', 'platform', *RELEASE_FIELDS)}
                    releases.append(Release(**fields))
    versions = [release.version for release in releases]
    if len(set(versions)) != len(versions):
        raise ValueError('Duplicate Blender versions for this platform')
    return sorted(releases, key=lambda release: tuple(map(int, release.version.split('.'))), reverse=True)


def initialize_release_settings(directory=None):
    """Register version files and migrate old personal fields without deleting the source."""
    from features.settings import migration_ledger, settings_store
    directory = Path(directory) if directory is not None else CONFIG_DIR
    paths = release_config_paths(directory)
    for path in paths:
        settings_store(path)
    legacy_store = settings_store(directory / 'config.ini')
    if not legacy_store.personal.exists():
        return
    def migrate():
        old = legacy_store.overrides()
        for path in paths:
            version = version_from_path(path)
            store = settings_store(path)
            defaults, existing = store.values('application'), store.overrides()
            changes = {}
            for section, key in defaults:
                identity = version + '-' + section, key
                if identity in old and (section, key) not in existing:
                    changes[section, key] = old[identity]
            if changes:
                # Existing new-format fields win; partial migration retries are idempotent.
                store.save(changes)
    try:
        migration_ledger(legacy_store).run('blender-release-files-v1', migrate)
    except (OSError, UnicodeError, Error, ValueError) as error:
        from commonUtils.runtime.diagnostics import log, Severity
        log(Severity.ERROR, 'Blender release settings', f'Could not migrate release overrides; original files preserved: {error}')
