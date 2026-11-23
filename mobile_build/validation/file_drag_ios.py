"""Verify a held iOS drag opens a folder and preserves moved bytes in List and Tiles."""

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import argparse
from functools import partial
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time
from uuid import uuid4

from build_manager.apple_simulators import AppleSimulators
from build_manager.native_commands import interrupt
from logistics_build.build_retention import scratch
from logistics_build.native_tooling import wheel_status
from logistics_build.test_environments import load, runtime_id
from mobile_build.deployment import manager_settings
from mobile_build.tools import stage
from . import document_storage_tools as devices
from . import incoming_ios_tools as fixture


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = 'io.github.ispaure.logisticsnotebookqa'


def exercise(app, output, env, *, project, bundle, runtime_id, result_name, **_options):
    client = AppleSimulators(env)
    runtime, model = devices.simulator_selection(client.devices()['devices'], 'iPhone', runtime_id)
    name = 'Build Manager File Drag QA ' + uuid4().hex
    udid = client.create(name, model, runtime)
    installed = False
    try:
        (output / 'ios-lease.json').write_text(json.dumps(
            dict(device=udid, name=name, runtime=runtime, model=model)))
        client.boot(udid, name=name)
        if not client.matching(udid, name):
            raise RuntimeError('File drag simulator lease identity changed.')
        client.invoke('install', udid, str(app), timeout=180)
        installed = True
        command = fixture._xcodebuild(project, f'platform=iOS Simulator,id={udid}')
        code = fixture._logged([*command, '-collect-test-diagnostics', 'never',
            '-resultBundlePath', str(output / 'file-drag.xcresult'),
            '-only-testing:IntakeTests/FileDragUITests/testLongPressMovesFolderInListAndFileInTiles',
            'test-without-building'], env, output / 'xctest.log', timeout=360)
        cache = Path(client.invoke('get_app_container', udid, bundle, 'data')) / 'Library/Caches'
        result = cache / result_name
        deadline = time.monotonic() + (8 if code == 0 else 0)
        while not result.exists() and time.monotonic() < deadline:
            time.sleep(.1)
        if result.is_file():
            shutil.copyfile(result, output / result_name)
        if code or not result.is_file():
            raise RuntimeError(f'File drag XCTest or byte verification failed (XCTest exit {code}).')
        if json.loads(result.read_text()) != dict(
                list_spring_opened=True, tiles_spring_opened=True, destination_bytes_match=True):
            raise RuntimeError('File drag fixture did not verify both layouts and moved bytes.')
    finally:
        devices.cleanup_ios_probe(client, udid, name, bundle, output, installed=installed)


def run(output, source_app=None):
    output.mkdir(parents=True)
    mobile = ROOT / 'mobile_build'
    options, _ = manager_settings.settings(mobile)
    wheels = wheel_status(ROOT)
    if source_app is None and not wheels['ready']:
        raise RuntimeError(wheels['message'])
    with scratch(ROOT) as work:
        env = dict(os.environ, LOGISTICS_DEPLOY_WORKSPACE=str(work),
            PATH=os.pathsep.join((str(Path(sys.executable).parent),
                str(ROOT / 'mobile_build/.tools/go/bin'), os.environ['PATH'])),
            GOCACHE=str(work / 'go-cache'), DEVELOPER_DIR=options['tools.xcode'],
            GOTOOLCHAIN='local', GOTELEMETRY='off')
        if wheels['ready']:
            env['PIP_FIND_LINKS'] = wheels['directory']
        os.environ.update(env)
        payload = work / 'payload'
        (output / 'source.json').write_text(json.dumps(stage(ROOT, payload, allow_dirty=True), indent=2))
        project = fixture._project_files(work)
        shutil.copyfile(fixture.SOURCES / 'FileDragUITests.swift', work / 'IncomingFilesUITests.swift')
        command = fixture._xcodebuild(project, 'generic/platform=iOS Simulator')
        if fixture._logged([*command, 'build-for-testing'], env, output / 'xctest-build.log', timeout=300):
            raise RuntimeError('Could not build the disposable file drag XCTest.')
        shutil.copyfile(ROOT / 'mobile_build/pyproject.toml', work / 'pyproject.toml')
        devices.run_ios(work, payload, output, env, bundle=BUNDLE,
            entry_point='tests.logisticsmobile.file_drag_gesture_probe', result_name='file-drag-result.json',
            runtime_id=runtime_id(load(ROOT), 'iphone'), source_app=source_app,
            exercise=partial(exercise, project=project))


def main():
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupt)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--ios-app', type=Path, help='Reuse a managed simulator app with matching native sources.')
    args = parser.parse_args()
    run(args.output.resolve(), args.ios_app.resolve() if args.ios_app else None)


if __name__ == '__main__':
    main()
