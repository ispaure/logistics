"""Read and update Obsidian's global vault registry."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import json
import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from commonUtils.persistence import atomic_write_bytes


def _normalize_path(path: Path) -> str:
    """Return a normalized absolute path suitable for comparing vault registry entries."""

    try:
        resolved_path = path.expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        resolved_path = path.expanduser().absolute()

    return os.path.normcase(os.path.normpath(str(resolved_path)))


def _read_registry_bytes(registry_path: Path) -> bytes | None:
    """Read the registry's current bytes if it is a regular file."""

    if not registry_path.is_file():
        return None
    try:
        return registry_path.read_bytes()
    except FileNotFoundError:
        return None


def _write_registry(
    registry_path: Path,
    registry: dict[str, Any],
    *,
    validate: Callable[[], None] | None = None,
    overwrite: bool = True
) -> None:
    """Atomically write an Obsidian registry, preserving existing file permissions when possible."""

    try:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(registry, separators=(',', ':'), ensure_ascii=False) + '\n'
        atomic_write_bytes(registry_path, content.encode('utf-8'), validate=validate, overwrite=overwrite)
    except OSError as error:
        raise RuntimeError(f'Could not write Obsidian registry "{registry_path}": {error}') from error


@dataclass(frozen=True)
class RegistrySnapshot:
    """A parsed registry and the byte revision used to read it."""

    path: Path
    _data: dict[str, Any]
    _original: bytes | None

    @classmethod
    def read(cls, path: Path) -> 'RegistrySnapshot':
        try:
            original = _read_registry_bytes(path)
            if original is None:
                return cls(path, {'vaults': {}}, None)
            data = json.loads(original.decode('utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f'Could not read Obsidian registry "{path}": {error}') from error

        if not isinstance(data, dict):
            raise RuntimeError(f'Obsidian registry "{path}" does not contain a JSON object.')

        if not isinstance(data.setdefault('vaults', {}), dict):
            raise RuntimeError(f'Obsidian registry "{path}" has an invalid "vaults" value.')

        return cls(path, data, original)

    def find_vault_id(self, vault_path: Path) -> str | None:
        """Find the ID for the vault's canonical filesystem path."""

        normalized_vault_path = _normalize_path(vault_path)
        for vault_id, vault_data in self._data['vaults'].items():
            if not isinstance(vault_data, dict):
                continue

            registered_path = vault_data.get('path')
            if not isinstance(registered_path, str):
                continue

            if _normalize_path(Path(registered_path)) == normalized_vault_path:
                return vault_id

        return None

    def register(self, vault_path: Path) -> str:
        """Publish a new vault entry against this revision and return its ID."""

        vaults = self._data['vaults']
        while True:
            vault_id = secrets.token_hex(8)
            if vault_id not in vaults:
                break

        new_entry = {
            'path': str(vault_path.expanduser().resolve(strict=False)),
            'ts': int(time.time() * 1000)
        }
        data = {**self._data, 'vaults': {**vaults, vault_id: new_entry}}

        def validate_revision() -> None:
            if _read_registry_bytes(self.path) != self._original:
                raise RuntimeError(f'Obsidian registry changed during registration: "{self.path}"')

        _write_registry(self.path, data, validate=validate_revision, overwrite=self._original is not None)
        return vault_id
