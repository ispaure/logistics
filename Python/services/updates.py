"""Logistics update policy and handoff. Shared runtime owns file/Git transactions."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import mkdtemp

from commonUtils.runtime.updates.github import GitHubSource
from commonUtils.runtime.updates.transaction import MARKER, head, prepare_git, prepare_archive
from features.preferences import preferences_path
from features.settings import settings_store

ROOT = Path(__file__).resolve().parents[2]
BRANCHES = ('main', 'beta', 'alpha')
PROTECTED = ('.git', '.env', '.env.*', '.venv', 'venv', 'env', 'ENV', 'Software', 'Credentials',
             'RemoteCredentials', 'Addons', 'pyCharmProjects', 'Temp', 'temp', '__pycache__', '*.conf')


@dataclass(frozen=True)
class UpdateChoice:
    enabled: bool
    branch: str


def choice():
    from commonUtils.configuration.layered import effective_settings
    settings = effective_settings(ROOT / 'Python/configFile.ini', case_sensitive=False)
    branch = settings.get('Updates', 'branch_mode', fallback='main')
    if branch not in BRANCHES:
        raise ValueError('Choose main, beta or alpha for Logistics updates')
    return UpdateChoice(settings.getboolean('Updates', 'enabled_bool', fallback=True), branch)


def source():
    return GitHubSource('ispaure/logistics', {'Python/commonUtils': 'ispaure/commonUtils'})


def installed_revision(root=ROOT):
    if (root / '.git').exists():
        return head(root)
    return json.loads((root / MARKER).read_text(encoding='utf-8'))['revision']


def check(root=ROOT):
    selected = choice()
    if not selected.enabled:
        return None
    current = installed_revision(root)
    client = source()
    release = client.latest_release(selected.branch)
    if release is None or release['commit'] == current or not client.has_new_commits(current, release['commit']):
        return None
    return release


def restart_command(root=ROOT):
    if sys.platform == 'win32':
        launcher = root / 'LaunchLogistics_WIN.bat'
        if any(character in str(launcher) for character in '%"\r\n'):
            raise ValueError('Windows restart path contains unsupported characters')
        return ['cmd.exe', '/d', '/s', '/c', '""' + str(launcher) + '""']
    launcher = root / ('LaunchLogistics_MAC.command' if sys.platform == 'darwin' else 'LaunchLogistics_LINUX_UV.sh')
    return ['/bin/bash', str(launcher)]


def prepare(available, root=ROOT, state_root=None):
    selected = choice()
    if not selected.enabled or selected.branch != available['branch']:
        raise ValueError('Update preferences changed; check for updates again')
    state_root = state_root or preferences_path().parent / 'state' / 'updates'
    state_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(mkdtemp(prefix='prepared-', dir=state_root))
    try:
        snapshot = source().release_snapshot(available, workspace)
        if (root / '.git').exists():
            plan = prepare_git(root, available['commit'], PROTECTED, 'https://github.com/ispaure/logistics.git')
        else:
            plan = prepare_archive(root, snapshot, available['commit'], PROTECTED)
        from commonUtils.runtime.updates import transaction
        shutil.copy2(Path(transaction.__file__), workspace / 'apply_update.py')
        request = workspace / 'request.json'
        request.write_text(json.dumps({'pid': os.getpid(), 'plan': plan, 'restart': restart_command(root),
                                       'status': str(state_root / 'last-result.json')}, indent=2), encoding='utf-8')
        request.chmod(0o600)
        return request
    except BaseException:
        shutil.rmtree(workspace)
        raise


def launch_helper(request):
    """Called after the Qt event loop and host indexing service have stopped."""
    with (request.parent / 'update.log').open('ab') as log:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        return subprocess.Popen([sys.executable, str(request.parent / 'apply_update.py'), str(request)],
                                cwd=request.parent, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                start_new_session=os.name != 'nt', creationflags=flags, close_fds=True)


def settings_widget(parent=None, scope='personal'):
    from commonUtils.ui.settings.layered_settings import LayeredSettingsEditor
    return LayeredSettingsEditor(settings_store(ROOT / 'Python/configFile.ini'), parent, scope=scope,
                                 sections=['Updates'], labels={('Updates', 'enabled_bool'): 'Enable updates', ('Updates', 'branch_mode'): 'Update channel'})
