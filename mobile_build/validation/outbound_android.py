"""Run the outgoing-share journey with a generated endpoint on one owned Android emulator."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import unquote

from logistics_build.build_retention import scratch
from mobile_build.deployment import manager_settings
from mobile_build.tools import stage
from . import document_storage_tools as devices
from .incoming_android import (Device, build_fixture, control, matches, one_node,
                               require, wait_for, wait_ui, write_json)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = 'io.github.ispaure.logisticsoutgoingreceiver'
RECEIVER_LABEL = 'Logistics QA Receiver'
PROBE = 'tests.logisticsmobile.outbound_share_probe'
STAGE = 'cache/outbound-share-stage'


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    options, _ = manager_settings.settings(ROOT / 'mobile_build')
    sdk, java = options['tools.android_sdk'], options['tools.java']
    with scratch(ROOT) as work:
        environment = dict(os.environ, ANDROID_HOME=sdk, ANDROID_SDK_ROOT=sdk, JAVA_HOME=java,
                           GOCACHE=str(work / 'go-cache'), LOGISTICS_DEPLOY_WORKSPACE=str(work))
        environment['PATH'] = os.pathsep.join((str(Path(sys.executable).parent),
            str(ROOT / 'mobile_build/.tools/go/bin'), environment['PATH']))
        os.environ.update(environment)
        receiver = build_fixture(work, sdk, java, output, source=ROOT / 'mobile_build/native_tests/android/outbound',
                                 package=PACKAGE, activity='OutgoingReceiver', artifact='receiver')
        shutil.copyfile(ROOT / 'mobile_build/pyproject.toml', work / 'pyproject.toml')
        payload = work / 'payload'
        write_json(output / 'source.json', stage(ROOT, payload, allow_dirty=True))
        completed = set()

        def observe(phase, emulator, record, evidence):
            if phase not in {'ready', 'poll', 'result'}:
                return
            device = Device(emulator.adb, record['serial'], record['name'], evidence)
            if phase == 'ready':
                device.call('install', str(receiver), timeout=180)
                return
            if phase == 'result':
                device.call('uninstall', PACKAGE)
                packages = device.shell('pm', 'list', 'packages', PACKAGE).stdout.decode()
                require('package:' + PACKAGE not in packages, 'The generated receiver remains installed')
                write_json(output / 'receiver-cleanup.json', dict(uninstalled=True, package=PACKAGE))
                return

            status = device.call('exec-out', 'run-as', devices.BUNDLE, 'cat', STAGE, check=False).stdout.decode()
            if status not in {'cancel', 'deliver'} or status in completed:
                return
            if status == 'cancel':
                wait_ui(device, 'cancel-chooser', lambda tree: one_node(tree, lambda n: matches(n, RECEIVER_LABEL)))
                device.screenshot('cancel-chooser')
                device.key('KEYCODE_BACK')
            else:
                control(device, 'deliver-chooser', lambda n: matches(n, RECEIVER_LABEL))
                wait_for('receiving app', lambda: device.shell('run-as', PACKAGE, 'test', '-f',
                                                              'files/receive', check=False).returncode == 0)
                uri = device.read(PACKAGE, 'files/receive').decode()
                uri_prefix = 'content://' + devices.BUNDLE + '.outgoing-files/outgoing/'
                require(uri.startswith(uri_prefix), f'Unexpected receiving URI: {uri}')
                contents = device.read(PACKAGE, 'files/receive.bin')
                digest = sha256(contents).hexdigest()
                directory, storage, filename = uri.removeprefix(uri_prefix).split('/')
                require(re.fullmatch(r'share-[a-z0-9_]+', directory), 'Unexpected staging directory')
                filename = unquote(filename)
                require(storage == 'payload' and filename == 'Selected payload.logisticsfixture',
                        f'Unexpected outbound filename: {filename}')
                share = f'cache/OutgoingShares/{directory}'
                cached = f'{share}/payload/{filename}'
                device.shell('run-as', devices.BUNDLE, 'test', '-f', cached)
                wait_for('native chooser selection callback', lambda: device.shell('run-as', devices.BUNDLE,
                    'test', '-f', share + '/.target-chosen', check=False).returncode == 0)
                device.shell('run-as', devices.BUNDLE, 'touch', '-c', '-t', '202001010000', cached)
                device.shell('run-as', devices.BUNDLE, 'touch', '-c', '-t', '202001010000', share)
                control(device, 'read-after-expiry', lambda n: matches(n, 'Read again'))
                wait_for('expired file result', lambda: device.shell('run-as', PACKAGE, 'test', '-f',
                                                                     'files/reopen', check=False).returncode == 0)
                expiry = device.read(PACKAGE, 'files/reopen').decode()
                require(expiry == 'java.io.FileNotFoundException', f'Expired grant returned {expiry}')
                write_json(output / 'recipient.json', dict(uri=uri, sha256=digest, bytes=len(contents), expiration=expiry))
                device.shell('run-as', devices.BUNDLE, 'touch', 'cache/outbound-receiver-verified')
            completed.add(status)

        result = devices.run_android(work, payload, output, environment, options,
            entry_point=PROBE, result_name='outbound-share-result.json', observe=observe, probe_timeout=120)
        recipient = json.loads((output / 'recipient.json').read_text())
        require((result['bytes'], result['sha256']) == (recipient['bytes'], recipient['sha256']),
                'Generated receiver did not receive the exact selected file bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    run(options.output.resolve())


if __name__ == '__main__':
    main()
