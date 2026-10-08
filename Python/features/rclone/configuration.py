"""
rclone configuration handling for the Logistics rclone feature.
"""

from pathlib import Path

from commonUtils import fileUtils
from commonUtils.fileTypes import txtType


def get_rclone_config_dir() -> Path:
    """Return the current user's rclone configuration directory."""

    return Path(fileUtils.get_user_home_dir(), '.config', 'rclone')


def ensure_rclone_config_dir() -> Path:
    """Ensure the rclone configuration directory exists and return it."""

    config_dir = get_rclone_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_rclone_conf_path() -> Path:
    """Return the legacy/default rclone.conf path."""

    return get_rclone_config_dir() / 'rclone.conf'


def get_credential_config_path(credential_zip_path: str | Path) -> Path:
    """Return the generated .conf path paired with one credential ZIP."""

    import hashlib
    import config
    package = Path(credential_zip_path).resolve()
    primary = config.LogisticsConfig().path_logistics_remote_cred.resolve()
    credential_name = package.stem
    # Preserve legacy names for packages directly in the checkout credential root.
    # External/nested packages get stable identities even if another source disappears.
    if package.parent != primary:
        identity = hashlib.sha256(str(package).encode('utf-8')).hexdigest()[:12]
        credential_name += f'-{identity}'
    return get_rclone_config_dir() / f'{credential_name}.conf'


def get_rclone_remote_names(config_path: str | Path) -> list[str]:
    """Return remote names defined in one explicit rclone config file."""

    config_path = Path(config_path)

    if not config_path.is_file():
        return []

    config_file = txtType.TXTFile(config_path)
    config_file.read_lines()

    remote_names = []

    for line in config_file.line_lst:
        stripped_line = line.strip()

        if stripped_line.startswith('[') and stripped_line.endswith(']'):
            remote_names.append(stripped_line[1:-1])

    return remote_names


def delete_config_file(config_path: str | Path) -> bool:
    """Delete one rclone .conf file if it exists."""

    config_path = Path(config_path)

    if not config_path.is_file():
        return False

    fileUtils.File(config_path).delete_file()
    return True


def get_all_conf_paths() -> list[Path]:
    """Return all .conf files directly inside the rclone configuration folder."""

    config_dir = get_rclone_config_dir()

    if not config_dir.is_dir():
        return []

    return sorted(
        (
            path
            for path in config_dir.iterdir()
            if path.is_file() and path.suffix.casefold() == '.conf'
        ),
        key=lambda path: path.name.casefold()
    )


def clear_all_conf_files() -> list[Path]:
    """
    Delete every .conf file directly inside the rclone configuration folder.

    This includes the legacy/default rclone.conf and Logistics-generated
    per-credential config files. Credential ZIP packages are not touched.
    """

    deleted_paths = []

    for config_path in get_all_conf_paths():
        if delete_config_file(config_path):
            deleted_paths.append(config_path)

    return deleted_paths
