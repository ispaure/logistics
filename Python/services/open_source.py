"""Offline notices from the installed runtime and the app's bundled components."""
from dataclasses import dataclass
from importlib import metadata
import ast
import json
from pathlib import Path
import sys
import sysconfig
import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from .license_inventory import is_notice, full_license


@dataclass(frozen=True)
class Notice:
    name: str
    version: str
    license: str
    source: str
    text: str

    @property
    def title(self):
        return ' '.join(filter(None, (self.name, self.version)))

    @property
    def content(self):
        return '\n\n'.join(filter(None, (self.title, self.license, self.source, self.text)))


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        return ''


def _license_file(path):
    return is_notice(path)


def python_notices(requirements):
    """Follow installed runtime dependencies, including explicitly requested extras."""
    pending = [(value, {''}) for value in requirements]
    seen, recorded, notices = {}, set(), []
    while pending:
        value, parent_extras = pending.pop()
        requirement = Requirement(value)
        if requirement.marker and not any(requirement.marker.evaluate({'extra': extra}) for extra in parent_extras):
            continue
        key = canonicalize_name(requirement.name)
        extras = {''} | requirement.extras
        if not extras - seen.get(key, set()):
            continue
        seen.setdefault(key, set()).update(extras)
        try:
            distribution = metadata.distribution(requirement.name)
        except metadata.PackageNotFoundError:
            continue
        pending.extend((value, extras) for value in distribution.requires or ())
        if key in recorded:
            continue
        recorded.add(key)
        info = distribution.metadata
        texts = []
        for file in sorted(distribution.files or (), key=str):
            if _license_file(file) and not str(file).endswith(('.py', '.pyc')):
                text = _read(distribution.locate_file(file))
                if text and text not in texts:
                    texts.append(text)
        license_name = info.get('License-Expression') or info.get('License', '')
        # Some older wheels put the complete license in METADATA instead.
        for name in (*(info.get_all('License-File') or ()), 'LICENSE', 'COPYING', 'licenses/LICENSE', 'licenses/COPYING'):
            text = distribution.read_text(name) if hasattr(distribution, 'read_text') else None
            if text and text.strip() not in texts:
                texts.append(text.strip())
        supplemental = Path(__file__).with_name('licenses') / 'python.json'
        if supplemental.is_file():
            entry = json.loads(supplemental.read_text()).get(key, {})
            if distribution.version == entry.get('version'):
                for name in entry.get('files', ()):
                    text = _read(supplemental.parent / name)
                    if text and text not in texts:
                        texts.append(text)
        if not texts and full_license(license_name):
            texts.append(license_name)
        notices.append(Notice(info.get('Name', requirement.name), distribution.version,
            license_name if len(license_name) < 160 else '',
            info.get('Home-page', '') or next(iter(info.get_all('Project-URL') or ()), ''),
            '\n\n'.join(texts) or 'No complete license text was supplied in this installed package.'))
    return notices


def runtime_requirements(root, platform):
    """Use the platform's declared runtime, never the build host's whole environment."""
    staged = root / 'mobile/open-source-dependencies.json'
    if staged.is_file():
        return json.loads(staged.read_text())[platform]
    project = root.parent / 'mobile_build/pyproject.toml'
    if platform in ('android', 'ios'):
        config = tomllib.loads(project.read_text())['tool']['briefcase']['app']['logisticsmobile']
        return config['requires'] + config['iOS' if platform == 'ios' else 'android']['requires']
    return tomllib.loads((root / 'pyproject.toml').read_text())['project']['dependencies']


