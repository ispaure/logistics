"""Install Logistics' raw-filesystem boundary for provider-owned local storage."""
from commonUtils.filesystem.local_access import protect_local_root


def install_local_storage_policy(root=None):
    from features.rclone.localcrypt.backend import storage_root
    root = root if root is not None else storage_root()
    return protect_local_root(('logistics-localcrypt', str(root.absolute())), root,
        'Open LocalCrypt in its unlocked file browser. Use its Move or Save As actions; '
        'ordinary filesystem operations cannot access encrypted storage directly.')
