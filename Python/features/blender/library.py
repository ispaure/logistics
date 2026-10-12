"""Private versioned addon library. Metadata is parsed, never imported."""
import ast
from functools import lru_cache
from datetime import date
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from tempfile import TemporaryDirectory
import tomllib
import zipfile

from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.streams import copy_stream
from .releases import relative_path


def version_tuple(value):
    if isinstance(value, (tuple, list)):
        value = '.'.join(map(str, value))
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+){0,3}', value):
        raise ValueError('Expected a numeric addon or Blender version')
    parts = tuple(map(int, value.split('.')))
    return parts + (0,) * max(0, 3 - len(parts))


def version_string(value):
    return '.'.join(map(str, version_tuple(value)))


@dataclass(frozen=True)
class Addon:
    identity: str
    name: str
    version: str
    minimum: str
    maximum: str
    kind: str
    module: str
    prefix: str
    platforms: tuple
    package: Path
    digest: str
    source: str = 'Personal'
    published: str = ''
    package_name: str = ''

    def compatible(self, release):
        return (bool(self.minimum) and version_tuple(release.version) >= version_tuple(self.minimum)
                and (not self.maximum or version_tuple(release.version) < version_tuple(self.maximum))
                and (not self.platforms or release.platform in self.platforms))


def inspect_package(package):
    package = Path(package)
    before = package.stat()
    fingerprint = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    try:
        result = _cached_package(package, fingerprint)
        after = package.stat()
        if fingerprint != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Addon ZIP changed while reading it')
        return result
    except (zipfile.BadZipFile, SyntaxError, UnicodeError, KeyError, TypeError, RuntimeError) as error:
        raise ValueError(f'Cannot read addon ZIP metadata: {error}') from error


@lru_cache(maxsize=512)
def _cached_package(package, fingerprint):
    return _inspect_package(package)


def package_date(filename):
    match = re.search(r'_(\d{4})_(\d{2})_(\d{2})\.zip$', filename, re.IGNORECASE)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    return ''


def legacy_version(value):
    # Some publishers append a release nickname to the numeric bl_info tuple.
    if isinstance(value, (tuple, list)):
        value = list(value)
        while value and isinstance(value[-1], str):
            value.pop()
    return version_string(value)


