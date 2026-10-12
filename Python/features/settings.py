"""Logistics owns the paths; commonUtils owns layered configuration mechanics."""
from pathlib import Path
from contextlib import contextmanager
import shutil
import logging
from tempfile import TemporaryDirectory
from uuid import uuid4

from commonUtils.configuration.layered import LayeredSettings, register_settings
from commonUtils.configuration.settings import settings_path
from features.preferences import preferences_path

LEGACY_SETTINGS_MIGRATIONS = ('feature-enable-v1', 'text-editor-v1', 'git-options-v1')


def migration_ledger(store=None):
    from commonUtils.configuration.migrations import MigrationLedger
    root = preferences_path().parent
    if store is not None:
        # Explicit test/external stores retain their own metadata location.
        root = next((parent.parent for parent in store.personal.parents if parent.name == 'configuration'),
                    store.personal.parent)
    return MigrationLedger(root / 'state' / 'settings-migrations.ini')


def settings_store(path):
    path = Path(path).resolve()
    root = Path(__file__).resolve().parents[1]
    if path == settings_path().resolve():
        name = Path('commonUtils') / 'settings.ini'
    else:
        try:
            name = path.relative_to(root)
        except ValueError:
            if path == root.parent / 'launch_config.ini':
                name = Path('launch_config.ini')
            else:
                # Feature-owned external configuration retains its own storage.
                return LayeredSettings(path, preferences_path().parent / 'configuration' / path.name)
    return register_settings(path, preferences_path().parent / 'configuration' / name)


def initialize_settings():
    root = Path(__file__).resolve().parents[1]
    paths = [settings_path(), root / 'configFile.ini', root / 'maintenance.ini', root.parent / 'launch_config.ini']
    paths += [path for path in (root / 'features').glob('*/config.ini') if path.parent.name != 'emulation']
    for path in paths:
        settings_store(path)


@contextmanager
def reset_personal_configuration():
    """Replace personal overrides; roll back if publication/runtime reset fails.

    Completion metadata stays in state/, independently of resettable overrides.
    Only configuration/ is replaced, never the user-data root.
    """
    from commonUtils.persistence import atomic_write_bytes
    root = preferences_path().parent / 'configuration'
    root.parent.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError('Personal configuration must be a regular folder to reset it')
    ledger = migration_ledger()
    ledger_snapshot = ledger.path.read_bytes() if ledger.path.exists() else None
    with TemporaryDirectory(prefix='.settings-reset-', dir=root.parent) as workspace:
        replacement = Path(workspace) / 'replacement'
        # Keep recovery outside the auto-cleaned staging directory: a failed
        # rollback must never erase the only remaining copy of the old settings.
        backup = root.with_name('configuration.reset-backup-' + uuid4().hex)
        replacement.mkdir(mode=0o700)
        if root.exists():
            for path in root.rglob('*'):
                if path.is_symlink():
                    raise ValueError('Personal configuration contains a symlink; inspect it before resetting')
        previous = root.exists()
        if previous:
            root.rename(backup)
        try:
            replacement.rename(root)
            ledger.complete(*LEGACY_SETTINGS_MIGRATIONS)
            yield root
        except BaseException:
            try:
                if root.exists():
                    shutil.rmtree(root)
                if previous:
                    backup.rename(root)
                if ledger_snapshot is None:
                    ledger.path.unlink(missing_ok=True)
                else:
                    atomic_write_bytes(ledger.path, ledger_snapshot)
            except OSError as error:
                raise OSError(f'Could not restore personal configuration. Previous settings are kept at {backup}') from error
            raise
        else:
            if previous:
                try:
                    shutil.rmtree(backup)
                except OSError:
                    logging.warning('Personal settings reset; obsolete configuration backup could not be removed: %s', backup)


def validate_configuration(path, values):
    path = Path(path).resolve()
    if path.parent.name == 'git':
        from features.git.configuration import validate
        validate(values)
    elif path.parent.name == 'books':
        from features.books.preferences import THEMES
        for key, low, high in (('line_spacing_int', 100, 220), ('reading_width_int', 480, 1400)):
            if not low <= int(values.get(('Reader', key), low)) <= high:
                raise ValueError(f'{key}: choose a value between {low} and {high}')
        if values.get(('Reader', 'theme_mode'), 'sepia') not in THEMES:
            raise ValueError('Choose a supported reading theme')
    elif path.parent.name == 'text_editor':
        if not 1 <= int(values.get(('Editor', 'indent_width_int'), 4)) <= 16:
            raise ValueError('Indentation width must be between 1 and 16')
