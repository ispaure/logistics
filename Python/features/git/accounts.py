"""Credential-helper integration; secrets never enter preference files or logs."""
import os
from pathlib import Path
import shutil
import sys
from .runner import GitError
from .options import validate_account


def credential_store():
    return 'keychain' if sys.platform == 'darwin' else 'wincredman' if os.name == 'nt' else 'secretservice'


def secure_helper(runner):
    folder = runner.run(['--exec-path']).stdout.decode().strip()
    suffix = '.exe' if os.name == 'nt' else ''
    native = 'osxkeychain' if sys.platform == 'darwin' else 'libsecret' if os.name != 'nt' else 'manager'
    for name in dict.fromkeys((native, 'manager')):
        program = 'git-credential-' + name + suffix
        if shutil.which(program) or (Path(folder) / program).is_file(): return name
    raise GitError('Install Git Credential Manager or a native secure Git credential helper first. Plaintext storage is not used.')


def change_credential(runner, account, token=None, *, erase=False):
    validate_account(account)
    if account['protocol'] == 'ssh': return None
    helper = account.get('helper') or secure_helper(runner)
    if helper not in ('osxkeychain', 'libsecret', 'manager'): raise GitError('A secure credential helper is required.')
    payload = f'protocol=https\nhost={account["host"]}\nusername={account["username"]}\n'
    if not erase:
        if not token or len(token.encode()) > 2048 or any(ord(c) < 32 for c in token): raise GitError('Enter a token without control characters (up to 2 KiB).')
        payload += f'password={token}\n'
    args = ['-c', 'credential.credentialStore=' + credential_store()] if helper == 'manager' else []
    # Invoke only the approved helper directly; never Git's configured helper chain,
    # which could contain credential-store or a shell command from a repository.
    previous = runner.config_options
    try:
        runner.config_options = {'credential.credentialStore': credential_store()} if helper == 'manager' else {}
        return runner.run([*args, 'credential-' + helper, 'erase' if erase else 'store'],
                          input_data=(payload + '\n').encode(), sensitive=True)
    finally: runner.config_options = previous


def browser_login_command(executable):
    import shlex
    import subprocess
    args = [executable, '-c', 'credential.credentialStore=' + credential_store(),
            'credential-manager', 'github', 'login']
    return ('set "GCM_CREDENTIAL_STORE=wincredman" && ' + subprocess.list2cmdline(args)) if os.name == 'nt' else 'GCM_CREDENTIAL_STORE=' + credential_store() + ' ' + shlex.join(args)
