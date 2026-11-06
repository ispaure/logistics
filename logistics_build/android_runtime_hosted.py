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
from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
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


def collect_receipt(emulator, record, name, destination):
    """Capture bounded app-private bytes before creating durable host evidence."""
    destination = Path(destination)
    destination.unlink(missing_ok=True)
    emulator.verify(record)
    try:
        data = run_bytes([str(emulator.adb), '-s', record['serial'], 'shell',
                          'run-as', PACKAGE, 'cat', name],
                         max_output=MAX_RECEIPT_BYTES, timeout=30)
    except (OSError, ValueError) as error:
        raise RuntimeError('Actual Android runtime receipt could not be retrieved.') from error
    destination.write_bytes(data)


def _retain_failure(primary, error, phase):
    """Keep the original failure while identifying secondary evidence/cleanup loss."""
    if primary is None:
        return error
    if primary is not error:
        primary.add_note(phase + ': ' + type(error).__name__ + ': ' + str(error))
    return primary


def run(root, cpython, payload, reports, *, install_image=True):
    root, cpython, payload, reports = (Path(value).resolve() for value in (root, cpython, payload, reports))
    reports.mkdir(parents=True, exist_ok=True)
    # A reused reports directory must never attribute an earlier receipt or
    # device record to a run that fails before launching the testbed.
    for name in ('android-result.json', 'android-result.receipt.log', 'android-receipt.json',
                 'android-testbed.log', 'android-runtime-device.json', 'android-logcat.log',
                 'android-logcat-error.txt', 'android-lease.json', 'android-removed-lease.json',
                 'android-emulator.log'):
        (reports / name).unlink(missing_ok=True)
    values = load(root)
    image = android_image(values, hosted=True)
    sdk = Path(os.environ['ANDROID_HOME'])
    if install_image:
        with (reports / 'android-image-install.log').open('w') as log:
            command([str(sdk / 'cmdline-tools/latest/bin/sdkmanager'), 'emulator', image],
                    root, 600, stdout=log, stderr=subprocess.STDOUT)
    token = uuid4().hex
    app_receipt, adb_receipt = receipt_paths(token)
    failure = None
    result = None
    try:
        with scratch(root) as workspace:
            # Hosted Linux requires the SDK's explicit qualified Actions boundary;
            # default local admission intentionally does not accept that host.
            # Establish retention before anything can start an AVD. A failed
            # late pin write must not expose a live device tree to scratch cleanup.
            pin = workspace / '.keep'
            pin.touch()
            emulator = None
            record = None
            try:
                emulator = AndroidEmulator(sdk, workspace / 'emulator', startup_timeout=240,
                                           gpu='swiftshader', execution_context='github-actions')
                with emulator.session(image, values['android_model']) as record:
                    try:
                        emulator.verify(record)
                        (reports / 'android-runtime-device.json').write_text(json.dumps(record, indent=2) + '\n')
                        log = reports / 'android-testbed.log'
                        try:
                            with log.open('w') as stream:
                                code = command(android_test_command(record['serial'], payload,
                                    ['-m', 'mobile.smoke', '--target', 'android', '--result-file', app_receipt]),
                                    cpython, 1800, stdout=stream, stderr=subprocess.STDOUT, check=False)
                            if code:
                                raise RuntimeError('Pinned Android runtime driver failed: ' + str(code))
                        except BaseException as error:
                            failure = error
                        # Keep the owned AVD alive for receipt and diagnostics,
                        # including when the driver raises or logcat never attached.
                        receipt = reports / 'android-receipt.json'
                        try:
                            collect_receipt(emulator, record, adb_receipt, receipt)
                        except BaseException as error:
                            failure = _retain_failure(failure, error, 'Receipt collection failed')
                        candidate = workspace / 'android-result.json'
                        if failure is None:
                            try:
                                result = verify_receipt(receipt, payload / 'source.json', candidate)
                            except BaseException as error:
                                failure = error
                        try:
                            diagnostics(emulator, record, reports)
                        except BaseException as error:
                            failure = _retain_failure(failure, error, 'Runtime diagnostics failed')
                        if failure is not None:
                            raise failure
                        # Verification precedes diagnostic errors, but accepted
                        # evidence is published only after live collection succeeds.
                        shutil.copyfile(candidate.with_suffix('.receipt.log'), reports / 'android-result.receipt.log')
                        shutil.copyfile(candidate, reports / 'android-result.json')
                    except BaseException as error:
                        # Capture session-body failures before exit can raise a
                        # separate owned-device cleanup failure. Session entry
                        # itself remains owned by the manager context.
                        failure = _retain_failure(failure, error, 'Runtime verification failed')
                        raise failure
            except BaseException as error:
                failure = _retain_failure(failure, error, 'Owned emulator cleanup failed')
                raise failure
            finally:
                # SDK session owns AVD/PID retirement; scratch owns remaining files.
                # Remove the pre-start pin only after the lease has retired;
                # subsequent diagnostic-copy errors cannot endanger a live AVD.
                try:
                    if emulator is not None and emulator.marker.exists():
                        # Preserve earlier retained-workspace pointers on retries.
                        with (reports / 'android-cleanup-incomplete.txt').open('a') as incomplete:
                            incomplete.write('Owned emulator cleanup incomplete; retained workspace: '
                                             + str(workspace) + '\n')
                    else:
                        pin.unlink()
                    if record is not None:
                        for name in ('lease.json', 'removed-lease.json', 'emulator.log'):
                            path = emulator.workspace / name
                            if path.is_file():
                                shutil.copyfile(path, reports / ('android-' + name))
                    elif emulator is not None and emulator.workspace.is_dir():
                        for path in emulator.workspace.glob('*.log'):
                            shutil.copyfile(path, reports / ('android-' + path.name))
                except BaseException as error:
                    failure = _retain_failure(failure, error, 'Final emulator diagnostics failed')
                    raise failure
    except BaseException as error:
        # Scratch retirement is also secondary to a recorded test/device failure.
        failure = _retain_failure(failure, error, 'Scratch cleanup failed')
        raise failure
    return result


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
