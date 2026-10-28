"""Pinned CPython iOS core tests in an owned disposable simulator testbed."""
import argparse
import json
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
from uuid import uuid4

from build_manager import cpython_mobile, cpython_testbed
from build_manager.native_commands import command as native_command
from build_manager.apple_simulators import AppleSimulators
from build_manager.locking import workspace_lock
from build_manager.profiles import save_json
from logistics_build.ios_backend import bundle_digest, cleanup
from logistics_build.ios_testbed import modernize, normalize_log
from build_manager.native_commands import command, interrupt
from logistics_build.mobile_runtime import checksum, runtime_wheels, source


def pins():
    return json.loads(Path(__file__).with_name('mobile_runtime_tools.json').read_text())['cpython']


def settings():
    return json.loads(Path(__file__).with_name('mobile_runtime_tools.json').read_text())['preparation']


def toolchain():
    return cpython_mobile.toolchain()


def framework(cache):
    return cpython_mobile.framework(cache, settings()['ios_framework'])


def validate_prepared(cache):
    return cpython_mobile.validate_ios(cache, pins(), framework_relative=settings()['ios_framework'],
                                      tree_digest=bundle_digest, current_toolchain=toolchain)


def prepare(cache, result):
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise ValueError('This project-owned iOS core compiler requires a native macOS ARM host.')
    options = settings()
    return cpython_mobile.prepare_ios(cache, result, pins(), target=options['ios_target'],
        framework_relative=options['ios_framework'], host_configure_args=options['host_configure_args'],
        command=command, prepare_source=source, prepare_wheels=runtime_wheels,
        tree_digest=bundle_digest, current_toolchain=toolchain)


def test(root, cache, model, runtime, lease, output):
    from logistics_build.build_retention import scratch
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
            cpython_testbed.install_payload_wheels(root, payload, runtime_wheels(cache),
                ['markdown-it-py==4.2.0', 'mdurl==0.1.2'], command=command)
            testbed = run / 'app'
            record['testbed_compatibility'] = cpython_testbed.prepare_ios(
                cache, testbed, framework(cache), payload,
                ['mobile.smoke', '--target', 'ios', '--local-source-sha256', manifest['source_sha256']],
                command=command, adapt=modernize)
            client = AppleSimulators()
            name = 'Build Manager core ' + uuid4().hex
            device = client.create(name, model, runtime)
            save_json(lease, dict(device=device, name=name))
            record.update(device=device, model=model, runtime=runtime)
            client.boot(device)
            base = cpython_testbed.ios_build_command(testbed, device,
                                                    deployment_target=settings()['ios_deployment_target'])
            command([*base, 'build-for-testing'], testbed, 600)
            log = output.with_suffix('.log')
            raw = output.with_suffix('.raw.log')
            with raw.open('w') as stream:
                code = native_command([*base, 'test-without-building'], testbed, 600,
                                      stdout=stream, stderr=subprocess.STDOUT, check=False)
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
