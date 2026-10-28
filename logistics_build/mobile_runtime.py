"""Pinned upstream CPython preparation and source-verified mobile runtime tests."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys

from build_manager import cpython_mobile, cpython_testbed
from build_manager.native_commands import command as native_command
from build_manager.locking import workspace_lock
from build_manager.native_commands import command, interrupt


def checksum(path):
    return cpython_mobile.checksum(path)


def source(cache, pin):
    return cpython_mobile.source(cache, pin)


def runtime_wheels(cache, *, download=False):
    pins = json.loads(Path(__file__).with_name('mobile_runtime_tools.json').read_text())['runtime_wheels']
    return cpython_mobile.runtime_wheels(cache, pins, download=download)


def host_interpreter(cache):
    return cpython_mobile.host_interpreter(cache)


def prepare(cache, result):
    settings = json.loads(Path(__file__).with_name('mobile_runtime_tools.json').read_text())
    return cpython_mobile.prepare_android(cache, result, settings['cpython'],
        library_relative=settings['preparation']['android_library'],
        host_configure_args=settings['preparation']['host_configure_args'],
        command=command, prepare_source=source, prepare_wheels=runtime_wheels)


def test(root, cache, serial, output):
    from mobile_build import tools
    payload=output.parent/'runtime-payload'
    output.parent.mkdir(parents=True,exist_ok=True)
    manifest=tools.stage(root,payload,testbed=True,allow_dirty=True)
    # These two pure-Python packages are the exact dependencies declared by the
    # canonical runtime workflow; they never contain native host binaries.
    cpython_testbed.install_payload_wheels(root, payload, runtime_wheels(cache),
        ['markdown-it-py==4.2.0', 'mdurl==0.1.2'], command=command)
    with workspace_lock(cache.parent/'mobile-runtime.lock'):
        with output.with_suffix('.log').open('w') as log:
            code = native_command(cpython_testbed.android_test_command(serial, payload,
                ['-m', 'mobile.smoke', '--target', 'android', '--local-source-sha256', manifest['source_sha256']]),
                cache, 1800, stdout=log, stderr=subprocess.STDOUT, check=False)
        if code:raise RuntimeError('Pinned Android runtime testbed failed: '+str(code))
        report=tools.verify(output.with_suffix('.log'),'android',output,local_manifest=payload/'source.json')
        if report['source']!=manifest:raise ValueError('Runtime source identity changed.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','test'])
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--root',type=Path)
    parser.add_argument('--serial')
    args=parser.parse_args()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupt)
    if args.action=='prepare':prepare(args.cache,args.result)
    else:test(args.root,args.cache,args.serial,args.result)


if __name__=='__main__':
    main()
