"""Build a signed Android beta and distribute it to a verified Firebase group."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import tomllib
from urllib.request import urlopen

try:
    from . import android_deploy as android
    from .deployment_confirmation import gui_input
except ImportError:
    import android_deploy as android
    from deployment_confirmation import gui_input

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / '.android-beta'


def private_json(path, value):
    with open(path, 'w', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        json.dump(value, stream, indent=2)
    path.chmod(0o600)


def firebase_cli():
    local = ROOT / '.tools/firebase'
    local.parent.mkdir(parents=True, exist_ok=True)
    if local.is_file():
        return str(local)
    installed = shutil.which('firebase')
    if installed:
        return installed
    if sys.platform != 'darwin':
        raise ValueError('Install the Firebase CLI first: https://firebase.google.com/docs/cli')
    print('Downloading the official standalone Firebase CLI (no Node.js required)…', flush=True)
    local.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=local.parent) as temporary:
        download = Path(temporary) / 'firebase'
        with urlopen('https://firebase.tools/bin/macos/latest', timeout=120) as response, download.open('wb') as output:
            shutil.copyfileobj(response, output)
        download.chmod(0o755)
        subprocess.run([str(download), '--version'], check=True, cwd=ROOT / '.tools')
        download.replace(local)
    return str(local)


def firebase_json(cli, *args):
    # Firebase debug logs can contain authentication data; keep its cwd ignored.
    result = subprocess.run([cli, *args, '--json', '--non-interactive'],
                            cwd=ROOT / '.tools', capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Firebase access failed. Run deploy_android_firebase.command --login '
                         'and use the Google account that owns the Firebase project. '
                         'Also check App Distribution is enabled in the console.')
    return json.loads(result.stdout)['result']


def resolve_group(groups, requested):
    matches = [g for g in groups if requested.casefold() in
               (g['name'].rsplit('/', 1)[-1].casefold(), g.get('displayName', '').casefold())]
    if len(matches) != 1:
        raise ValueError('Cannot uniquely find group ' + requested + '. Available groups: ' +
                         ', '.join(g.get('displayName', g['name']) for g in groups))
    return matches[0]['name'].rsplit('/', 1)[-1]


def preflight(cli, *, login=False, allow_login=True):
    config = json.loads((ROOT / 'firebase-distribution.json').read_text())
    match = re.fullmatch(r'1:(\d+):android:[a-f0-9]+', config['app_id'])
    if not match or config['bundle_id'] != android.BUNDLE:
        raise ValueError('Invalid Firebase app/package configuration.')
    if login:
        subprocess.run([cli, 'login', '--reauth'], cwd=ROOT / '.tools', check=True)
    else:
        accounts = firebase_json(cli, 'login:list')
        if not accounts:
            if not allow_login:
                raise ValueError('Firebase sign-in is needed. Run Mobile/deploy_android_firebase.command --login once, then retry.')
            print('Sign in with the Google account that owns your Firebase project.', flush=True)
            subprocess.run([cli, 'login'], cwd=ROOT / '.tools', check=True)
    projects = firebase_json(cli, 'projects:list')
    project = next((p['projectId'] for p in projects if str(p['projectNumber']) == match[1]), None)
    if not project:
        raise ValueError('This Google account cannot access the configured Firebase project.')
    apps = firebase_json(cli, 'apps:list', 'ANDROID', '--project', project)
    app = next((a for a in apps if a['appId'] == config['app_id']), None)
    if not app or app.get('packageName') != android.BUNDLE:
        raise ValueError('Firebase app does not have package ' + android.BUNDLE + '. Check Project settings → Your apps.')
    groups = firebase_json(cli, 'appdistribution:groups:list', '--project', project)['groups']
    alias = resolve_group(groups, config['group'])
    print('Verified Firebase app and tester group: ' + alias, flush=True)
    return config, alias


def signing(env):
    key = PRIVATE / 'signing.p12'
    record = PRIVATE / 'signing.json'
    if record.exists():
        saved = json.loads(record.read_text())
        if not key.is_file():
            raise ValueError('Android beta signing key is missing. Restore .android-beta from backup; do not replace it.')
        return key, saved['password']
    if key.exists() or (ROOT / 'build/firebase').exists():
        raise ValueError('Signing record is missing. Restore .android-beta from backup before continuing.')
    password = secrets.token_urlsafe(32)
    # Persist before generating so interruption cannot silently replace an existing key.
    private_json(record, dict(password=password))
    key_env = dict(env, LOGISTICS_BETA_STORE_PASSWORD=password)
    subprocess.run([str(Path(env['JAVA_HOME']) / 'bin/keytool'), '-genkeypair', '-noprompt',
                    '-keystore', str(key), '-storetype', 'PKCS12', '-alias', 'logistics-beta',
                    '-storepass:env', 'LOGISTICS_BETA_STORE_PASSWORD', '-keyalg', 'RSA',
                    '-keysize', '3072', '-validity', '10000', '-dname', 'CN=Logistics Android Beta'],
                   env=key_env, check=True)
    key.chmod(0o600)
    print('Created private signing key. Back up Mobile/.android-beta securely.', flush=True)
    return key, password


def reserve_build():
    record = PRIVATE / 'build.json'
    previous = json.loads(record.read_text())['last_build'] if record.exists() else 0
    existing = [int(p.name) for p in (ROOT / 'build/firebase').glob('*') if p.name.isdigit()]
    number = max(int(datetime.now(timezone.utc).strftime('%Y%m%d')) * 10 + 1,
                 previous + 1, max(existing, default=0) + 1)
    if number > 2100000000:
        raise ValueError('Android version code limit exceeded.')
    private_json(record, dict(last_build=number))
    return number


def build():
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text())['tool']['briefcase']
    if config['bundle'] + '.logisticsmobile' != android.BUNDLE:
        raise ValueError('Android bundle identity changed.')
    env = android.deployment_environment()
    android.refresh_sources(env)
    env, _ = android.tools_environment(env)
    if not env.get('JAVA_HOME'):
        raise ValueError('Set JAVA_HOME to the JDK used by Briefcase.')
    key, password = signing(env)
    number = reserve_build()
    output = ROOT / 'build/firebase' / str(number)
    output.mkdir(parents=True)
    android.run([sys.executable, 'cloud_build.py', 'android'], env,
                log=output / 'bridge.log')
    # Use a Gradle init script so device/debug configuration is never rewritten.
    init = output / 'version.gradle'
    init.write_text('gradle.beforeProject { p ->\n'
                    '  p.pluginManager.withPlugin("com.android.application") {\n'
                    '    p.androidComponents.finalizeDsl { dsl ->\n'
                    f'      dsl.defaultConfig.versionCode = {number}\n'
                    '    }\n  }\n}\n')
    with (output / 'build.log').open('w') as log:
        subprocess.run([str(android.PROJECT / 'gradlew'), '--no-daemon', '-I', str(init),
                        'clean', ':app:assembleRelease'], cwd=android.PROJECT,
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    sdk = Path(env['ANDROID_HOME'])
    candidates = [p for p in (sdk / 'build-tools').iterdir()
                  if re.fullmatch(r'\d+(\.\d+)+', p.name) and (p / 'apksigner').is_file()]
    tools = max(candidates, key=lambda p: tuple(map(int, p.name.split('.'))))
    unsigned = android.PROJECT / 'app/build/outputs/apk/release/app-release-unsigned.apk'
    aligned = output / 'aligned.apk'
    apk = output / 'Logistics-android-beta.apk'
    subprocess.run([str(tools / 'zipalign'), '-f', '-p', '4', str(unsigned), str(aligned)], check=True, env=env)
    key_env = dict(env, LOGISTICS_BETA_STORE_PASSWORD=password)
    subprocess.run([str(tools / 'apksigner'), 'sign', '--ks', str(key),
                    '--ks-key-alias', 'logistics-beta', '--ks-pass', 'env:LOGISTICS_BETA_STORE_PASSWORD',
                    '--out', str(apk), str(aligned)], env=key_env, check=True)
    subprocess.run([str(tools / 'apksigner'), 'verify', '--verbose', str(apk)], env=env, check=True)
    metadata = subprocess.check_output([str(tools / 'aapt'), 'dump', 'badging', str(apk)], env=env, text=True)
    if f"name='{android.BUNDLE}'" not in metadata.splitlines()[0] or f"versionCode='{number}'" not in metadata.splitlines()[0]:
        raise ValueError('Built APK identity/version verification failed.')
    notes = output / 'release-notes.txt'
    notes.write_text(f'Logistics Android beta {config["version"]}, build {number}.\n'
                     'Built from current local sources, including uncommitted edits.\n')
    return apk, notes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--login', action='store_true', help='Sign in and verify Firebase setup only')
    parser.add_argument('--check', action='store_true', help='Verify Firebase app/group without building')
    parser.add_argument('--build-only', action='store_true', help='Build/sign without uploading')
    parser.add_argument('--gui', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    PRIVATE.chmod(0o700)
    try:
        with (PRIVATE / 'deploy.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            cli = firebase_cli()
            config, group = preflight(cli, login=args.login, allow_login=not args.gui)
            if args.login or args.check:
                return
            apk, notes = build()
            print('\nVerified APK: ' + str(apk), flush=True)
            if args.build_only:
                return
            if args.gui:
                ask = gui_input
            else:
                ask = input
            answer = ask('Upload this build to Firebase and notify ' + group + '? [y/N] ')
            if answer.strip().lower() not in ('y', 'yes'):
                print('Build saved. Nothing uploaded.')
                return
            subprocess.run([cli, 'appdistribution:distribute', str(apk), '--app', config['app_id'],
                            '--groups', group, '--release-notes-file', str(notes), '--non-interactive'],
                           cwd=ROOT / '.tools', check=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, EOFError) as error:
        print('Android beta stopped: ' + str(error), file=sys.stderr)
        print('Build logs: Mobile/build/firebase/<build>/. No app is uninstalled.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
