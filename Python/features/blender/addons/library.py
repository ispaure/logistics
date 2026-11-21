"""Private versioned addon library. Metadata is parsed, never imported."""
import ast
from contextlib import contextmanager
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

from commonUtils.filesystem.links import create_link, is_junction
from commonUtils.persistence.atomic import atomic_write_bytes
from commonUtils.persistence.publication import rename_exclusive
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.streams import copy_stream
from features.blender.installation.releases import relative_path

SELECTION_FILE = '.logistics-addons.json'
RECOVERY_DIRECTORY = '.addon-update-recovery'


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
    branch: str = ''

    def compatible(self, release):
        return (bool(self.minimum) and version_tuple(release.version) >= version_tuple(self.minimum)
                and (not self.maximum or version_tuple(release.version) < version_tuple(self.maximum))
                and (not self.platforms or release.platform in self.platforms))


@dataclass(frozen=True)
class _PreparedApply:
    remove: tuple[tuple[str, Path], ...]
    install: tuple[tuple[Addon, Path], ...]
    old_checkout: Path | None
    new_checkout: Path | None
    previous_bluehole: Path | None
    environments: Path
    deluxe: Addon | None
    request: Path
    selection: dict


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
            from features.blender.addons.metadata import parse_addon_source
            tree = parse_addon_source(archive.read(marker).decode('utf-8-sig'), f'{package}!/{marker}')
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
        return Addon(package_identity(kind, module),
                     str(info.get('name') or module), legacy_version(info.get('version', '')) if kind == 'Legacy addon' else version_string(info.get('version', '')),
                     version_string(minimum) if minimum else '', version_string(maximum) if maximum else '',
                     kind, module, prefix, tuple(platforms), package, digest, published=package_date(package.name), package_name=package.name)


def package_identity(kind, module):
    return 'extension:' + module.rsplit('.', 1)[-1] if kind == 'Extension' else 'legacy:' + module


def addon_replacements(entries, state=None):
    """Map unambiguous extension successors to the saved legacy selection."""
    from features.blender.addons.bluehole import IDENTITY

    def normalized(value):
        return re.sub(r'[\s_-]+', '', value.casefold())

    legacy = [addon for addon in entries if addon.kind == 'Legacy addon' and addon.identity != IDENTITY]
    extensions = [addon for addon in entries if addon.kind == 'Extension']
    candidates = {}
    for extension in extensions:
        name = normalized(extension.name)
        for addon in legacy:
            if normalized(addon.name) != name:
                continue
            # The vendor confirms the Zen UV conversion, including packages with a renamed module.
            if (normalized(addon.module) == normalized(extension.module)
                    or (addon.identity == 'legacy:ZenUV' and name == 'zenuv')):
                candidates.setdefault(extension.identity, set()).add(addon.identity)
    counts = {}
    for matches in candidates.values():
        for identity in matches:
            counts[identity] = counts.get(identity, 0) + 1
    replacements = {}
    if state is not None:
        # Keep a confirmed pairing when one ZIP is removed from the library.
        replacements.update(state.get('replacements', {}))
    available = {addon.identity for addon in entries}
    for extension, legacy_id in list(replacements.items()):
        if extension in available and legacy_id in available:
            # Recheck an installed pairing when both packages can be compared.
            replacements.pop(extension)
    for identity, matches in candidates.items():
        if len(matches) == 1:
            match, = matches
            if counts[match] == 1 and match not in replacements.values():
                replacements[identity] = match
    return replacements


def record_replacements(state, replacements):
    selected = set(state['selected'])
    confirmed = {key: identity for key, identity in replacements.items() if identity in selected}
    if confirmed:
        state['replacements'] = confirmed
    else:
        state.pop('replacements', None)



