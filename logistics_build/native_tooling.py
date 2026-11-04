"""Explicit project-owned native prerequisites; inspection never downloads tools."""
import argparse
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
REMEDY = 'Set up the mobile environment, then explicitly Update project tooling (CLI: tooling --update --confirm).'
GO_MARKER = '.logistics-native-tool.json'
WHEEL_RECEIPT = 'langdetect-receipt.json'


def declared():
    return json.loads(Path(__file__).with_suffix('.json').read_text())


def host_key():
    system = {'Darwin': 'darwin', 'Linux': 'linux', 'Windows': 'windows'}.get(platform.system())
    arch = {'x86_64': 'amd64', 'AMD64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine())
    return f'{system}-{arch}'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def owned(root, path):
    from logistics_build.tooling_bootstrap import owned_path
    if not owned_path(root, path):
        raise ValueError('Native tooling refuses linked destinations. Preserve the existing path. ' + REMEDY)


def go_path(root):
    return Path(root) / 'mobile_build/.tools/go/bin' / ('go.exe' if os.name == 'nt' else 'go')


def go_status(root, *, environment=None):
    env = dict(os.environ if environment is None else environment, GOTOOLCHAIN='local', GOTELEMETRY='off')
    local = go_path(root)
    # An explicit project selector wins even when broken; never silently borrow PATH.
    selector = local.parent.parent
    executable = str(local) if selector.exists() or selector.is_symlink() else shutil.which('go', path=env.get('PATH', ''))
    result = dict(ready=False, executable=executable, expected=declared()['go_version'])
    if executable:
        try:
            process = subprocess.run([executable, 'version'], capture_output=True, text=True, env=env, timeout=10)
            text = process.stdout.strip()
            result.update(version=text.split()[2].removeprefix('go') if text.startswith('go version go') else None,
                          resolved_executable=str(Path(executable).resolve()))
            result['ready'] = process.returncode == 0 and result['version'] == result['expected'] and len(text) < 1024
        except (OSError, subprocess.SubprocessError):
            pass
    if not result['ready']:
        result['message'] = REMEDY
    return result


def wheel_metadata(path):
    """Reject platform wheels, links, traversal and unexpected executable content."""
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > 5000 or sum(row.file_size for row in entries) > 32 * 1024 * 1024:
            raise ValueError('Unexpected native prerequisite wheel size.')
        for row in entries:
            parts = PurePosixPath(row.filename)
            if parts.is_absolute() or '..' in parts.parts or '\\' in row.filename or (row.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Unsafe native prerequisite wheel entry.')
            if parts.suffix.lower() in ('.so', '.pyd', '.dll', '.dylib', '.exe'):
                raise ValueError('Native prerequisite wheel must be pure Python.')
        prefix = 'langdetect-1.0.9.dist-info/'
        metadata = BytesParser().parsebytes(archive.read(prefix + 'METADATA'))
        wheel = BytesParser().parsebytes(archive.read(prefix + 'WHEEL'))
        tags = wheel.get_all('Tag', [])
        if metadata['Name'] != 'langdetect' or metadata['Version'] != declared()['langdetect']['version'] or wheel['Root-Is-Purelib'] != 'true' or not tags or any(not tag.endswith('-none-any') for tag in tags):
            raise ValueError('Incorrect native prerequisite wheel metadata.')
        if not any(tag.split('-')[0] in ('py3', 'py2.py3') for tag in tags):
            raise ValueError('Native prerequisite wheel must support Python 3.')
        return tags


def readable(path):
    from logistics_build.tooling_bootstrap import linked
    if any(linked(part) for part in (path, *path.parents)):
        raise ValueError('Linked wheel inputs are not eligible.')


def wheel_status(root, *, directory=None):
    directory = Path(directory) if directory is not None else Path(root) / 'mobile_build/.tools/release-wheels'
    result = dict(ready=False, directory=str(directory))
    try:
        readable(directory)
        receipt = directory / WHEEL_RECEIPT
        readable(receipt)
        if receipt.stat().st_size > 16384:
            raise ValueError('Oversized wheel receipt.')
        proof = json.loads(receipt.read_text())
        expected = declared()['langdetect']
        filename = proof.get('filename', '')
        if (proof.get('schema') != 1 or proof.get('source_sha256') != expected['sha256']
                or Path(filename).name != filename or not filename.startswith('langdetect-1.0.9-') or not filename.endswith('.whl')):
            raise ValueError('Wheel receipt does not match the pinned source.')
        path = directory / filename
        readable(path)
        if path.stat().st_size > 32 * 1024 * 1024 or digest(path) != proof['wheel_sha256']:
            raise ValueError('Wheel bytes changed after preparation.')
        wheel_metadata(path)
        result.update(ready=True, filename=filename, sha256=proof['wheel_sha256'])
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
        result['message'] = REMEDY
    return result


def status(root=ROOT):
    root = Path(root)
    supported = host_key() in declared()['go']
    suffix = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
    applicable = supported and (root / 'mobile_build/.venv' / suffix).is_file()
    if not applicable:
        return dict(applicable=False, ready=False, message='Native setup requires a supported host and a project mobile environment.')
    go, wheel = go_status(root), wheel_status(root)
    return dict(applicable=True, ready=go['ready'] and wheel['ready'], go=go, wheel=wheel,
                message='Native prerequisites are ready.' if go['ready'] and wheel['ready'] else REMEDY)


def download(record, destination):
    """Trust tracked pins, not a checksum discovered during installation."""
    url = record.get('url', 'https://go.dev/dl/' + record['filename'])
    if not url.startswith(('https://go.dev/dl/', 'https://files.pythonhosted.org/')):
        raise ValueError('Unapproved native tooling download origin.')
    with urllib.request.urlopen(url, timeout=30) as response, destination.open('xb') as output:
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > record['size']:
                raise ValueError('Native tooling download exceeds its pinned size.')
            output.write(chunk)
    if total != record['size'] or digest(destination) != record['sha256']:
        raise ValueError('Native tooling download does not match its tracked checksum.')


def extract_go(archive, destination):
    destination.mkdir()
    if archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as source:
            entries = source.infolist()
            if sum(row.file_size for row in entries) > 1024 ** 3:
                raise ValueError('Oversized Go archive.')
            for row in entries:
                name = PurePosixPath(row.filename)
                if name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] != 'go' or '\\' in row.filename or (row.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Unsafe Go archive entry.')
            source.extractall(destination)
    else:
        with tarfile.open(archive) as source:
            entries = source.getmembers()
            if sum(row.size for row in entries) > 1024 ** 3:
                raise ValueError('Oversized Go archive.')
            for row in entries:
                name = PurePosixPath(row.name)
                if name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] != 'go' or not (row.isfile() or row.isdir()):
                    raise ValueError('Unsafe Go archive entry.')
            source.extractall(destination, members=entries, filter='data')
    return destination / 'go'


def provision(root=ROOT):
    """Called only by the owning bootstrap, under its mutation/workflow guard."""
    from logistics_build.build_retention import scratch
    from logistics_build.tooling_bootstrap import atomic_json
    root = Path(root).resolve()
    current = status(root)
    if not current['applicable'] or current['ready']:
        return current
    # Never reset/adopt an existing installation. Valid user-selected SDKs are read-only.
    destination = root / 'mobile_build/.tools/go'
    if not current['go']['ready'] and (destination.exists() or destination.is_symlink()):
        raise ValueError('The selected Go SDK conflicts with the pin. Preserve it and move the selector aside. ' + REMEDY)
    wheel_dir = root / 'mobile_build/.tools/release-wheels'
    owned(root, wheel_dir)
    if not current['wheel']['ready'] and wheel_dir.exists() and any(wheel_dir.iterdir()):
        raise ValueError('The wheel directory is unverified. Preserve it and move it aside. ' + REMEDY)
    with scratch(root) as work:
        if not current['go']['ready']:
            owned(root, destination)
            record = declared()['go'][host_key()]
            archive = work / record['filename']
            download(record, archive)
            staged = extract_go(archive, work / 'extracted')
            probe = subprocess.run([str(staged / 'bin' / ('go.exe' if os.name == 'nt' else 'go')), 'version'],
                env=dict(os.environ, GOTOOLCHAIN='local', GOTELEMETRY='off'), capture_output=True, text=True, timeout=10)
            if probe.returncode or not probe.stdout.startswith('go version go' + declared()['go_version'] + ' '):
                raise ValueError('Extracted Go SDK failed version verification.')
            atomic_json(staged / GO_MARKER, dict(schema=1, archive_sha256=record['sha256'], version=declared()['go_version']))
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged.rename(destination)
        if not current['wheel']['ready']:
            record = declared()['langdetect']
            archive = work / record['filename']
            download(record, archive)
            output = work / 'wheels'
            output.mkdir()
            # Outer bootstrap owns this process group and its pip descendants.
            subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
                '--no-index', '--wheel-dir', str(output), str(archive)], check=True, timeout=120,
                env=dict(os.environ, PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_CACHE_DIR=str(work / 'pip-cache')))
            wheels = list(output.glob('*.whl'))
            if len(wheels) != 1:
                raise ValueError('Expected exactly one pure langdetect wheel.')
            wheel_metadata(wheels[0])
            atomic_json(output / WHEEL_RECEIPT, dict(schema=1, filename=wheels[0].name,
                source_sha256=record['sha256'], wheel_sha256=digest(wheels[0]), python=sys.version.split()[0]))
            if not wheel_status(root, directory=output)['ready']:
                raise ValueError('Prepared wheel receipt failed verification.')
            if wheel_dir.exists():
                wheel_dir.rmdir()  # Only an empty directory was accepted above.
            output.rename(wheel_dir)
    result = status(root)
    if not result['ready']:
        raise ValueError('Native tooling verification failed. ' + REMEDY)
    return result


