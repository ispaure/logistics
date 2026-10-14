"""Installed build identity, independent of network access and update checks."""
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class BuildVersion:
    version: str = 'Development build'
    revision: str = ''
    committed_at: str = ''
    modified: bool = False

    @property
    def label(self):
        identity = ' · '.join(filter(None, (self.version, self.revision[:10])))
        timestamp = ''
        if self.committed_at:
            try:
                timestamp = datetime.fromisoformat(self.committed_at).astimezone().strftime('%Y-%m-%d %H:%M %Z')
            except ValueError:
                pass
        detail = ' · '.join(filter(None, (timestamp, 'modified' if self.modified else '')))
        return identity + ('\n' + detail if detail else '')

    @property
    def details(self):
        return '\n'.join(filter(None, (self.version, self.revision,
                                      'Commit time: ' + self.committed_at if self.committed_at else '',
                                      'Local changes are present.' if self.modified else '')))


def installed_build(root=ROOT):
    root = Path(root)
    try:
        if (root / '.git').exists():
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                                      text=True, timeout=3, check=True).stdout.strip()
            revision = git('rev-parse', 'HEAD')
            timestamp = git('show', '-s', '--format=%cI', 'HEAD')
            try:
                tag = git('describe', '--tags', '--exact-match', 'HEAD')
            except subprocess.CalledProcessError:
                tag = git('branch', '--show-current') or 'Development build'
            return BuildVersion(tag, revision, timestamp, bool(git('status', '--porcelain',
                                '--untracked-files=no', '--ignore-submodules=none')))
        path = root / '.app-version.json'
        if path.exists():
            if path.stat().st_size > 4096:
                return BuildVersion()
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                return BuildVersion()
            revision = data['revision']
            tag, timestamp = data.get('tag', ''), data.get('committed_at', '')
            if (not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{40,64}', revision)
                    or not isinstance(tag, str) or len(tag) > 100
                    or not isinstance(timestamp, str) or len(timestamp) > 100
                    or any(ord(char) < 32 for char in tag + timestamp)):
                return BuildVersion()
            return BuildVersion(tag or 'Source build', revision, timestamp)
        # Releases created before build stamping still carry the install marker.
        data = json.loads((root / '.app-install.json').read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return BuildVersion()
        revision = data.get('revision', '')
        if isinstance(revision, str) and re.fullmatch(r'[a-f0-9]{40,64}', revision):
            return BuildVersion('Source build', revision)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        pass
    return BuildVersion()
