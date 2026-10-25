"""Pinned CPython iOS core tests in an owned disposable simulator testbed."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time
from uuid import uuid4

from build_manager.apple_simulators import AppleSimulators
from build_manager.locking import workspace_lock
from build_manager.profiles import save_json
from Scripts.ios_backend import bundle_digest, cleanup
from Scripts.ios_testbed import modernize, normalize_log
from Scripts.mobile_processes import command, interrupt
from Scripts.mobile_runtime import checksum, runtime_wheels, source


def pins():
    return json.loads(Path(__file__).with_name('mobile_runtime_tools.json').read_text())['cpython']


def toolchain():
    return dict(xcode=subprocess.check_output(['xcodebuild', '-version'], text=True).strip(),
                sdk=subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-build-version'], text=True).strip())


def framework(cache):
    return cache / 'cross-build/arm64-apple-ios-simulator/Apple/iOS/Frameworks/arm64-iphonesimulator'


def validate_prepared(cache):
    pin = pins()
    saved = json.loads((cache / 'prepared-manager-ios.json').read_text())
    if (saved['revision'] != pin['revision'] or saved['archive_sha256'] != pin['sha256']
            or saved['toolchain'] != toolchain() or not framework(cache).is_dir()
            or saved['framework_sha256'] != bundle_digest(framework(cache))):
        raise ValueError('Prepared iOS core runtime differs; inspect the owned cache before rebuilding.')
    return saved


def prepare(cache, result):
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise ValueError('This project-owned iOS core compiler requires a native macOS ARM host.')
    cache.parent.mkdir(parents=True, exist_ok=True)
    pin = pins()
    with workspace_lock(cache.parent / 'mobile-runtime.lock'):
        source(cache, pin)
        runtime_wheels(cache, download=True)
        saved = cache / 'prepared-manager-ios.json'
        if saved.exists():
            save_json(result, dict(validate_prepared(cache), reused=True))
            return
        host = cache / 'cross-build/build/python.exe'
        if not host.exists():
            previous = dict(os.environ)
            try:
                developer = Path(os.environ.get('DEVELOPER_DIR') or subprocess.check_output(['xcode-select', '-p'], text=True).strip())
                sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
                for link, target in [(cache / 'macos-sdk', Path(sdk)),
                                     (cache / 'xcode-toolchain', developer / 'Toolchains/XcodeDefault.xctoolchain')]:
                    if link.is_symlink() and link.resolve() != target.resolve():
                        raise ValueError('Cached compiler reference changed; inspect before rebuilding.')
                    if not link.exists():
                        link.symlink_to(target, target_is_directory=True)
                os.environ.update(SDKROOT=str(cache / 'macos-sdk'), CC=str(cache / 'xcode-toolchain/usr/bin/clang'),
                    CXX=str(cache / 'xcode-toolchain/usr/bin/clang++'),
                    PATH=str(developer / 'usr/bin') + os.pathsep + str(cache / 'xcode-toolchain/usr/bin') + os.pathsep + previous.get('PATH', ''))
                command([sys.executable, 'Apple', 'build', 'iOS', 'build', '--', '--with-openssl=/opt/homebrew/opt/openssl@3'], cache, 1800)
            finally:
                os.environ.clear()
                os.environ.update(previous)
        if not host.exists():
            host = cache / 'cross-build/build/python'
        version = subprocess.check_output([str(host), '-c', 'import platform;print(platform.python_version())'], text=True).strip()
        if version != pin['version']:
            raise ValueError('Pinned CPython host version mismatch.')
        command([sys.executable, 'Apple', 'build', 'iOS', 'arm64-apple-ios-simulator'], cache, 2400)
        downloads = cache / 'cross-build/downloads'
        record = dict(status='prepared', revision=pin['revision'], version=version, archive_sha256=pin['sha256'],
            host_sha256=checksum(host), framework_sha256=bundle_digest(framework(cache)), toolchain=toolchain(),
            dependencies={path.name: checksum(path) for path in downloads.iterdir() if path.is_file()})
        save_json(saved, record)
        save_json(result, record)


def test(root, cache, model, runtime, lease, output):
    from Scripts.build_retention import scratch
    with scratch(root) as run:
        _test(root, cache, model, runtime, lease, output, run)


def _test(root, cache, model, runtime, lease, output, run):
    from mobile_build import tools
    if lease.exists():
        cleanup(lease)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    record = dict(schema=1, status='running', success=False, target='ios', error='Core testbed did not complete.')
    started = time.monotonic()
    try:
        with workspace_lock(cache.parent / 'mobile-runtime.lock'):
            source(cache, pins())
            record['runtime_build'] = validate_prepared(cache)
            payload = run / 'payload'
            manifest = tools.stage(root, payload, testbed=True, allow_dirty=True)
            record['source'] = manifest
            command([sys.executable, '-m', 'pip', 'install', '--no-index', '--find-links', str(runtime_wheels(cache)),
                     '--target', str(payload), '--no-deps', 'markdown-it-py==4.2.0', 'mdurl==0.1.2'], root, 180)
            testbed = run / 'app'
            command([sys.executable, 'Apple/testbed', 'clone', '--platform', 'iOS', '--framework', str(framework(cache)), str(testbed)], cache, 180)
            record['testbed_compatibility'] = modernize(testbed)
            shutil.copytree(payload, testbed / 'iOSTestbed/app', dirs_exist_ok=True)
            spec = importlib.util.spec_from_file_location('logistics_owned_testbed', testbed / '__main__.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.update_test_plan(testbed, 'iOS', ['mobile.smoke', '--target', 'ios', '--local-source-sha256', manifest['source_sha256']])
            client = AppleSimulators()
            name = 'Build Manager core ' + uuid4().hex
            device = client.create(name, model, runtime)
            save_json(lease, dict(device=device, name=name))
            record.update(device=device, model=model, runtime=runtime)
            client.boot(device)
            base = ['xcodebuild', '-project', str(testbed / 'iOSTestbed.xcodeproj'), '-scheme', 'iOSTestbed',
                    '-destination', 'platform=iOS Simulator,id=' + device, '-derivedDataPath', str(testbed / 'DerivedData'),
                    '-parallel-testing-enabled', 'NO', 'IPHONEOS_DEPLOYMENT_TARGET=15.0']
            command([*base, 'build-for-testing'], testbed, 600)
            log = output.with_suffix('.log')
            raw = output.with_suffix('.raw.log')
            with raw.open('w') as stream:
                process = subprocess.Popen([*base, 'test-without-building'], cwd=testbed, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = process.wait(timeout=600)
                finally:
                    from build_manager.executor import stop_process
                    stop_process(process)
            normalize_log(raw, log)
            if code:
                raise RuntimeError('Native iOS core testbed failed: ' + str(code))
            verified = tools.verify(log, 'ios', output, local_manifest=payload / 'source.json')
            if verified['source'] != manifest:
                raise ValueError('Runtime source identity changed.')
            record.update(verified, status='passed', error='')
    except BaseException as error:
        record.update(status='cancelled' if isinstance(error, KeyboardInterrupt) else 'failed', success=False, error=str(error))
        raise
    finally:
        try:
            cleanup(lease)
            record['owned_simulator_removed'] = True
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            record.update(status='failed', success=False, error='Owned cleanup failed: ' + str(error))
        record['seconds'] = time.monotonic() - started
        save_json(output, record)
        if record['status'] != 'passed' and sys.exc_info()[0] is None:
            raise RuntimeError(record['error'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'test', 'cleanup'])
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--result', type=Path)
    parser.add_argument('--model')
    parser.add_argument('--runtime')
    parser.add_argument('--lease', type=Path)
    args = parser.parse_args()
    required = {'prepare': ('cache', 'result'), 'test': ('cache', 'root', 'result', 'model', 'runtime', 'lease'), 'cleanup': ('lease',)}
    for name in required[args.action]:
        if getattr(args, name) is None:
            parser.error('--' + name + ' is required for ' + args.action)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupt)
    if args.action == 'prepare':
        prepare(args.cache, args.result)
    elif args.action == 'test':
        test(args.root, args.cache, args.model, args.runtime, args.lease, args.result)
    else:
        cleanup(args.lease)


if __name__ == '__main__':
    main()