def require_owner(root, nonce):
    """A standalone invocation cannot bypass environment/workflow exclusion."""
    from logistics_build.tooling_bootstrap import ActiveWorkflowError, file_lock, lock_path, read_intent
    try:
        with file_lock(lock_path(root)):
            pass
    except ActiveWorkflowError:
        pass
    else:
        raise ValueError('Native setup requires the owning tooling repair lock. ' + REMEDY)
    if sys.platform == 'win32':
        # Windows venv launchers can insert redirector processes. Authority is
        # the held project lock plus the parent's one-use launch capability,
        # never immediate-parent PID equality or a substitute Job implementation.
        from logistics_build.tooling_bootstrap import private
        capability = private(root) / 'native-setup-owner.json'
        owned(root, capability)
        if not capability.is_file() or capability.stat().st_size > 4096:
            raise ValueError('Native setup requires a bounded regular launch capability.')
        value = json.loads(capability.read_text())
        if value != dict(schema=1, root=str(Path(root).resolve()), nonce=nonce):
            raise ValueError('Native setup lacks the owning launch capability.')
        return
    deadline = time.monotonic() + 1
    while True:
        intent = read_intent(root)
        if not intent or intent['nonce'] != nonce:
            raise ValueError('Native setup lacks the owning mutation identity.')
        if dict(pgid=os.getpgrp(), sid=os.getsid(0)) in intent['groups']:
            return
        if time.monotonic() >= deadline:
            raise ValueError('Native setup process was not enrolled by its owner.')
        time.sleep(.01)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--owner-nonce', required=True)
    args = parser.parse_args()
    require_owner(args.root, args.owner_nonce)
    print(json.dumps(provision(args.root)))


if __name__ == '__main__':
    main()
