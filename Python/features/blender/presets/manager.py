"""Private paths, preset lifecycle and Blender process ownership."""
import os
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from features.preferences import preferences_path
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.streams import copy_stream
from features.blender.installation.install import installed, install_release, remove_installation
from features.blender.installation.releases import relative_path


def preset_name(value):
    value = value.strip()
    if (not value or len(value) > 80 or value.startswith('.') or value.endswith(('.', ' '))
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
            or value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                                              *(f'COM{i}' for i in range(1, 10)),
                                              *(f'LPT{i}' for i in range(1, 10))}):
        raise ValueError('Use a preset name without path separators, reserved names or special filename characters')
    return value


class BlenderManager:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else preferences_path().parent
        self.software = self.root / 'software' / 'blender'
        self.preferences = self.root / 'preferences' / 'blender'
        self.processes = []

    def _contained(self, root, *parts):
        path = root.joinpath(*parts)
        if (not path.resolve().is_relative_to(root.resolve())
                or not path.resolve().is_relative_to(self.root.resolve()) or path.is_symlink()):
            raise ValueError('Managed Blender paths must stay inside their Logistics folder')
        # Reject symlinked intermediate directories too, including version folders.
        for parent in path.parents:
            if parent == root.parent:
                break
            if parent.is_symlink():
                raise ValueError('Managed Blender directories cannot be symlinks')
        return path

    def installation(self, release):
        return self._contained(self.software, release.version)

    def preset(self, release, name):
        return self._contained(self.preferences, release.version, preset_name(name))

    def presets(self, release):
        folder = self._contained(self.preferences, release.version)
        if not folder.is_dir():
            return []
        return sorted((path.name for path in folder.iterdir() if path.is_dir() and not path.is_symlink()
                       and not path.name.startswith('.')), key=str.casefold)

    def ready(self, release):
        return installed(release, self.installation(release))

    def install(self, release, **kwargs):
        return install_release(release, self.installation(release), **kwargs)

    def running(self, release, name=None):
        self.processes = [(process, version, preset) for process, version, preset in self.processes
                          if process.poll() is None]
        return any(version == release.version and (name is None or preset == name)
                   for _, version, preset in self.processes)

    def _require_idle(self, release, name=None):
        if self.running(release, name):
            raise ValueError('Close the Blender instance launched by Logistics before changing its files')

    def remove(self, release):
        self._require_idle(release)
        remove_installation(release, self.installation(release))

    def create_preset(self, release, name):
        destination = self.preset(release, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir()  # Refuse overwrite.
        for folder in ('config', 'scripts/addons', 'scripts/presets', 'extensions', 'datafiles'):
            (destination / folder).mkdir(parents=True)
        return destination

    def duplicate_preset(self, release, source_name, name, *, target_release=None, cancelled=lambda: False):
        self._require_idle(release, source_name)
        source = self.preset(release, source_name)
        destination = self.preset(target_release or release, name)
        if destination.exists():
            raise ValueError('A preset with that name already exists')
        if not source.is_dir():
            raise ValueError('Source preset no longer exists')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.preset-', dir=destination.parent) as workspace:
            def copy(source, target):
                check_cancelled(cancelled)
                with open(source, 'rb') as inp, open(target, 'wb') as out:
                    copy_stream(inp, out, cancelled=cancelled)
                shutil.copystat(source, target)
                return target
            staged = Path(workspace) / 'preset'
            shutil.copytree(source, staged, symlinks=True, copy_function=copy)
            check_cancelled(cancelled)
            staged.rename(destination)
        return destination

    def rename_preset(self, release, source_name, name):
        self._require_idle(release, source_name)
        source, destination = self.preset(release, source_name), self.preset(release, name)
        if destination.exists():
            raise ValueError('A preset with that name already exists')
        source.rename(destination)
        return destination

    def remove_preset(self, release, name):
        self._require_idle(release, name)
        shutil.rmtree(self.preset(release, name))

    def environment(self, release, name):
        root = self.preset(release, name)
        if not root.is_dir():
            raise ValueError('Create or select an existing preset first')
        env = os.environ.copy()
        env['BLENDER_USER_RESOURCES'] = str(root)
        for key, folder in (('CONFIG', 'config'), ('SCRIPTS', 'scripts'),
                            ('EXTENSIONS', 'extensions'), ('DATAFILES', 'datafiles')):
            path = root / folder
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Preset resource folders must stay inside the preset')
            path.mkdir(parents=True, exist_ok=True)
            env[f'BLENDER_USER_{key}'] = str(path)
        return env

    def executable(self, release):
        if not self.ready(release):
            raise ValueError('Install this Blender version first')
        return self.installation(release) / relative_path(release.executable)

    def launch(self, release, name):
        executable = self.executable(release)
        from features.blender.addons.library import AddonLibrary
        state = AddonLibrary(self).selection(self.preset(release, name))
        entries = sorted(state['installed'].values(),
                         key=lambda entry: (entry.get('name', entry['module']).casefold(), entry['module'].casefold()))
        modules = [entry['module'] for entry in entries]
        if any(not re.fullmatch(r'(?:bl_ext\.logistics\.)?[A-Za-z_][A-Za-z_0-9]*', module) for module in modules):
            raise ValueError('Invalid managed addon module')
        command = [str(executable)]
        env = self.environment(release, name)
        env.pop('LOGISTICS_BLENDER_ADDONS', None)
        if modules:
            command.extend(['--addons', ','.join(modules), '--python', str(Path(__file__).parents[1] / 'addons' / 'launch_addons.py')])
            env['LOGISTICS_BLENDER_ADDONS'] = json.dumps(modules)
        process = subprocess.Popen(command, env=env,
                                   cwd=self.preset(release, name), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes.append((process, release.version, name))
        return process.pid


_default_manager = None


def get_manager():
    """Share launched-process ownership between the feature page and Settings."""
    global _default_manager
    if _default_manager is None:
        _default_manager = BlenderManager()
    return _default_manager