def _inspect_package(package):
    package = Path(package)
    with zipfile.ZipFile(package) as archive:
        members = archive.infolist()
        if len(members) > 20000 or sum(item.file_size for item in members) > 1024 ** 3:
            raise ValueError('Addon ZIP exceeds the library size limit (1 GiB / 20,000 files)')
        names = set()
        for item in members:
            path = relative_path(item.filename)
            key = str(path).casefold()
            if key in names or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Addon ZIP has duplicate paths or symbolic links')
            names.add(key)
        files = [item.filename for item in members if not item.is_dir()]
        manifests = [name for name in files if PurePosixPath(name).name == 'blender_manifest.toml']
        if manifests:
            if len(manifests) != 1:
                raise ValueError('Choose a ZIP containing exactly one addon')
            marker = manifests[0]
            prefix = str(PurePosixPath(marker).parent)
            prefix = '' if prefix == '.' else prefix + '/'
            if prefix + '__init__.py' not in files:
                raise ValueError('Extension ZIP is missing __init__.py')
            if archive.getinfo(marker).file_size > 1024 ** 2:
                raise ValueError('Addon metadata is too large')
            info = tomllib.loads(archive.read(marker).decode('utf-8-sig'))
            if info.get('type') != 'add-on':
                raise ValueError('Only addon extensions are supported')
            module = info.get('id', '')
            kind = 'Extension'
            minimum = info.get('blender_version_min', '')
            maximum = info.get('blender_version_max', '')
            platforms = info.get('platforms', [])
            if not isinstance(platforms, list) or any(not isinstance(p, str) for p in platforms):
                raise ValueError('Invalid extension platforms')
        else:
            candidates = [name for name in files if PurePosixPath(name).name == '__init__.py'
                          and len(PurePosixPath(name).parts) == 2]
            if not candidates:
                candidates = [name for name in files if '/' not in name and name.endswith('.py')]
            if len(candidates) != 1:
                raise ValueError('Choose a ZIP containing one top-level addon package or Python file')
            marker = candidates[0]
            module = PurePosixPath(marker).parts[0].removesuffix('.py')
            prefix = module + '/' if marker.endswith('/__init__.py') else ''
            if archive.getinfo(marker).file_size > 1024 ** 2:
                raise ValueError('Addon metadata is too large')
            tree = ast.parse(archive.read(marker).decode('utf-8-sig'))
            info = {}
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'bl_info' for t in node.targets):
                    info = ast.literal_eval(node.value)
                    break
            if not isinstance(info, dict) or not info:
                raise ValueError('Addon ZIP has no literal bl_info metadata')
            kind = 'Legacy addon'
            minimum, maximum, platforms = info.get('blender', ''), '', []
        if not isinstance(module, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', module):
            raise ValueError('Addon has an invalid module identity')
        # Ignore unrelated archive files; normalized payload is only this addon.
        if kind == 'Legacy addon' and not prefix and len(files) != 1:
            raise ValueError('Single-file addons must contain only their Python file')
        with package.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        return Addon(('extension:' if kind == 'Extension' else 'legacy:') + module,
                     str(info.get('name') or module), legacy_version(info.get('version', '')) if kind == 'Legacy addon' else version_string(info.get('version', '')),
                     version_string(minimum) if minimum else '', version_string(maximum) if maximum else '',
                     kind, module, prefix, tuple(platforms), package, digest, published=package_date(package.name), package_name=package.name)


class AddonLibrary:
    def __init__(self, manager, *, provided_root=None, preset_root=None):
        self.manager = manager
        self.errors = []
        self.warnings = []
        self.legacy_root = manager.root / 'addons' / 'blender'
        self.preset_root = preset_root
        self.root = manager._contained(preset_root, 'addon-library') if preset_root is not None else self.legacy_root
        if provided_root is None:
            from config import get_config_file_path
            from commonUtils.configuration.layered import effective_settings
            config_path = get_config_file_path()
            settings = effective_settings(config_path, case_sensitive=False)
            value = settings.get('Resources', 'blender_addons_path', fallback='Software/Blender_Addons_Library').strip() or 'Software/Blender_Addons_Library'
            provided_root = Path(value).expanduser()
            if not provided_root.is_absolute():
                provided_root = config_path.parent.parent / provided_root
        self.provided_root = Path(provided_root)

    def for_preset(self, root):
        return AddonLibrary(self.manager, provided_root=self.provided_root, preset_root=root)

    def entries(self, *, shared_only=False, legacy_identities=None):
        combined = {}
        self.errors = []
        layers = [('Provided', self.provided_root)]
        if not shared_only:
            layers.append(('Personal', self.legacy_root))
            if self.preset_root is not None:
                layers.append(('Preset', self.root))
        if self.preset_root is not None and legacy_identities is None:
            legacy_identities = self.selection(self.preset_root)['selected']
        for source, root in layers:
            if not root.is_dir():
                continue
            layer = {}
            paths = sorted(p for p in root.rglob('*.zip') if '_support' not in p.relative_to(root).parts) if source == 'Provided' else sorted(root.glob('*/*/addon.zip'))
            conflicts = set()
            for path in paths:
                try:
                    addon = self._entry(path, root, source)
                    if source == 'Personal' and self.preset_root is not None and addon.identity not in legacy_identities:
                        continue
                    key = (addon.identity, addon.version, addon.published)
                    if key in conflicts:
                        raise ValueError('Package conflicts with another ZIP for this addon version/date')
                    if key in layer and layer[key].digest != addon.digest:
                        previous = layer.pop(key)
                        conflicts.add(key)
                        self.errors.append(f'{previous.package}: conflicting package for {addon.name} {addon.version}')
                        raise ValueError(f'Conflicting package for {addon.name} {addon.version}')
                    layer[key] = addon
                except (OSError, ValueError) as error:
                    self.errors.append(f'{path}: {error}')
            # Artist packages override only the matching identity/version.
            if source != 'Provided':
                versions = {(item.identity, item.version) for item in layer.values()}
                combined = {key: item for key, item in combined.items() if (item.identity, item.version) not in versions}
            combined.update(layer)
        return sorted(combined.values(), key=lambda a: (a.name.casefold(), a.identity, version_tuple(a.version)))

    def _entry(self, path, root, source):
        if source != 'Provided':
            path = self.manager._contained(root, *path.relative_to(root).parts)
        addon = replace(inspect_package(path), source=source)
        origin = path.with_name('origin.json')
        if source != 'Provided' and origin.is_file():
            record = json.loads(self.manager._contained(root, *origin.relative_to(root).parts).read_text())
            if not isinstance(record, dict) or any(not isinstance(record.get(field, ''), str) for field in ('published', 'package_name')):
                raise ValueError('Invalid personal addon package record')
            if record.get('published'):
                date.fromisoformat(record['published'])
            addon = replace(addon, published=record.get('published', ''), package_name=record.get('package_name', path.name))
        return addon

    def add(self, package, *, cancelled=lambda: False):
        addon = inspect_package(package)
        destination = self.manager._contained(self.root, addon.identity.replace(':', '-'), addon.version + ('--' + addon.published if addon.published else ''))
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            existing = inspect_package(destination / 'addon.zip')
            if existing.digest != addon.digest:
                raise ValueError('This addon version already exists with different contents')
            return replace(existing, published=addon.published, package_name=addon.package_name, source='Preset' if self.preset_root is not None else 'Personal')
        with TemporaryDirectory(prefix='.import-', dir=destination.parent) as temp:
            staged = Path(temp) / 'release'
            staged.mkdir()
            with addon.package.open('rb') as source, (staged / 'addon.zip').open('wb') as target:
                copy_stream(source, target, cancelled=cancelled)
            copied = inspect_package(staged / 'addon.zip')
            if copied.digest != addon.digest:
                raise ValueError('Addon ZIP changed during import')
            (staged / 'origin.json').write_text(json.dumps({'published': addon.published, 'package_name': addon.package_name}), encoding='utf-8')
            check_cancelled(cancelled)
            staged.rename(destination)
        return replace(inspect_package(destination / 'addon.zip'), published=addon.published, package_name=addon.package_name, source='Preset' if self.preset_root is not None else 'Personal')

    def resolve(self, identity, release, *, entries=None):
        choices = [item for item in (self.entries() if entries is None else entries) if item.identity == identity and item.compatible(release)]
        return max(choices, key=lambda item: (version_tuple(item.version), item.published), default=None)

    def selection(self, root):
        path = root / '.logistics-addons.json'
        if not path.exists():
            return {'selected': [], 'installed': {}}
        if path.is_symlink():
            raise ValueError('Addon selection cannot be a symbolic link')
        value = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or not isinstance(value.get('selected'), list)
                or any(not isinstance(key, str) for key in value['selected'])
                or not isinstance(value.get('installed'), dict)
                or any(not isinstance(entry, dict) or not {'module', 'path', 'digest'} <= entry.keys()
                       or any(not isinstance(entry[field], str) for field in ('module', 'path', 'digest'))
                       for entry in value['installed'].values())):
            raise ValueError('Invalid preset addon selection')
        return value

    def apply(self, release, name, identities, *, bluehole=None, cancelled=lambda: False):
        self.warnings = []
        from .install import installation_lock
        with installation_lock(self.manager.preset(release, name)):
            return self._apply(release, name, identities, bluehole=bluehole, cancelled=cancelled)

    def _apply(self, release, name, identities, *, bluehole=None, cancelled=lambda: False):
        """Rollback files/preferences if Blender fails to enable the resolved selection."""
        manager = self.manager
        manager._require_idle(release, name)
        executable = manager.executable(release)
        root = manager.preset(release, name)
        state = self.selection(root)
        from .bluehole import IDENTITY
        identities = [identity for identity in identities if identity != IDENTITY]
        resolved = []
        entries = self.for_preset(root).entries(legacy_identities=identities)
        for identity in sorted(set(identities)):
            addon = self.resolve(identity, release, entries=entries)
            if addon is None:
                raise ValueError(f'No declared-compatible release is available for {identity}')
            resolved.append(addon)
        from . import bluehole as bluehole_source
        bluehole = bluehole_source.validate(bluehole if bluehole is not None else state.get('bluehole', {'enabled': False, 'branch': 'main'}))
        commit = None
        installed_branch = bluehole['branch']
        fallback = False
        if bluehole['enabled']:
            try:
                addon, commit = bluehole_source.update(manager, release, bluehole['branch'], cancelled=cancelled)
            except bluehole_source.UpdateUnavailable as error:
                check_cancelled(cancelled)
                addon, installed_branch, commit = bluehole_source.installed_fallback(manager, release, root, state)
                fallback = True
                self.warnings.append(f'{error}. Using installed Blue Hole {installed_branch} · {commit[:12]}; update and Deluxe changes will be retried next launch.')
            resolved = [item for item in resolved if item.identity != bluehole_source.IDENTITY]
            resolved.append(addon)
        resolved.sort(key=lambda a: (a.name.casefold(), a.module.casefold(), a.identity))
        new = {}
        payloads = []
        for addon in resolved:
            module = f'bl_ext.logistics.{addon.module}' if addon.kind == 'Extension' else addon.module
            relative = (f'extensions/logistics/{addon.module}' if addon.kind == 'Extension' else
                        f'scripts/addons/{addon.module}' + ('.py' if not addon.prefix else ''))
            new[addon.identity] = {'module': module, 'path': relative, 'digest': addon.digest, 'name': addon.name, 'source': addon.source, 'version': addon.version, 'published': addon.published, 'package_name': addon.package_name}
            payloads.append((addon, relative))
        old = state['installed']
        # Only paths published by this library may be replaced/removed.
        for entry in list(old.values()) + list(new.values()):
            rel = relative_path(entry['path'])
            if (len(rel.parts) != 3 or rel.parts[:2] not in [('scripts', 'addons'), ('extensions', 'logistics')]):
                raise ValueError('Invalid managed addon destination')
            manager._contained(root, *rel.parts)
        for key, entry in new.items():
            target = root / entry['path']
            if target.exists() and not any(e['path'] == entry['path'] for e in old.values()):
                raise ValueError(f'{target.name} already exists outside the addon library; move it before selecting this addon')
        retained = {key for key, entry in new.items() if key in old
                    and all(entry[field] == old[key][field] for field in ('module', 'path', 'digest'))
                    and ((root / entry['path']).is_file() if entry['path'].endswith('.py') else
                         (root / entry['path'] / '__init__.py').is_file())}
        manager.environment(release, name)  # Validate all resource folders before copying.
        environments = manager._contained(root, 'addon-data', 'bluehole')
        with TemporaryDirectory(prefix='.addon-update-', dir=root.parent) as temp:
            backup = Path(temp)
            packages = backup / 'packages'
            packages.mkdir()
            snapshots = {}
            for index, addon in enumerate(resolved):
                if addon.identity in retained and not (addon.identity == bluehole_source.IDENTITY and bluehole['deluxe'] and not fallback):
                    snapshots[addon.identity] = addon
                    continue
                staged_package = packages / f'{index}.zip'
                with addon.package.open('rb') as source, staged_package.open('wb') as output:
                    copy_stream(source, output, cancelled=cancelled)
                if inspect_package(staged_package).digest != addon.digest:
                    raise ValueError(f'{addon.name} ZIP changed before installation; refresh and try again')
                snapshots[addon.identity] = replace(addon, package=staged_package)
            resolved = [snapshots[addon.identity] for addon in resolved]
            payloads = [(snapshots[addon.identity], relative) for addon, relative in payloads]
            folders = ('config', 'scripts', 'extensions', 'addon-data')
            existing = {folder for folder in folders if (root / folder).exists()}
            for folder in folders:
                if folder in existing:
                    shutil.copytree(root / folder, backup / folder, symlinks=True)
            try:
                previous_bluehole = old.get(bluehole_source.IDENTITY)
                if previous_bluehole and (root / previous_bluehole['path']).is_dir():
                    if environments.exists():
                        shutil.rmtree(environments)
                    bluehole_source.preserve_environments(root / previous_bluehole['path'], environments, cancelled=cancelled)
                for key, entry in old.items():
                    if key in retained:
                        continue
                    target = root / entry['path']
                    if target.is_dir():
                        shutil.rmtree(target)
                    elif target.exists():
                        target.unlink()
                for addon, relative in payloads:
                    if addon.identity in retained:
                        continue
                    target = root / relative
                    with zipfile.ZipFile(addon.package) as archive:
                        for member in archive.infolist():
                            check_cancelled(cancelled)
                            if member.is_dir() or (addon.prefix and not member.filename.startswith(addon.prefix)):
                                continue
                            suffix = member.filename[len(addon.prefix):]
                            output = target / relative_path(suffix) if addon.prefix or addon.kind == 'Extension' else target
                            output.parent.mkdir(parents=True, exist_ok=True)
                            with archive.open(member) as source, output.open('wb') as out:
                                copy_stream(source, out, cancelled=cancelled)
                            mode = (member.external_attr >> 16) & 0o777
                            if os.name != 'nt' and mode:
                                output.chmod(mode)
                    if addon.identity == bluehole_source.IDENTITY:
                        bluehole_source.preserve_environments(environments, target, cancelled=cancelled)
                deluxe_stamp = state.get('bluehole', {}).get('deluxe_stamp') if fallback else None
                if bluehole['enabled'] and bluehole['deluxe'] and not fallback:
                    bluehole_addon = next(a for a in resolved if a.identity == bluehole_source.IDENTITY)
                    deluxe_stamp = bluehole_source.apply_deluxe(bluehole_addon, root,
                                    state.get('bluehole', {}).get('deluxe_stamp'), cancelled=cancelled)
                request = backup / 'request.json'
                request.write_text(json.dumps({'enable': [e['module'] for e in new.values()],
                                               'disable': [e['module'] for e in old.values() if e['module'] not in [v['module'] for v in new.values()]],
                                               'extensions': str(root / 'extensions/logistics') if any(a.kind == 'Extension' for a in resolved) else ''}), encoding='utf-8')
                from .addons import run_blender_script
                run_blender_script(executable, manager.environment(release, name), Path(__file__).with_name('apply_addons.py'),
                                   request, cancelled=cancelled)
                check_cancelled(cancelled)
                staged = root / '.logistics-addons.tmp'
                manager._contained(root, staged.name)
                staged.write_text(json.dumps({'selected': sorted(set(identities)), 'installed': new, 'installed_bluehole': {'branch': installed_branch, 'commit': commit, 'version': new.get(bluehole_source.IDENTITY, {}).get('version', '')} if commit else None, 'bluehole': {**bluehole, 'commit': commit, 'deluxe_stamp': deluxe_stamp}}, indent=2), encoding='utf-8')
                staged.replace(root / '.logistics-addons.json')
            except BaseException:
                for folder in folders:
                    if (root / folder).exists():
                        shutil.rmtree(root / folder)
                    if folder in existing:
                        shutil.copytree(backup / folder, root / folder, symlinks=True)
                raise
        return root