def bundled_notices(root, platform, native_inventory=None):
    notices = []
    for name, paths in (
        ('Logistics', (root / 'mobile/LICENSE.md', root.parent / 'LICENSE.md')),
        ('commonUtils', (root / 'commonUtils/LICENSE.md',)),
        ('Pygments editor adaptation', (root / 'commonUtils/ui/code_editor/PYGMENTS_LICENSE.txt',)),
    ):
        text = next((value for path in paths if (value := _read(path))), '')
        if text:
            notices.append(Notice(name, '', '', '', text))
    codec = _read(root / 'features/notebooks/_vendor/rmscene/LICENSE.py')
    if codec:
        notices.append(Notice('rmscene', '0.8.0', 'MIT', 'https://github.com/ricklupton/rmscene',
                              ast.literal_eval(ast.parse(codec).body[0].value)))
    directory = Path(__file__).with_name('licenses')
    catalog = directory / 'native.json'
    if catalog.is_file():
        resolved = {item['module'] for item in (native_inventory or {}).get('components', ())}
        for entry in json.loads(catalog.read_text()):
            if platform in entry['platforms'] and entry.get('module') not in resolved:
                texts = [_read(directory / name) for name in entry.get('files', ())]
                version = sys.version.split()[0] if entry['name'] == 'Python runtime' else entry.get('version', '')
                source = entry.get('source', '')
                if entry['name'] == 'Python runtime':
                    exact = _read(Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt') or _read(directory / ('Python-' + version + '.txt'))
                    if exact:
                        texts = [exact]
                    elif version != entry.get('version'):
                        texts.append('The bundled reference text is from CPython ' + entry.get('version', '') +
                                     '; this runtime did not provide a matching license file.')
                    source = 'https://github.com/python/cpython/tree/v' + version
                notices.append(Notice(entry['name'], version, entry.get('license', ''),
                    source, '\n\n'.join(filter(None, [*texts, entry.get('note', '')]))))
    if platform not in ('ios', 'android'):
        qt_catalog = directory / 'qt-source-notices.json'
        if qt_catalog.is_file():
            data = json.loads(qt_catalog.read_text())
            try:
                version = metadata.version('PySide6')
            except metadata.PackageNotFoundError:
                version = ''
            if version == data['version']:
                for entry in data['components']:
                    notices.append(Notice('Qt third-party: ' + entry['name'], entry.get('version', ''),
                        entry.get('license', ''), entry.get('source', ''), '\n\n'.join(filter(None,
                        (entry['scope'], entry['provenance'], entry['text'],
                         'No complete license text was supplied in this source attribution.' if entry.get('missing_notice') else '')))))
            elif version:
                notices.append(Notice('Qt third-party inventory needs refresh', version, '', '',
                    'The bundled source notice inventory is for Qt ' + data['version'] + ', rather than this installed version.'))
        engine_catalog = directory / 'qtwebengine-source-notices.json'
        if engine_catalog.is_file():
            data = json.loads(engine_catalog.read_text())
            try:
                from PySide6.QtWebEngineCore import qWebEngineVersion
                engine_version = qWebEngineVersion()
            except ImportError:
                engine_version = ''
            if engine_version == data['version']:
                for entry in data['components']:
                    notices.append(Notice('Qt WebEngine third-party: ' + entry['name'], '', '', entry['source'],
                                          entry['scope'] + '\n\n' + entry['text']))
            elif engine_version:
                notices.append(Notice('Qt WebEngine third-party inventory needs refresh', engine_version, '', '',
                    'The bundled source notice inventory is for WebEngine ' + data['version'] + ', rather than this installed version.'))
        rclone_catalog = directory / 'rclone-dependency-notices.json'
        if rclone_catalog.is_file():
            data = json.loads(rclone_catalog.read_text())
            for entry in data['components']:
                notices.append(Notice('rclone dependency: ' + entry['name'], entry['version'], entry['license'],
                                      entry['source'], entry['scope'] + '\n\n' + entry['text']))
    for entry in (native_inventory or {}).get('components', ()):
        notices.append(Notice(entry['name'], entry['version'], entry.get('license', ''), entry.get('source', ''), entry['text']))
    # The native engine build already preserves each compiled Go module's notices.
    native = root / 'mobile/native-licenses'
    manifest = native / 'manifest.json'
    if manifest.is_file():
        for module in json.loads(manifest.read_text()):
            texts = [_read(native / item['file']) for item in module['notices']]
            notices.append(Notice(module['module'], module['version'], '', '', '\n\n'.join(filter(None, texts))))
        go = _read(native / 'Go-LICENSE')
        if go:
            notices.append(Notice('Go runtime', '', '', 'https://go.dev', go))
    elif platform in ('ios', 'android'):
        notices.append(Notice('Native Go dependency inventory unavailable', '', '', '',
            'This build does not include the native engine dependency notice manifest.'))
    return notices


def installed_notices(*, root=None, platform=None, native_inventory=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    platform = platform or sys.platform
    notices = bundled_notices(root, platform, native_inventory) + python_notices(runtime_requirements(root, platform))
    if platform not in ('android', 'ios'):
        import config
        software = config.LogisticsConfig(create_resources=False).path_logistics_software
        notices.extend(desktop_native_notices(software))
    return sorted(notices, key=lambda item: (item.name.casefold(), item.version))


def desktop_native_notices(software):
    """Expose notices retained by the managed desktop LibVLC downloader."""
    notices = []
    for directory in sorted((Path(software) / 'video').glob('libvlc-*/notices')):
        texts, seen = [], set()
        for path in sorted(directory.rglob('*')):
            if path.is_file() and (text := _read(path)) and text not in seen:
                seen.add(text)
                texts.append(path.relative_to(directory).as_posix() + '\n\n' + text)
        if any(texts):
            notices.append(Notice('LibVLC desktop runtime', directory.parent.name.removeprefix('libvlc-'),
                '', 'https://www.videolan.org/vlc/libvlc.html', '\n\n'.join(filter(None, texts))))
    return notices
