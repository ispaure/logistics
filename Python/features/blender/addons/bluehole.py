"""Blue Hole packages from pinned GitHub commits or a local working tree."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import ast
from contextlib import contextmanager
from dataclasses import replace
import errno
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote
import zipfile

from commonUtils.persistence.publication import rename_exclusive
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.streams import copy_stream, iter_chunks, write_all
from features.blender.addons.library import Addon, inspect_package, legacy_version, version_string, version_tuple
from features.blender.installation.releases import relative_path

IDENTITY = 'legacy:BlueHole'
ADDON_PATH = 'scripts/addons/BlueHole'
BRANCHES = ('main', 'beta', 'alpha')
DEFAULT = {'enabled': True, 'branch': 'main', 'deluxe': False, 'auto_update': True}
VERSION_BRANCH = re.compile(r'blender-(\d+\.\d+\.\d+)/(main|beta|alpha)')


class UpdateOffline(ValueError):
    """GitHub could not be reached, allowing an installed-copy fallback."""


_UNREACHABLE = {
    getattr(errno, name)
    for name in ('ENETDOWN', 'ENETUNREACH', 'EHOSTDOWN', 'EHOSTUNREACH',
                 'WSAENETDOWN', 'WSAENETUNREACH', 'WSAEHOSTDOWN', 'WSAEHOSTUNREACH')
    if hasattr(errno, name)
}


@contextmanager
def _offline_on_network_error(message):
    try:
        yield
    except OSError as error:
        reason = error.reason if isinstance(error, URLError) else error
        if isinstance(error, HTTPError) or not isinstance(reason, OSError):
            raise
        if isinstance(reason, socket.gaierror):
            unreachable = reason.errno in (socket.EAI_AGAIN, socket.EAI_NONAME)
        else:
            unreachable = reason.errno in _UNREACHABLE
        if not unreachable:
            raise
        raise UpdateOffline(message) from error


class NoCompatibleBranch(ValueError):
    """Remote metadata was read successfully but no version baseline fits."""


def uses_runtime_deluxe(release):
    return version_tuple(release.version) >= (5, 2, 2)


def valid_branch(branch):
    return isinstance(branch, str) and (branch in BRANCHES or VERSION_BRANCH.fullmatch(branch) is not None)


def resolve_branch(channel, blender_version):
    """Resolve against the managed Blender release being launched, not the host Python version."""
    if channel not in BRANCHES:
        raise ValueError('Invalid Blue Hole channel')
    from commonUtils.runtime.updates.github import json_get
    names = []
    for page in range(1, 21):
        records = json_get(f'https://api.github.com/repos/ispaure/BlueHole/branches?per_page=100&page={page}')
        if not isinstance(records, list) or any(not isinstance(item, dict) or not isinstance(item.get('name'), str) for item in records):
            raise ValueError('GitHub returned invalid branch metadata')
        names.extend(item['name'] for item in records)
        if len(records) < 100:
            break
    else:
        raise ValueError('Blue Hole branch catalog exceeds the size limit')
    choices = [(version_tuple(match[1]), name) for name in names
               if (match := VERSION_BRANCH.fullmatch(name)) and match[2] == channel
               and version_tuple(match[1]) <= version_tuple(blender_version)]
    if choices:
        return max(choices)[1]
    if channel in names:  # Temporary compatibility while existing branches are renamed.
        return channel
    raise NoCompatibleBranch(f'No Blue Hole {channel} branch supports Blender {blender_version}')


def validate(value):
    if not isinstance(value, dict) or not isinstance(value.get('enabled'), bool) or value.get('branch') not in BRANCHES:
        raise ValueError('Choose main, beta or alpha for Blue Hole')
    if not isinstance(value.get('deluxe', False), bool):
        raise ValueError('Choose Yes or No for Blue Hole Deluxe')
    if not isinstance(value.get('auto_update', True), bool):
        raise ValueError('Choose whether to auto-update Blue Hole')
    config = {'enabled': value['enabled'], 'branch': value['branch'], 'deluxe': value.get('deluxe', False),
              'auto_update': value.get('auto_update', True)}
    source = value.get('source', 'github')
    if source not in ('local', 'github'):
        raise ValueError('Choose GitHub or Local for Blue Hole')
    path = value.get('path', '')
    if not isinstance(path, str):
        raise ValueError('Choose a local Blue Hole checkout folder')
    if source == 'local':
        config['source'] = source
    if source == 'local' or path:
        config['path'] = path
    return config


def checkout_git(root, *args):
    try:
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True,
                              timeout=30).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError('Could not read the Blue Hole checkout with Git') from error


def local_checkout(path):
    if not path.strip() or not Path(path).expanduser().is_absolute():
        raise ValueError('Choose the root folder of a local Blue Hole checkout')
    root = Path(path).expanduser().resolve()
    if not (root / '__init__.py').is_file() or not (root / '.git').exists():
        raise ValueError('Choose the root folder of a local Blue Hole checkout')
    if checkout_git(root, 'rev-parse', '--is-inside-work-tree').strip() != b'true':
        raise ValueError('Choose the root folder of a local Blue Hole checkout')
    return root


def local_addon(root, release):
    """Read metadata from the checked-out source without importing it."""
    from hashlib import sha256

    script = root / '__init__.py'
    if script.resolve() != script or script.stat().st_size > 1024 ** 2:
        raise ValueError('The Blue Hole checkout entrypoint is invalid')
    content = script.read_bytes()
    info = addon_info(content, script)
    if info.get('name') != 'Blue Hole':
        raise ValueError('The checkout is not the Blue Hole add-on')
    if uses_runtime_deluxe(release):
        profile = root / 'keymaps/deluxe-defaults.json'
        if not profile.is_file() or profile.resolve() != profile:
            raise ValueError('The Blue Hole checkout must contain keymaps/deluxe-defaults.json')
    addon = Addon(IDENTITY, info['name'], legacy_version(info.get('version', '')),
                  version_string(info['blender']) if info.get('blender') else '', '', 'Legacy addon',
                  'BlueHole', 'BlueHole/', (), None, sha256(content).hexdigest(),
                  source='Local checkout', package_name=str(root))
    if not addon.compatible(release):
        raise ValueError(f'The local Blue Hole checkout is not declared compatible with Blender {release.version}')
    return addon


def addon_info(content, script):
    from features.blender.addons.metadata import parse_addon_source

    try:
        for node in parse_addon_source(content.decode('utf-8-sig'), script).body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'bl_info'
                                                    for target in node.targets):
                info = ast.literal_eval(node.value)
                if isinstance(info, dict):
                    return info
    except (SyntaxError, UnicodeError) as error:
        raise ValueError('The Blue Hole metadata is invalid') from error
    raise ValueError('The Blue Hole metadata is invalid')


def branch_commit(branch):
    if not valid_branch(branch):
        raise ValueError('Invalid Blue Hole branch')
    from commonUtils.runtime.updates.github import json_get
    record = json_get(f'https://api.github.com/repos/ispaure/BlueHole/branches/{quote(branch, safe="")}')
    head = record.get('commit') if isinstance(record, dict) else None
    commit = head.get('sha') if isinstance(head, dict) else None
    if not isinstance(commit, str) or not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('GitHub returned an invalid Blue Hole commit')
    return commit


def download(commit, destination, cancelled):
    request = Request(f'https://codeload.github.com/ispaure/BlueHole/zip/{commit}',
                      headers={'User-Agent': 'Logistics-Blender'})
    with _offline_on_network_error('Could not reach GitHub to download Blue Hole'):
        response = urlopen(request, timeout=30)
    with response, destination.open('wb') as output:
        chunks = iter_chunks(response, cancelled=cancelled)
        while True:
            with _offline_on_network_error('Lost access to GitHub while downloading Blue Hole'):
                chunk = next(chunks, None)
            if chunk is None:
                break
            write_all(output, chunk, cancelled=cancelled)


def update(manager, release, branch, *, cancelled=lambda: False, step=lambda message: None):
    check_cancelled(cancelled)
    step(f'Checking Blue Hole {branch} on GitHub')
    with _offline_on_network_error(f'Could not reach GitHub to check Blue Hole {branch}'):
        remote_branch = resolve_branch(branch, release.version)
        check_cancelled(cancelled)
        commit = branch_commit(remote_branch)  # Always compare branch head, even with a warm cache.
    check_cancelled(cancelled)
    root = manager.root / 'addons' / 'bluehole'
    destination = manager._contained(root, remote_branch, commit)
    package = destination / 'addon.zip'
    # Reuse the old channel cache for the renamed original 4.5.1 family.
    legacy_package = manager._contained(root, branch, commit, 'addon.zip')
    if remote_branch == f'blender-4.5.1/{branch}' and legacy_package.is_file() and not package.is_file():
        package = legacy_package
    if not package.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        from features.blender.installation.install import installation_lock
        with installation_lock(destination):
            if not package.is_file():
                with TemporaryDirectory(prefix='.github-', dir=destination.parent) as temp:
                    workspace = Path(temp)
                    archive_path = workspace / 'github.zip'
                    step('Downloading Blue Hole from GitHub')
                    download(commit, archive_path, cancelled)
                    step('Preparing the Blue Hole GitHub package')
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
                    if addon.identity != IDENTITY or addon.name != 'Blue Hole':
                        raise ValueError('Unexpected Blue Hole addon identity')
                    check_cancelled(cancelled)
                    rename_exclusive(staged, destination)
    step('Checking the Blue Hole package')
    addon = replace(inspect_package(package), source=f'GitHub · {remote_branch}', branch=remote_branch)
    if addon.identity != IDENTITY or addon.name != 'Blue Hole':
        raise ValueError('Unexpected Blue Hole addon identity')
    if not addon.compatible(release):
        raise ValueError(f'Blue Hole ({branch}) is not declared compatible with Blender {release.version}')
    return addon, commit


def installed_fallback(manager, release, root, state):
    """Use only a recorded, present, declared-compatible installed Blue Hole copy."""
    entry = state['installed'].get(IDENTITY)
    current = state.get('installed_bluehole') or state.get('bluehole', {})
    if (not entry or entry['module'] != 'BlueHole' or entry['path'] != 'scripts/addons/BlueHole'
            or not isinstance(current, dict) or not valid_branch(current.get('branch'))
            or not isinstance(current.get('commit'), str) or not re.fullmatch(r'[a-f0-9]{40}', current['commit'])
            or not re.fullmatch(r'[a-f0-9]{64}', entry['digest'])):
        raise ValueError('No recorded installed Blue Hole copy is available for offline launch')
    match = VERSION_BRANCH.fullmatch(current['branch'])
    if match and version_tuple(match[1]) > version_tuple(release.version):
        raise ValueError('The installed Blue Hole branch requires a newer Blender version')
    script = manager._contained(root, 'scripts', 'addons', 'BlueHole', '__init__.py')
    if not script.is_file() or script.stat().st_size > 1024 ** 2:
        raise ValueError('The installed Blue Hole entrypoint is missing or invalid')
    info = addon_info(script.read_bytes(), script)
    if info.get('name') != 'Blue Hole':
        raise ValueError('The installed addon is not Blue Hole')
    try:
        version = legacy_version(info.get('version'))
    except ValueError as error:
        raise ValueError('The installed Blue Hole version is missing or invalid') from error
    addon = Addon(IDENTITY, info['name'], version,
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
    if addon.package is None:
        local_payload = Path(addon.package_name) / 'overlays/deluxe/payload'
        preference = (local_payload / 'userpref.blend').read_bytes()
        keymap = (local_payload / 'keyconfig/BH_Keymaps.py').read_bytes()
    else:
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
