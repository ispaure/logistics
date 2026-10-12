"""Blue Hole-only GitHub branch tracking; downloads are pinned to resolved commits."""
from dataclasses import replace
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen
import zipfile

from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.streams import copy_stream
from .library import inspect_package
from .releases import relative_path

IDENTITY = 'legacy:BlueHole'
BRANCHES = ('main', 'beta', 'alpha')
DEFAULT = {'enabled': True, 'branch': 'main', 'deluxe': False}


class UpdateUnavailable(ValueError):
    """A remote check/download failed, allowing an installed-copy fallback."""


def validate(value):
    if not isinstance(value, dict) or not isinstance(value.get('enabled'), bool) or value.get('branch') not in BRANCHES:
        raise ValueError('Choose main, beta or alpha for Blue Hole')
    if not isinstance(value.get('deluxe', False), bool):
        raise ValueError('Choose Yes or No for Blue Hole Deluxe')
    return {'enabled': value['enabled'], 'branch': value['branch'], 'deluxe': value.get('deluxe', False)}


def branch_commit(branch):
    if branch not in BRANCHES:
        raise ValueError('Invalid Blue Hole branch')
    from commonUtils.runtime.updates.github import GitHubSource
    return GitHubSource('ispaure/BlueHole').latest(branch)


def download(commit, destination, cancelled):
    request = Request(f'https://codeload.github.com/ispaure/BlueHole/zip/{commit}',
                      headers={'User-Agent': 'Logistics-Blender'})
    with urlopen(request, timeout=30) as response, destination.open('wb') as output:
        copy_stream(response, output, cancelled=cancelled)


def update(manager, release, branch, *, cancelled=lambda: False):
    check_cancelled(cancelled)
    try:
        commit = branch_commit(branch)  # Always compare branch head, even with a warm cache.
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise UpdateUnavailable(f'Could not check Blue Hole {branch}: {error}') from error
    check_cancelled(cancelled)
    root = manager.root / 'addons' / 'bluehole'
    destination = manager._contained(root, branch, commit)
    package = destination / 'addon.zip'
    if not package.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        from .install import installation_lock
        with installation_lock(destination):
            if not package.is_file():
                with TemporaryDirectory(prefix='.github-', dir=destination.parent) as temp:
                    workspace = Path(temp)
                    archive_path = workspace / 'github.zip'
                    try:
                        download(commit, archive_path, cancelled)
                    except OSError as error:
                        raise UpdateUnavailable(f'Could not download Blue Hole {branch}: {error}') from error
                    staged = workspace / 'release'
                    staged.mkdir()
                    # GitHub archive roots include a commit suffix; the addon module
                    # must retain its stable BlueHole identity across all branches.
                    with zipfile.ZipFile(archive_path) as source, zipfile.ZipFile(staged / 'addon.zip', 'w', zipfile.ZIP_DEFLATED) as output:
                        if len(source.infolist()) > 20000 or sum(m.file_size for m in source.infolist()) > 1024 ** 3:
                            raise ValueError('Blue Hole archive exceeds the package size limit')
                        roots = {PurePosixPath(m.filename).parts[0] for m in source.infolist()}
                        if len(roots) != 1:
                            raise ValueError('Unexpected Blue Hole archive layout')
                        for member in source.infolist():
                            check_cancelled(cancelled)
                            path = relative_path(member.filename)
                            if member.is_dir() or len(path.parts) < 2:
                                continue
                            info = zipfile.ZipInfo('BlueHole/' + '/'.join(path.parts[1:]))
                            info.external_attr = member.external_attr
                            with source.open(member) as inp, output.open(info, 'w') as out:
                                copy_stream(inp, out, cancelled=cancelled)
                    addon = inspect_package(staged / 'addon.zip')
                    if addon.identity != IDENTITY:
                        raise ValueError('Unexpected Blue Hole addon identity')
                    check_cancelled(cancelled)
                    staged.rename(destination)
    addon = replace(inspect_package(manager._contained(root, branch, commit, 'addon.zip')), source=f'GitHub · {branch}')
    if addon.identity != IDENTITY or not addon.compatible(release):
        raise ValueError(f'Blue Hole ({branch}) is not declared compatible with Blender {release.version}')
    return addon, commit


