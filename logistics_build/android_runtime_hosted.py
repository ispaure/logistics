"""Hosted CPython Android runtime gate with owned AVD and durable app receipts."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
from uuid import uuid4

from build_manager.android_emulators import AndroidEmulator
from build_manager.cpython_testbed import android_test_command
from build_manager.native_commands import command, interrupt
from logistics_build.build_retention import scratch
from logistics_build.test_environments import android_image, load
from mobile_build import tools

PACKAGE = 'org.python.testbed'
MAX_RECEIPT_BYTES = 1024 * 1024


def receipt_paths(token):
    if len(token) != 32 or any(char not in '0123456789abcdef' for char in token):
        raise ValueError('Receipt token must be a unique hexadecimal UUID.')
    name = 'logistics-runtime-' + token + '.json'
    # Pinned CPython823 PythonTestRunner uses files/python/cwd. Its asset
    # refresh deletes only files/python; retain this receipt outside that tree.
    return '../../' + name, 'files/' + name


def verify_receipt(path, manifest, output):
    from mobile.smoke import PREFIX
    if path.stat().st_size > MAX_RECEIPT_BYTES:
        raise ValueError('Android runtime receipt exceeds its bounded report size.')
    report = json.loads(path.read_text(encoding='utf-8'))
    expected = json.loads(Path(manifest).read_text(encoding='utf-8'))
    if not isinstance(report, dict) or report.get('source') != expected:
        raise ValueError('Android runtime receipt came from a different staged source.')
    evidence = Path(output).with_suffix('.receipt.log')
    evidence.write_text(PREFIX + json.dumps(report, sort_keys=True) + '\n', encoding='utf-8')
    return tools.verify(evidence, 'android', output)


def diagnostics(emulator, record, reports):
    # Diagnostics cannot turn a missing/failed receipt into acceptance.
    try:
        text = emulator.invoke('-s', record['serial'], 'logcat', '-d', '-t', '2000', timeout=15)
        (reports / 'android-logcat.log').write_text(text[-1024 * 1024:], encoding='utf-8')
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        (reports / 'android-logcat-error.txt').write_text(type(error).__name__, encoding='utf-8')
    for name in ('lease.json', 'removed-lease.json', 'emulator.log'):
        path = emulator.workspace / name
        if path.is_file():
            shutil.copyfile(path, reports / ('android-' + name))


def run(root, cpython, payload, reports, *, install_image=True):
    root, cpython, payload, reports = (Path(value).resolve() for value in (root, cpython, payload, reports))
    reports.mkdir(parents=True, exist_ok=True)
    values = load(root)
    image = android_image(values, hosted=True)
    sdk = Path(os.environ['ANDROID_HOME'])
    if install_image:
        with (reports / 'android-image-install.log').open('w') as log:
            command([str(sdk / 'cmdline-tools/latest/bin/sdkmanager'), 'emulator', image],
                    root, 600, stdout=log, stderr=subprocess.STDOUT)
    token = uuid4().hex
    app_receipt, adb_receipt = receipt_paths(token)
    with scratch(root) as workspace:
        emulator = AndroidEmulator(sdk, workspace / 'emulator', startup_timeout=240, gpu='swiftshader')
        record = None
        try:
            with emulator.session(image, values['android_model']) as record:
                emulator.verify(record)
                (reports / 'android-runtime-device.json').write_text(json.dumps(record, indent=2) + '\n')
                log = reports / 'android-testbed.log'
                code = None
                try:
                    with log.open('w') as stream:
                        code = command(android_test_command(record['serial'], payload,
                            ['-m', 'mobile.smoke', '--target', 'android', '--result-file', app_receipt]),
                            cpython, 1800, stdout=stream, stderr=subprocess.STDOUT, check=False)
                finally:
                    # Keep the owned emulator alive until the app-private report
                    # has been retrieved, including when logcat never attached.
                    try:
                        emulator.verify(record)
                        receipt = reports / 'android-receipt.json'
                        with receipt.open('w') as stream:
                            receipt_code = command([str(emulator.adb), '-s', record['serial'], 'shell',
                                'run-as', PACKAGE, 'cat', adb_receipt], cpython, 30,
                                stdout=stream, stderr=subprocess.STDOUT, check=False)
                    finally:
                        diagnostics(emulator, record, reports)
                if receipt_code:
                    raise RuntimeError('Actual Android runtime receipt could not be retrieved: ' + str(receipt_code))
                if code:
                    raise RuntimeError('Pinned Android runtime driver failed: ' + str(code))
                return verify_receipt(receipt, payload / 'source.json', reports / 'android-result.json')
        finally:
            # SDK session owns AVD/PID retirement; scratch owns remaining files.
            # Preserve startup/cleanup diagnostics even if session entry failed.
            if emulator.marker.exists():
                # A failed cleanup must preserve the owner record and workspace,
                # rather than letting scratch remove files under a live AVD.
                (workspace / '.keep').touch()
                (reports / 'android-cleanup-incomplete.txt').write_text(
                    'Owned emulator cleanup incomplete; retained workspace: ' + str(workspace) + '\n')
            if record is not None:
                for name in ('lease.json', 'removed-lease.json', 'emulator.log'):
                    path = emulator.workspace / name
                    if path.is_file():
                        shutil.copyfile(path, reports / ('android-' + name))
            elif emulator.workspace.is_dir():
                for path in emulator.workspace.glob('*.log'):
                    shutil.copyfile(path, reports / ('android-' + path.name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--cpython', type=Path, required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupt)
    run(args.root, args.cpython, args.payload, args.reports)


if __name__ == '__main__':
    main()
