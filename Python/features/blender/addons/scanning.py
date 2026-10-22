"""Inventory fallback reads metadata without importing third-party addon code."""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from time import monotonic
import tomllib

from commonUtils.runtime.operations import check_cancelled
from features.blender.addons.metadata import parse_addon_source


def scan_preset(root):
    root = Path(root)
    result = []
    legacy = root / 'scripts' / 'addons'
    if legacy.is_dir():
        for entry in sorted(legacy.iterdir()):
            script = entry / '__init__.py' if entry.is_dir() else entry
            if script.suffix != '.py' or entry.name.startswith(('.', '__')) or not script.is_file():
                continue
            info = {}
            try:
                tree = parse_addon_source(script.read_text(encoding='utf-8-sig'), script)
                for node in tree.body:
                    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'bl_info'
                                                            for target in node.targets):
                        value = ast.literal_eval(node.value)
                        if isinstance(value, dict):
                            info = value
                        break
            except (OSError, UnicodeError, SyntaxError, ValueError, TypeError):
                pass
            version = info.get('version', '')
            if isinstance(version, (tuple, list)):
                version = '.'.join(map(str, version))
            result.append({'module': entry.stem, 'name': str(info.get('name') or entry.stem),
                           'version': str(version), 'kind': 'Legacy addon', 'enabled': None, 'path': str(script)})
    extensions = root / 'extensions'
    if extensions.is_dir():
        # Extension layout is <repository>/<extension-id>/blender_manifest.toml.
        for manifest in sorted(extensions.glob('*/*/blender_manifest.toml')):
            try:
                info = tomllib.loads(manifest.read_text(encoding='utf-8'))
                if info.get('type') != 'add-on':
                    continue
                result.append({'module': f'bl_ext.{manifest.parent.parent.name}.{manifest.parent.name}',
                               'name': str(info.get('name') or manifest.parent.name),
                               'version': str(info.get('version', '')), 'kind': 'Extension',
                               'enabled': None, 'path': str(manifest.parent / '__init__.py')})
            except (OSError, UnicodeError, ValueError):
                continue
    return result


def inspect_addons(manager, release, name, *, cancelled=lambda: False, timeout=90):
    root = manager.preset(release, name)
    fallback = scan_preset(root)
    if not manager.ready(release):
        return fallback, 'Install Blender to read enabled state. Showing addons found in this preset.'
    check_cancelled(cancelled)
    with TemporaryDirectory(prefix='logistics-blender-inventory-') as workspace:
        output = Path(workspace) / 'addons.json'
        command = [str(manager.executable(release)), '--background', '--disable-autoexec', '--offline-mode',
                   '--python-exit-code', '1', '--python', str(Path(__file__).with_name('probe.py')),
                   '--', str(output)]
        try:
            # A file keeps native/third-party startup output from filling a pipe.
            with (Path(workspace) / 'probe.log').open('wb') as log:
                process = subprocess.Popen(command, env=manager.environment(release, name),
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=log)
                deadline = monotonic() + timeout
                try:
                    while process.poll() is None:
                        check_cancelled(cancelled)
                        if monotonic() >= deadline:
                            raise TimeoutError('Blender inventory timed out')
                        try:
                            process.wait(timeout=.1)
                        except subprocess.TimeoutExpired:
                            pass
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                if process.returncode:
                    raise ValueError('Blender could not inspect this preset')
            rows = json.loads(output.read_text(encoding='utf-8'))
            if not isinstance(rows, list) or any(not isinstance(row, dict) or
                    not {'module', 'name', 'version', 'kind', 'enabled', 'path'} <= row.keys() for row in rows):
                raise ValueError('Blender returned an invalid addon inventory')
            # Keep files that Blender cannot discover (for example incompatible addons).
            seen = {str(Path(row['path']).resolve()) for row in rows}
            rows.extend(row for row in fallback if str(Path(row['path']).resolve()) not in seen)
            return rows, 'Saved enabled state read from Blender. Refresh after saving changes in Blender.'
        except (OSError, ValueError, TimeoutError) as error:
            return fallback, f'{error}. Showing preset files; enabled state is unknown.'


def run_blender_script(executable, env, script, request, *, cancelled=lambda: False, timeout=90):
    """Bounded saved-preference update; logs stay private and child is always reaped."""
    with TemporaryDirectory(prefix='logistics-blender-apply-') as workspace:
        with (Path(workspace) / 'apply.log').open('wb') as log:
            process = subprocess.Popen([str(executable), '--background', '--factory-startup', '--disable-autoexec', '--offline-mode',
                                        '--python-exit-code', '1', '--python', str(script), '--', str(request)],
                                       env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            deadline = monotonic() + timeout
            try:
                while process.poll() is None:
                    check_cancelled(cancelled)
                    if monotonic() >= deadline:
                        raise TimeoutError('Blender addon update timed out')
                    try:
                        process.wait(timeout=.1)
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
        # Close the writer before reopening/copying the file on Windows.
        if process.returncode:
            log_path = Path(workspace) / 'apply.log'
            # Keep the complete log outside the rolled-back resource folders.
            # A unique file also avoids replacing an existing file or symlink.
            config = env.get('BLENDER_USER_CONFIG')
            directory = Path(config).parent if config else None
            try:
                with NamedTemporaryFile(prefix='blender-addons-error-', suffix='.log',
                                        dir=directory, delete=False) as saved, log_path.open('rb') as source:
                    shutil.copyfileobj(source, saved)
                    saved_path = saved.name
                location = f'\nFull Blender log: {saved_path}'
            except OSError as error:
                location = f'\nCould not preserve the full Blender log: {error}'
            detail = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '',
                            log_path.read_text(encoding='utf-8', errors='replace'))
            # Shutdown/unregister chatter can easily bury the actual exception.
            start = detail.find('Traceback (most recent call last):')
            if start >= 0:
                detail = detail[start:]
            if len(detail) > 6000:
                detail = detail[:4500] + '\n… (see full log) …\n' + detail[-1500:]
            raise ValueError(f'Blender could not apply addons (exit {process.returncode}). '
                             f'Previous files and preferences were restored.{location}\n{detail}')