def installed_fallback(manager, release, root, state):
    """Use only a recorded, present, declared-compatible installed Blue Hole copy."""
    import ast
    from .library import Addon, legacy_version, version_string
    entry = state['installed'].get(IDENTITY)
    current = state.get('installed_bluehole') or state.get('bluehole', {})
    if (not entry or entry['module'] != 'BlueHole' or entry['path'] != 'scripts/addons/BlueHole'
            or not isinstance(current, dict) or current.get('branch') not in BRANCHES
            or not isinstance(current.get('commit'), str) or not re.fullmatch(r'[a-f0-9]{40}', current['commit'])
            or not re.fullmatch(r'[a-f0-9]{64}', entry['digest'])):
        raise ValueError('No recorded installed Blue Hole copy is available for offline launch')
    script = manager._contained(root, 'scripts', 'addons', 'BlueHole', '__init__.py')
    if not script.is_file() or script.stat().st_size > 1024 ** 2:
        raise ValueError('The installed Blue Hole entrypoint is missing or invalid')
    info = {}
    for node in ast.parse(script.read_text(encoding='utf-8-sig')).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'bl_info' for target in node.targets):
            info = ast.literal_eval(node.value)
            break
    if not isinstance(info, dict):
        raise ValueError('The installed Blue Hole metadata is invalid')
    addon = Addon(IDENTITY, str(info.get('name') or 'Blue Hole'), legacy_version(info.get('version', '')),
                  version_string(info['blender']) if info.get('blender') else '', '', 'Legacy addon',
                  'BlueHole', 'BlueHole/', (), None, entry['digest'], source=entry.get('source', f"GitHub · {current['branch']}"),
                  published=entry.get('published', ''), package_name=entry.get('package_name', ''))
    if not addon.compatible(release):
        raise ValueError('The installed Blue Hole copy is not declared compatible with this Blender version')
    return addon, current['branch'], current['commit']


def preserve_environments(previous, destination, *, cancelled=lambda: False):
    """Restore artist environments over a new payload; default stays publisher-owned."""
    import shutil
    previous, destination = Path(previous) / 'envFiles', Path(destination) / 'envFiles'
    if previous.is_symlink() or destination.is_symlink():
        raise ValueError('Blue Hole envFiles must be a real directory')
    if not previous.is_dir():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for entry in previous.iterdir():
        check_cancelled(cancelled)
        if entry.name.casefold() == 'default':
            continue
        target = destination / entry.name
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        if entry.is_symlink():
            target.symlink_to(entry.readlink(), target_is_directory=entry.is_dir())
        elif entry.is_dir():
            shutil.copytree(entry, target, symlinks=True)
        else:
            shutil.copy2(entry, target)


def apply_deluxe(addon, root, previous_stamp, *, cancelled=lambda: False):
    """Stamp the selected preset only when the requested Deluxe payload changes."""
    import hashlib
    for relative in ('config/userpref.blend', 'config/userpref.before-bluehole-deluxe.blend',
                     'scripts/presets/keyconfig/BH_Keymaps.py'):
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Deluxe destinations must stay inside the preset')
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(root)):
            raise ValueError('Deluxe destinations cannot use symbolic links')
    payload = 'BlueHole/overlays/deluxe/payload/'
    with zipfile.ZipFile(addon.package) as archive:
        preference = archive.read(payload + 'userpref.blend')
        keymap = archive.read(payload + 'keyconfig/BH_Keymaps.py')
    if not preference or not keymap:
        raise ValueError('Blue Hole Deluxe payload is missing or empty')
    stamp = hashlib.sha256(preference + keymap).hexdigest()
    if stamp != previous_stamp:
        check_cancelled(cancelled)
        config = root / 'config'
        current = config / 'userpref.blend'
        # Keep an inspectable copy before stamping an artist's saved preferences.
        backup = config / 'userpref.before-bluehole-deluxe.blend'
        if current.exists() and not backup.exists():
            import shutil
            shutil.copy2(current, backup)
        current.write_bytes(preference)
        destination = root / 'scripts/presets/keyconfig/BH_Keymaps.py'
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(keymap)
        check_cancelled(cancelled)
    return stamp
