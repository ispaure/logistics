"""Install Logistics' raw-filesystem boundary for provider-owned local storage."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.filesystem.local_access import protect_local_root


def install_local_storage_policy(root):
    return protect_local_root(('logistics-localcrypt', str(root.absolute())), root,
        'Open LocalCrypt in its unlocked file browser. Use its Move or Save As actions; '
        'ordinary filesystem operations cannot access encrypted storage directly.')
