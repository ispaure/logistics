"""Application-owned storage locations and legacy migration decisions."""
from pathlib import Path
from commonUtils.filesystem.relocation import relocate_directory


def application_root():
    from features.preferences import preferences_path
    return preferences_path().parent


def crypt_root():
    import config
    destination = application_root() / 'LocalCrypt'
    relocate_directory(config.LogisticsConfig().server_path / 'LocalCrypt', destination)
    return destination


def local_records(local_root):
    destination = application_root() / 'Connections' / 'Local'
    relocate_directory(Path(local_root).parent / '.local-connections', destination)
    return destination
