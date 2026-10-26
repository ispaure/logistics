"""Mobile Books and Comics catalogue; readers own their own presentation."""
from services.documents.locations import collection_path, CollectionFiles
from configparser import ConfigParser, Error as ConfigError
from pathlib import Path
from features.comics.library_config import library_names


def discover_libraries(root, jobs, client=None, crypt_remotes=()):
    """Inspect collection-root INIs, without recursively scanning book files."""
    from features.rclone.localcrypt.mobile.resources import encrypted_library_sources
    from .folder_hub import exclusions, visible_remotes
    from services.folders.policy import visible_name
    root = Path(root)
    sources, records, failures, seen = [], [], 0, set()
    try:
        local = collection_path(root)
    except (OSError, ValueError):
        return [], 1
    rules = exclusions()
    if local.is_dir() and not local.is_symlink():
        provider = CollectionFiles(root)
        sources.append((provider, '', 'Local'))
        for child in sorted(local.iterdir(), key=lambda path: path.name.casefold()):
            if child.is_dir() and not child.is_symlink() and visible_name(child.name, rules):
                sources.append((provider, child.name, 'Local'))
        for job in jobs:
            if not job['crypt'] and visible_name(job['remote'], rules, remote=True):
                sources.append((provider, job['target'], 'Local'))
    private_sources, private_failures = encrypted_library_sources(root, jobs, client, visible_remotes(crypt_remotes))
    sources.extend(private_sources)
    failures += private_failures
    # A local copy can itself be a collection, or hold collection folders.
    for provider, folder, source in list(sources):
        if provider.private:
            try:
                sources.extend((provider, row['path'], source) for row in provider.list(folder)
                               if row['directory'] and visible_name(row['name'], rules))
            except (OSError, ValueError):
                failures += 1
    for provider, folder, source in sources:
        identity = str(provider.root), folder
        if identity in seen:
            continue
        seen.add(identity)
        try:
            path = '/'.join(part for part in (folder, 'remoteConfig.ini') if part)
            with provider.open(path) as stream:
                data = stream.read(256 * 1024 + 1)
            if len(data) > 256 * 1024:
                raise ValueError('Library configuration is too large.')
            config = ConfigParser(interpolation=None)
            config.read_string(data.decode('utf-8-sig'))
            names = library_names(config)
            if names is None:
                legacy = (config.has_option('ComicRack', 'appdata_local_cyo_sub_path')
                          and config.has_option('ComicRack', 'appdata_roaming_cyo_sub_path'))
                if not legacy and not config.has_option('YACReaderLibrary', 'yacreaderlibrary_ini_sub_path'):
                    continue
                names = ['']
            for name in names:
                path = '/'.join(part for part in (folder, name) if part)
                try:
                    available = provider.entry(path)['directory']
                except FileNotFoundError:
                    continue
                if available:
                    records.append(dict(name=name or Path(folder).name or 'Comics',
                        folder=path, source=source, provider=provider))
        except FileNotFoundError:
            continue
        except (OSError, ValueError, UnicodeError, ConfigError):
            failures += 1
    return records, failures


# Compatibility export; discovery remains owned by the storage host.

from features.books.mobile.library.catalog import LibraryCatalog as LibraryCatalog
