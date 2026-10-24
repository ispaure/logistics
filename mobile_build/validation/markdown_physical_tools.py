"""Run synthetic Markdown checks under a separately provisioned iOS QA identity."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
from tempfile import TemporaryDirectory
import time

from .markdown_rework_tools import BUNDLE, prepare


def device(*args, check=True, timeout=45):
    return subprocess.run(['xcrun', 'devicectl', *args], capture_output=True,
                          text=True, check=check, timeout=timeout)


def qa_entitlements(profile, udid):
    entitlements = dict(profile['Entitlements'])
    identifier = entitlements.get('application-identifier', '')
    prefix, _, suffix = identifier.partition('.')
    if (suffix not in (BUNDLE, '*')
            or udid not in profile.get('ProvisionedDevices', ())):
        raise ValueError('QA provisioning must match the separate bundle and the exact physical device.')
    if any('logisticsmobile' in str(value) for value in entitlements.values()):
        raise ValueError('QA entitlements must not grant access to the main application.')
    # Wildcard development profiles are valid, but the signed application's
    # actual privileges must be restricted to the exact QA identity.
    entitlements['application-identifier'] = prefix + '.' + BUNDLE
    entitlements['keychain-access-groups'] = [prefix + '.' + BUNDLE]
    return entitlements


def sign(app, udid):
    profile = plistlib.loads(subprocess.check_output(
        ['security', 'cms', '-D', '-i', str(app / 'embedded.mobileprovision')]))
    entitlements = qa_entitlements(profile, udid)
    identities = subprocess.check_output(['security', 'find-identity', '-v', '-p', 'codesigning'], text=True)
    certificates = [hashlib.sha1(value).hexdigest().upper() for value in profile['DeveloperCertificates']]
    identity = next((value for value in certificates if value in identities), None)
    if identity is None:
        raise ValueError('No local signing identity matches the QA profile.')
    for path in sorted((app / 'Frameworks').glob('*'), key=lambda p: len(p.parts), reverse=True):
        if path.suffix in ('.framework', '.dylib'):
            subprocess.run(['codesign', '--force', '--sign', identity, str(path)],
                           check=True, capture_output=True)
    path = app.parent / 'qa-entitlements.plist'
    path.write_bytes(plistlib.dumps(entitlements))
    subprocess.run(['codesign', '--force', '--sign', identity, '--entitlements', str(path), str(app)],
                   check=True, capture_output=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True, capture_output=True)


def run(source, udid, output, *, native_library=None, keyboard=False, timeout=240):
    if output.exists():
        raise ValueError('Choose a fresh evidence directory.')
    output.mkdir(parents=True)
    installed, console = False, None
    folder = 'editor-keyboard-evidence' if keyboard else 'markdown-rework-evidence'
    with TemporaryDirectory(prefix='markdown-physical-qa-') as directory:
        app = prepare(source, Path(directory), native_library=native_library)
        sign(app, udid)
        (output / 'source.json').write_bytes((app / 'app/markdown-qa-source.json').read_bytes())
        try:
            # Installation can complete on the device even when the transport
            # times out. Always attempt QA-only cleanup after dispatch.
            installed = True
            install = device('device', 'install', 'app', '--device', udid, str(app), timeout=180)
            (output / 'install.log').write_text(install.stdout + install.stderr)
            with (output / 'native-console.log').open('w') as stream:
                console = subprocess.Popen(['xcrun', 'devicectl', 'device', 'process', 'launch',
                    '--device', udid, '--terminate-existing', '--console', BUNDLE,
                    *(['--', '--keyboard'] if keyboard else [])], stdout=stream, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + timeout
            report = output / 'result.json'
            while time.monotonic() < deadline:
                result = device('device', 'copy', 'from', '--device', udid,
                    '--domain-type', 'appDataContainer', '--domain-identifier', BUNDLE,
                    '--source', 'Library/Caches/' + folder + '/result.json',
                    '--destination', str(report), check=False)
                if result.returncode == 0 and report.exists():
                    value = json.loads(report.read_text())
                    if not value.get('success'):
                        raise RuntimeError(value.get('error', 'Physical Markdown checks failed.'))
                    return value
                if console.poll() is not None:
                    raise RuntimeError('Physical QA exited before reporting; inspect native-console.log.')
                time.sleep(1)
            raise TimeoutError('Physical QA timed out; inspect retained evidence.')
        finally:
            if installed:
                try:
                    for source_path, target in (('Library/Caches/' + folder, output / 'evidence'),
                                               ('Library/Caches/markdown-qa-python.log', output / 'python.log')):
                        copied = device('device', 'copy', 'from', '--device', udid,
                            '--domain-type', 'appDataContainer', '--domain-identifier', BUNDLE,
                            '--source', source_path, '--destination', str(target), check=False)
                        if copied.returncode:
                            (output / ('copy-' + target.name + '.log')).write_text(copied.stdout + copied.stderr)
                finally:
                    device('device', 'uninstall', 'app', '--device', udid, BUNDLE)
                    if console is not None:
                        try:
                            console.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            console.terminate()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', required=True, type=Path, help='A physical QA .app with its own provisioning profile')
    parser.add_argument('--device', required=True, help='Exact physical UDID included in the QA profile')
    parser.add_argument('--native-library', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--keyboard', action='store_true')
    args = parser.parse_args()
    result = run(args.app, args.device, args.output, native_library=args.native_library, keyboard=args.keyboard)
    print(json.dumps(dict(success=result['success'], physical=True, keyboard=args.keyboard)))
