"""Application-owned storage locations and legacy migration decisions."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

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


def install_local_storage_policy(root=None):
    """Compose the host filesystem guard with this backend's ciphertext root."""
    from services.local_storage import install_local_storage_policy as install
    return install(crypt_root() if root is None else root)