class AddonLibrary:
    def __init__(self, manager, *, provided_root=None, preset_root=None):
        self.manager = manager
        self.errors = []
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
            state = self.selection(self.preset_root)
            legacy_identities = set(state['selected']) | set(state.get('replacements', {}))
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
            rename_exclusive(staged, destination)
        return replace(inspect_package(destination / 'addon.zip'), published=addon.published, package_name=addon.package_name, source='Preset' if self.preset_root is not None else 'Personal')

    def resolve(self, identity, release, *, entries=None, replacements=None):
        entries = self.entries() if entries is None else entries
        replacements = addon_replacements(entries) if replacements is None else replacements
        family = replacements.get(identity, identity)
        choices = [item for item in entries if replacements.get(item.identity, item.identity) == family
                   and item.compatible(release)]
        return max(choices, key=lambda item: (version_tuple(item.version), item.kind == 'Legacy addon', item.published),
                   default=None)

    def selection(self, root):
        recovery = root / RECOVERY_DIRECTORY
        if recovery.exists() or recovery.is_symlink() or is_junction(recovery):
            raise OSError(f'Blender preset needs recovery before it can be used. Recovery folder: {recovery}')
        path = root / SELECTION_FILE
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
        replacements = value.get('replacements', {})
        if (not isinstance(replacements, dict)
                or any(not re.fullmatch(r'extension:[A-Za-z_][A-Za-z_0-9]*', key)
                       or not isinstance(identity, str)
                       or not re.fullmatch(r'legacy:[A-Za-z_][A-Za-z_0-9]*', identity)
                       or identity == 'legacy:BlueHole' for key, identity in replacements.items())
                or len(set(replacements.values())) != len(replacements)):
            raise ValueError('Invalid preset addon replacements')
        return value

    def save_bluehole_source(self, release, name, source, path, *, auto_update=None):
        """Save source preferences independently of addon installation."""
        from features.blender.addons import bluehole
        from features.blender.installation.install import installation_lock

        root = self.manager.preset(release, name)
        with installation_lock(root):
            state = self.selection(root)
            choice = {**state.get('bluehole', bluehole.DEFAULT), 'source': source, 'path': path}
            if auto_update is not None:
                choice['auto_update'] = auto_update
            bluehole.validate(choice)
            state['bluehole'] = choice
            self._publish_selection(root, state)

    def save_pending_selection(self, release, name, identities, *, bluehole):
        """Save choices for the next launch while retaining installed state."""
        from features.blender.addons import bluehole as bluehole_source
        from features.blender.installation.install import installation_lock

        config = bluehole_source.validate(bluehole)
        if bluehole_source.uses_runtime_deluxe(release):
            config.pop('deluxe')
        root = self.manager.preset(release, name)
        if config['enabled'] and config.get('source') == 'local':
            checkout = bluehole_source.local_checkout(config['path'])
            if checkout.is_relative_to(root.resolve()) or root.resolve().is_relative_to(checkout):
                raise ValueError('Choose a Blue Hole checkout outside this Blender preset')
            bluehole_source.local_addon(checkout, release)
            config['path'] = str(checkout)
        with installation_lock(root):
            state = self.selection(root)
            previous = state.get('bluehole', {})
            if 'installed_bluehole' not in state and previous.get('commit'):
                state['installed_bluehole'] = {key: previous.get(key) for key in ('branch', 'commit')}
            if config.get('deluxe'):
                config['deluxe_stamp'] = previous.get('deluxe_stamp')
            catalog = self.for_preset(root)
            previous_ids = set(state['selected']) | set(state.get('replacements', {}))
            entries = catalog.entries(legacy_identities=previous_ids | set(identities))
            replacements = addon_replacements(entries, state)
            selected = sorted({replacements.get(identity, identity) for identity in identities})
            state.update(selected=selected, bluehole=config)
            record_replacements(state, replacements)
            self._publish_selection(root, state)

    def _publish_selection(self, root, state):
        path = self.manager._contained(root, SELECTION_FILE)
        atomic_write_bytes(path, json.dumps(state, indent=2).encode('utf-8'))

    def apply(self, release, name, identities, *, bluehole=None, cancelled=lambda: False, step=lambda message: None):
        from features.blender.installation.install import installation_lock
        root = self.manager.preset(release, name)
        with installation_lock(root), TemporaryDirectory(prefix='.addon-update-', dir=root.parent) as temp:
            return self._apply(release, name, root, identities, Path(temp), bluehole=bluehole,
                               cancelled=cancelled, step=step)

    def _apply(self, release, name, root, identities, workspace, *, bluehole, cancelled, step):
        from features.blender.addons import bluehole as bluehole_source
        from features.blender.addons.scanning import run_blender_script

        self.manager._require_idle(release, name)
        executable = self.manager.executable(release)
        plan = self._prepare_apply(release, root, identities, workspace, bluehole=bluehole,
                                   cancelled=cancelled, step=step)
        check_cancelled(cancelled)
        step('Backing up Blender preset')
        with self._apply_transaction(release, name, root, workspace, plan) as (environment, saved_link):
            if plan.previous_bluehole is not None:
                step('Preserving Blue Hole environments')
                if plan.environments.exists():
                    shutil.rmtree(plan.environments)
                bluehole_source.preserve_environments(plan.previous_bluehole, plan.environments, cancelled=cancelled)
            for addon_name, target in plan.remove:
                step(f'Removing {addon_name} files from the preset')
                if target == plan.old_checkout:
                    target.rename(saved_link)
                elif target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
            self._install_payloads(plan.install, plan.environments, cancelled=cancelled, step=step)
            if plan.deluxe is not None:
                step('Checking Blue Hole Deluxe preferences')
                choice = plan.selection['bluehole']
                choice['deluxe_stamp'] = bluehole_source.apply_deluxe(plan.deluxe, root, choice['deluxe_stamp'],
                                                                    cancelled=cancelled)
            step('Preparing Blender add-on preferences')
            run_blender_script(executable, environment, Path(__file__).with_name('apply_addons.py'),
                               plan.request, cancelled=cancelled)
            check_cancelled(cancelled)
            step('Saving Blender preset add-on state')
            self._publish_selection(root, plan.selection)
        return root

    def _prepare_apply(self, release, root, identities, workspace, *, bluehole, cancelled, step):
        """Resolve and verify the inputs without changing preset resources."""
        from features.blender.addons import bluehole as bluehole_source

        state = self.selection(root)
        identities = [identity for identity in identities if identity != bluehole_source.IDENTITY]
        step('Reading the Blender add-on library')
        identities, resolved, replacements = self._resolve_addons(release, root, identities, state)
        choice, addon, installed_bluehole, stamp_deluxe = self._resolve_bluehole(release, root, state, bluehole,
                                                                              cancelled=cancelled, step=step)
        if addon is not None:
            resolved.append(addon)
        resolved.sort(key=lambda a: (a.name.casefold(), a.module.casefold(), a.identity))
        old = state['installed']
        link_path = root / bluehole_source.ADDON_PATH
        old_checkout = link_path if self.checkout_link(root, state) is not None else None
        new_checkout = link_path if (installed_bluehole or {}).get('source') == 'local' else None
        new, payloads, retained = self._plan_managed_payloads(root, resolved, old, old_link=old_checkout, step=step)
        installed_commit = (state.get('installed_bluehole') or state.get('bluehole') or {}).get('commit')
        if old_checkout or new_checkout or (choice['commit'] and choice['commit'] != installed_commit):
            retained.discard(bluehole_source.IDENTITY)

        environments = self.manager._contained(root, 'addon-data', 'bluehole')
        previous_bluehole = old.get(bluehole_source.IDENTITY)
        previous = root / previous_bluehole['path'] if previous_bluehole and old_checkout is None else None
        packages = workspace / 'packages'
        packages.mkdir()
        snapshots = self._snapshot_packages(resolved, retained, packages, deluxe=stamp_deluxe,
                                            cancelled=cancelled, step=step)
        deluxe = None
        if stamp_deluxe:
            deluxe = snapshots[bluehole_source.IDENTITY]
            if deluxe.package is None and new_checkout is None:
                deluxe = replace(deluxe, package_name=str(link_path))  # Read from the retained installed copy.

        selection = {'selected': identities, 'installed': new, 'installed_bluehole': installed_bluehole,
                     'bluehole': choice}
        record_replacements(selection, replacements)
        request = workspace / 'request.json'
        enabled = [entry['module'] for entry in new.values()]
        enabled_modules = set(enabled)
        request.write_text(json.dumps({
            'enable': enabled,
            'disable': [entry['module'] for entry in old.values() if entry['module'] not in enabled_modules],
            'extensions': str(root / 'extensions/logistics') if any(a.kind == 'Extension' for a in resolved) else '',
        }), encoding='utf-8')
        return _PreparedApply(
            remove=tuple((entry.get('name') or entry['module'], root / entry['path'])
                         for key, entry in old.items() if key not in retained),
            install=tuple((snapshots[item.identity], root / relative) for item, relative in payloads
                          if item.identity not in retained),
            old_checkout=old_checkout, new_checkout=new_checkout,
            previous_bluehole=previous if previous is not None and previous.is_dir() else None,
            environments=environments, deluxe=deluxe, request=request, selection=selection,
        )

    def _resolve_bluehole(self, release, root, state, choice, *, cancelled, step):
        from features.blender.addons import bluehole as bluehole_source

        config = bluehole_source.validate(choice if choice is not None else state.get('bluehole', {'enabled': False, 'branch': 'main'}))
        runtime_deluxe = bluehole_source.uses_runtime_deluxe(release)
        if runtime_deluxe:
            config.pop('deluxe')
        stamp_deluxe = config['enabled'] and config.get('deluxe', False)
        addon = None
        installed = None
        commit = None
        installed_branch = config['branch']
        fallback = False
        current = state.get('installed_bluehole') or state.get('bluehole', {})
        if config['enabled']:
            if config.get('source') == 'local':
                step('Checking the local Blue Hole checkout')
                checkout = bluehole_source.local_checkout(config['path'])
                if checkout.is_relative_to(root.resolve()) or root.resolve().is_relative_to(checkout):
                    raise ValueError('Choose a Blue Hole checkout outside this Blender preset')
                addon = bluehole_source.local_addon(checkout, release)
                config['path'] = str(checkout)
                installed = {'source': 'local', 'path': config['path'], 'version': addon.version}
            elif (not config['auto_update'] and bluehole_source.IDENTITY in state['installed']
                  and current.get('source', 'github') == 'github'
                  and bluehole_source.valid_branch(current.get('branch'))
                  and current['branch'].rsplit('/', 1)[-1] == config['branch']):
                step('Checking installed Blue Hole (auto-update off)')
                addon, installed_branch, commit = bluehole_source.installed_fallback(self.manager, release, root, state)
            else:
                try:
                    addon, commit = bluehole_source.update(self.manager, release, config['branch'],
                                                          cancelled=cancelled, step=step)
                    installed_branch = addon.branch or config['branch']
                except bluehole_source.UpdateOffline:
                    check_cancelled(cancelled)
                    step('Checking installed Blue Hole')
                    addon, installed_branch, commit = bluehole_source.installed_fallback(self.manager, release, root, state)
                    fallback = True
            if commit:
                installed = {'branch': installed_branch, 'commit': commit, 'version': addon.version}
        config['commit'] = commit
        if not runtime_deluxe:
            config['deluxe_stamp'] = state.get('bluehole', {}).get('deluxe_stamp') if fallback or stamp_deluxe else None
        return config, addon, installed, stamp_deluxe and not fallback

    @contextmanager
    def _apply_transaction(self, release, name, root, workspace, plan):
        """Restore preset resources if provisioning, preparation or publication fails."""
        folders = [root / folder for folder in ('config', 'scripts', 'extensions', 'addon-data')]
        if any(path.is_symlink() or is_junction(path) for path in folders):
            raise ValueError('Preset resource folders cannot be links')
        existing = {path for path in folders if path.exists()}
        datafiles = root / 'datafiles'
        had_datafiles = datafiles.exists() or datafiles.is_symlink() or is_junction(datafiles)
        manifest = self.manager._contained(root, SELECTION_FILE)
        recovery = root / RECOVERY_DIRECTORY
        saved_link = recovery / 'BlueHole-link'
        recovery.mkdir()
        keep_recovery = False
        try:
            for path in folders:
                if path in existing:
                    ignore = self.ignore_checkout if plan.old_checkout and path.name == 'scripts' else None
                    shutil.copytree(path, recovery / path.name, symlinks=True, ignore=ignore)
            saved_manifest = recovery / SELECTION_FILE
            if manifest.exists():
                shutil.copy2(manifest, saved_manifest)
            (recovery / 'backup-complete').touch()
            try:
                yield self.manager.environment(release, name), saved_link
            except BaseException as error:
                try:
                    # The backup omits the linked checkout. Save or remove only the link itself.
                    if plan.old_checkout is not None and not (saved_link.is_symlink() or is_junction(saved_link)):
                        if not (plan.old_checkout.is_symlink() or is_junction(plan.old_checkout)):
                            raise OSError(f'Previous Blue Hole checkout link is missing: {plan.old_checkout}')
                        plan.old_checkout.rename(saved_link)
                    elif plan.new_checkout is not None:
                        self.remove_checkout_link(plan.new_checkout)
                    for path in folders:
                        if path.is_symlink() or is_junction(path):
                            self.remove_checkout_link(path)
                        elif path.exists():
                            shutil.rmtree(path)
                        if path in existing:
                            shutil.copytree(recovery / path.name, path, symlinks=True)
                    if saved_manifest.exists():
                        previous = saved_manifest.read_bytes()
                        if not manifest.exists() or manifest.read_bytes() != previous:
                            atomic_write_bytes(manifest, previous)
                    else:
                        manifest.unlink(missing_ok=True)
                    # Existing datafiles and anything written there are outside addon ownership.
                    if not had_datafiles and datafiles.is_dir() and not datafiles.is_symlink() and not is_junction(datafiles):
                        if not any(datafiles.iterdir()):
                            datafiles.rmdir()
                    if plan.old_checkout is not None:
                        saved_link.rename(plan.old_checkout)
                except BaseException as restore_error:
                    keep_recovery = True
                    raise OSError(f'Blender addon update failed: {error}\n'
                                  f'Rollback failed: {restore_error}\n'
                                  f'Recovery folder: {recovery}') from restore_error
                raise
        finally:
            if not keep_recovery:
                # Release the recovery guard only once commit or rollback has finished.
                discarded = workspace / 'discarded-backup'
                recovery.rename(discarded)
                self.remove_checkout_link(discarded / saved_link.name)

    @staticmethod
    def ignore_checkout(folder, _names):
        path = Path(folder)
        return {'BlueHole'} if path.name == 'addons' and path.parent.name == 'scripts' else set()

    @staticmethod
    def create_checkout_link(checkout, target):
        create_link(checkout, target, 'junction' if os.name == 'nt' else 'symbolic')

    @staticmethod
    def remove_checkout_link(target):
        if is_junction(target):
            target.rmdir()
        elif target.is_symlink():
            target.unlink()

    def checkout_link(self, root, state):
        """Recognize only the preset's recorded link without following it for mutations."""
        from features.blender.addons.bluehole import ADDON_PATH, IDENTITY

        entry = state['installed'].get(IDENTITY)
        current = state.get('installed_bluehole') or {}
        path = current.get('path')
        if (not entry or entry['module'] != 'BlueHole' or entry['path'] != ADDON_PATH
                or current.get('source') != 'local' or not isinstance(path, str)):
            return None
        target = self.manager._contained(root, 'scripts', 'addons') / 'BlueHole'
        checkout = Path(path)
        if not checkout.is_absolute():
            raise ValueError('Invalid recorded Blue Hole checkout path')
        if not target.is_symlink() and not is_junction(target):
            return None
        if target.resolve() != checkout:
            raise ValueError('The Blue Hole link points to a different checkout than the preset records')
        return checkout

    def _install_payloads(self, payloads, environments, *, cancelled, step):
        """Install verified packages inside the caller's backup/rollback boundary."""
        from features.blender.addons import bluehole as bluehole_source
        for addon, target in payloads:
            if addon.identity == bluehole_source.IDENTITY and addon.source == 'Local checkout':
                step('Linking the local Blue Hole checkout')
                self.create_checkout_link(Path(addon.package_name), target)
                continue
            step(f'Syncing {addon.name} files to the preset')
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

    def _resolve_addons(self, release, root, identities, state):
        """Resolve regular selections from one preset catalog before any mutation."""
        from features.blender.addons.scanning import scan_preset

        catalog = self.for_preset(root)
        visible = set(identities) | set(state['selected']) | set(state.get('replacements', {}))
        entries = catalog.entries(legacy_identities=visible)
        replacements = addon_replacements(entries, state)
        identities = sorted({replacements.get(identity, identity) for identity in identities})
        resolved = []
        for identity in identities:
            addon = self.resolve(identity, release, entries=entries, replacements=replacements)
            if addon is None:
                raise ValueError(f'No declared-compatible release is available for {identity}')
            resolved.append(addon)
        families = set(identities).intersection(replacements.values())
        if families:
            managed = {entry['module'] for entry in state['installed'].values()}
            for item in scan_preset(root):
                identity = package_identity(item['kind'], item['module'])
                if replacements.get(identity, identity) in families and item['module'] not in managed:
                    raise ValueError(f"{item['name']} is installed outside the addon library as {item['module']}; "
                                     'move that copy before applying the selection')
        return identities, resolved, replacements

    def _plan_managed_payloads(self, root, resolved, old, *, old_link=None, step):
        """Describe destinations and unchanged packages, rejecting unmanaged collisions."""
        from features.blender.addons import bluehole as bluehole_source

        new = {}
        payloads = []
        for addon in resolved:
            module = f'bl_ext.logistics.{addon.module}' if addon.kind == 'Extension' else addon.module
            relative = (f'extensions/logistics/{addon.module}' if addon.kind == 'Extension' else
                        f'scripts/addons/{addon.module}' + ('.py' if not addon.prefix else ''))
            new[addon.identity] = {'module': module, 'path': relative, 'digest': addon.digest, 'name': addon.name, 'source': addon.source, 'version': addon.version, 'published': addon.published, 'package_name': addon.package_name}
            payloads.append((addon, relative))
        # Only paths published by this library may be replaced/removed.
        for entry in list(old.values()) + list(new.values()):
            rel = relative_path(entry['path'])
            if (len(rel.parts) != 3 or rel.parts[:2] not in [('scripts', 'addons'), ('extensions', 'logistics')]):
                raise ValueError('Invalid managed addon destination')
            if old_link is None or rel.as_posix() != bluehole_source.ADDON_PATH:
                self.manager._contained(root, *rel.parts)
        retained = set()
        for key, entry in new.items():
            step(f'Comparing {entry["name"]} with the preset')
            target = root / entry['path']
            if target.exists() and not any(e['path'] == entry['path'] for e in old.values()):
                raise ValueError(f'{target.name} already exists outside the addon library; move it before selecting this addon')
            if (key in old and all(entry[field] == old[key][field] for field in ('module', 'path', 'digest'))
                    and (target.is_file() if entry['path'].endswith('.py') else (target / '__init__.py').is_file())):
                retained.add(key)
        return new, payloads, retained

    def _snapshot_packages(self, resolved, retained, packages, *, deluxe, cancelled, step):
        """Copy changed payloads and verify digests before the rollback-owned mutation."""
        from features.blender.addons import bluehole as bluehole_source
        snapshots = {}
        for index, addon in enumerate(resolved):
            if addon.source == 'Local checkout' or (
                    addon.identity in retained and not (addon.identity == bluehole_source.IDENTITY and deluxe
                                                        and addon.package is not None)):
                snapshots[addon.identity] = addon
                continue
            step(f'Verifying the {addon.name} package')
            staged_package = packages / f'{index}.zip'
            with addon.package.open('rb') as source, staged_package.open('wb') as output:
                copy_stream(source, output, cancelled=cancelled)
            if inspect_package(staged_package).digest != addon.digest:
                raise ValueError(f'{addon.name} ZIP changed before installation; refresh and try again')
            snapshots[addon.identity] = replace(addon, package=staged_package)
        return snapshots
