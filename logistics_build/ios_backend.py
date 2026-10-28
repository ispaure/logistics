"""Logistics simulator build/cache and strict per-device native validation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from build_manager.apple_simulators import AppleSimulators
from build_manager.native_commands import command, interrupt


def bundle_digest(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(str(path.lstat().st_mode & 0o777).encode())
        if path.is_symlink():
            digest.update(b'link:' + os.readlink(path).encode())
        elif path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()




def build(root, result):
    from mobile_build.validation import ui_tools
    mobile = root / 'mobile_build'
    app = mobile / 'build/logisticsmobile/ios/xcode/build/Debug-iphonesimulator/Logistics Mobile.app'
    cache = mobile / 'build/manager-ios-cache.json'
    source = json.loads((root / '.manager-source.json').read_text())['source']
    toolchain = dict(xcode=subprocess.check_output(['xcodebuild', '-version'], text=True).strip(),
                     sdk=subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-build-version'], text=True).strip(),
                     briefcase=subprocess.check_output([sys.executable, '-m', 'briefcase', '--version'], text=True).strip())
    key = dict(source=source, toolchain=toolchain)
    started = time.monotonic()
    reused = False
    if cache.exists():
        saved = json.loads(cache.read_text())
        if saved['key'] == key and app.is_dir() and saved['bundle_sha256'] == bundle_digest(app):
            reused = True
    if not reused:
        from logistics_build.mobile_payload import stage_payload
        stage_payload(root, sys.executable, command)
        command([sys.executable, 'cloud_build.py', 'licenses'], mobile)
        command([sys.executable, '-m', 'briefcase', 'create', 'iOS', '--no-input'], mobile)
        command([sys.executable, 'cloud_build.py', 'ios'], mobile)
        command([sys.executable, '-m', 'briefcase', 'build', 'iOS', '--test', '--no-input'], mobile)
    os.chdir(mobile)
    ui_tools.verify_prebuilt_ios(local=True)
    record = dict(key=key, bundle_sha256=bundle_digest(app), reused=reused,
                  seconds=time.monotonic()-started, status='passed', app=str(app))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(record, indent=2)+'\n')
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(json.dumps(record, indent=2)+'\n')


def cleanup(lease):
    if not lease.exists():
        return
    record = json.loads(lease.read_text())
    AppleSimulators().remove(record['device'], record['name'])
    lease.unlink()


def test(root, result, kind, model, runtime, lease):
    from mobile_build.validation import ui_tools
    from uuid import uuid4
    # A failed prior teardown must never lose its UUID to a fresh lease.
    if lease.exists():
        cleanup(lease)
    client = AppleSimulators()
    name = 'Build Manager ' + kind + ' ' + uuid4().hex
    result.parent.mkdir(parents=True, exist_ok=True)
    result.unlink(missing_ok=True)
    lease.parent.mkdir(parents=True, exist_ok=True)
    record = dict(kind=kind, model=model, runtime=runtime, status='running', source=json.loads((root/'.manager-source.json').read_text())['source'])
    started = time.monotonic()
    try:
        device = client.create(name, model, runtime)
        lease.write_text(json.dumps(dict(device=device, name=name)))
        record['device'] = device
        boot = time.monotonic()
        client.boot(device)
        record['startup_seconds'] = time.monotonic()-boot
        mobile = root/'mobile_build'
        os.chdir(mobile)
        launch = time.monotonic()
        report = ui_tools.run('ios', device, local=True, no_update=True,
                              require_duo=kind=='duo', require_independent_windows=kind=='ipad')
        record.update(status='passed', native_seconds=time.monotonic()-launch, report=report)
    except BaseException as error:
        record.update(status='cancelled' if isinstance(error, KeyboardInterrupt) else 'failed', error=str(error))
        raise
    finally:
        logs = root/'mobile_build/logs'
        if logs.exists():
            for path in logs.glob('ios-*'):
                if path.is_file():
                    shutil.copy2(path, result.parent/path.name)
        teardown = time.monotonic()
        try:
            cleanup(lease)
            record['owned_simulator_removed'] = True
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            record.update(status='failed', cleanup_error=str(error))
        record.update(teardown_seconds=time.monotonic()-teardown, seconds=time.monotonic()-started)
        result.write_text(json.dumps(record, indent=2)+'\n')
        if record['status'] != 'passed' and sys.exc_info()[0] is None:
            raise RuntimeError('Simulator test or cleanup failed; inspect per-device result.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'test', 'cleanup'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--result', type=Path)
    parser.add_argument('--kind', choices=['iphone','duo','ipad'])
    parser.add_argument('--model')
    parser.add_argument('--runtime')
    parser.add_argument('--lease', type=Path)
    args = parser.parse_args()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupt)
    if args.action == 'build':
        build(args.root, args.result)
    elif args.action == 'test':
        test(args.root, args.result, args.kind, args.model, args.runtime, args.lease)
    else:
        cleanup(args.lease)


if __name__ == '__main__':
    main()
