"""Install temporary distribution signing assets on a disposable CI runner."""
import argparse
import base64
import json
import os
from pathlib import Path
import plistlib
import secrets
import shlex
import shutil
import subprocess

from .testflight_tools import release_identity, validate_profile


def private_file(path, data):
    path.write_bytes(data)
    path.chmod(0o600)


def setup(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    keychain = root / 'signing.keychain-db'
    old_search = shlex.split(subprocess.check_output(['security', 'list-keychains', '-d', 'user'], text=True))
    state = dict(keychain=str(keychain), search=old_search, profile=None)
    private_file(root / 'cleanup.json', json.dumps(state).encode())
    cert = root / 'distribution.p12'
    profile = root / 'distribution.mobileprovision'
    private_file(cert, base64.b64decode(os.environ['IOS_DISTRIBUTION_P12_BASE64'], validate=True))
    private_file(profile, base64.b64decode(os.environ['IOS_APP_STORE_PROFILE_BASE64'], validate=True))
    values = plistlib.loads(subprocess.check_output(['security', 'cms', '-D', '-i', str(profile)]))
    identity = release_identity(os.environ['IOS_TEAM_ID'], os.environ['IOS_APP_IDENTIFIER'])
    validate_profile(values, identity)
    profile_dir = Path.home() / 'Library/Developer/Xcode/UserData/Provisioning Profiles'
    profile_dir.mkdir(parents=True, exist_ok=True)
    installed = profile_dir / (values['UUID'] + '.mobileprovision')
    if installed.exists():
        raise ValueError('Runner already contains this profile; refusing to overwrite it.')
    private_file(installed, profile.read_bytes())
    state['profile'] = str(installed)
    private_file(root / 'cleanup.json', json.dumps(state).encode())
    password = secrets.token_hex(24)
    commands = [
        ['security', 'create-keychain', '-p', password, str(keychain)],
        ['security', 'set-keychain-settings', '-lut', '21600', str(keychain)],
        ['security', 'unlock-keychain', '-p', password, str(keychain)],
        ['security', 'import', str(cert), '-k', str(keychain), '-P', os.environ['IOS_DISTRIBUTION_P12_PASSWORD'], '-T', '/usr/bin/codesign'],
        ['security', 'list-keychains', '-d', 'user', '-s', str(keychain), *old_search],
        ['security', 'set-key-partition-list', '-S', 'apple-tool:,apple:,codesign:', '-s', '-k', password, str(keychain)],
    ]
    for command in commands:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    key_id = os.environ['ASC_KEY_ID']
    import re
    if not re.fullmatch(r'[A-Z0-9]{10}', key_id):
        raise ValueError('Invalid App Store Connect key ID.')
    api_key = root / ('AuthKey_' + key_id + '.p8')
    private_file(api_key, os.environ['ASC_PRIVATE_KEY'].encode())
    with Path(os.environ['GITHUB_ENV']).open('a') as output:
        output.write('ASC_KEY_PATH=' + str(api_key) + '\nIOS_PROFILE_PATH=' + str(profile) + '\n')
    print('Temporary distribution signing assets installed.')


def cleanup(root):
    state_file = root / 'cleanup.json'
    if not state_file.exists():
        return
    state = json.loads(state_file.read_text())
    subprocess.run(['security', 'list-keychains', '-d', 'user', '-s', *state['search']], check=True)
    subprocess.run(['security', 'delete-keychain', state['keychain']], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if state['profile']:
        Path(state['profile']).unlink(missing_ok=True)
    shutil.rmtree(root)
    print('Temporary signing assets removed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('setup', 'cleanup'))
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    (setup if args.command == 'setup' else cleanup)(args.directory)
