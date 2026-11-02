"""Offline notices from the installed runtime and the app's bundled components."""
from dataclasses import dataclass
from importlib import metadata
import ast
import json
from pathlib import Path
import sys
import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


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
    return Path(str(path)).name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'AUTHORS'))


def python_notices(requirements):
    """Follow installed dependencies, excluding extras and unrelated build tools."""
    pending, seen, notices = list(requirements), set(), []
    while pending:
        requirement = Requirement(pending.pop())
        if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
            continue
        key = canonicalize_name(requirement.name)
        if key in seen:
            continue
        seen.add(key)
        try:
            distribution = metadata.distribution(requirement.name)
        except metadata.PackageNotFoundError:
            continue
        pending.extend(distribution.requires or ())
        info = distribution.metadata
        texts = []
        for file in sorted(distribution.files or (), key=str):
            if _license_file(file) and not str(file).endswith(('.py', '.pyc')):
                text = _read(distribution.locate_file(file))
                if text and text not in texts:
                    texts.append(text)
        license_name = info.get('License-Expression') or info.get('License', '')
        # Some older wheels put the complete license in METADATA instead.
        if not texts and len(license_name) > 160:
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


def bundled_notices(root, platform):
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
        for entry in json.loads(catalog.read_text()):
            if platform in entry['platforms']:
                texts = [_read(directory / name) for name in entry.get('files', ())]
                version = sys.version.split()[0] if entry['name'] == 'Python runtime' else entry.get('version', '')
                notices.append(Notice(entry['name'], version, entry.get('license', ''),
                    entry.get('source', ''), '\n\n'.join(filter(None, [*texts, entry.get('note', '')]))))
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
    return notices


def installed_notices(*, root=None, platform=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    platform = platform or sys.platform
    notices = bundled_notices(root, platform) + python_notices(runtime_requirements(root, platform))
    if platform not in ('android', 'ios'):
        import config
        software = config.LogisticsConfig(create_resources=False).path_logistics_software
        notices.extend(desktop_native_notices(software))
    return sorted(notices, key=lambda item: (item.name.casefold(), item.version))


def desktop_native_notices(software):
    """Expose notices retained by the managed desktop LibVLC downloader."""
    notices = []
    for directory in sorted((Path(software) / 'video').glob('libvlc-*/notices')):
        texts = [_read(path) for path in sorted(directory.iterdir()) if path.is_file()]
        if any(texts):
            notices.append(Notice('LibVLC desktop runtime', directory.parent.name.removeprefix('libvlc-'),
                '', 'https://www.videolan.org/vlc/libvlc.html', '\n\n'.join(filter(None, texts))))
    return notices
