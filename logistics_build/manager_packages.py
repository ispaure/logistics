"""Project-owned Release archive stages shared by tester and device delivery."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from build_manager.profiles import save_json
from commonUtils.runtime.streams import file_sha256


def archive(state, arguments):
    from mobile_build.deployment import testflight_deploy as deploy
    from mobile_build.deployment import testflight_tools as tools
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-number')
    parser.add_argument('--profile')
    parser.add_argument('--inbox-profile')
    parser.add_argument('--widget-profile')
    parser.add_argument('--widget-actions-profile')
    parser.add_argument('--watch-profile')
    parser.add_argument('--watch-widget-profile')
    args = parser.parse_args(arguments)
    number = deploy.reserve_build(args.build_number)
    command = [sys.executable, '-m', 'mobile_build.deployment.testflight_tools']
    extra = []
    for key in ('profile', 'inbox_profile', 'widget_profile', 'widget_actions_profile', 'watch_profile', 'watch_widget_profile'):
        if getattr(args, key):extra += ['--' + key.replace('_', '-'), getattr(args, key)]
    for stage in ('plan', 'archive'):
        subprocess.run([*command, stage, '--build-number', number, *(extra if stage == 'archive' else [])],
                       cwd=deploy.ROOT.parent, check=True)
    workspace = deploy.ROOT / 'build/testflight' / number
    app = workspace / 'Logistics.xcarchive/Products/Applications/Logistics Mobile.app'
    save_json(state, dict(schema=1, workspace=str(workspace), build_number=number,
        release_sha256=file_sha256(workspace / 'release.json'), archive_sha256=tools.archive_fingerprint(app)))


def checked_archive(state):
    from mobile_build.deployment.testflight_tools import archive_fingerprint
    data = json.loads(Path(state).read_text()); workspace = Path(data['workspace'])
    app = workspace / 'Logistics.xcarchive/Products/Applications/Logistics Mobile.app'
    if (file_sha256(workspace / 'release.json') != data['release_sha256']
            or archive_fingerprint(app) != data['archive_sha256']):
        raise ValueError('Shared Release archive changed; prepare a fresh plan.')
    return data, json.loads((workspace / 'release.json').read_text())


def export_testflight(state):
    from mobile_build.deployment import testflight_tools as tools
    from mobile_build.deployment.manager_settings import record_prepared_artifact
    from mobile_build.deployment.testflight_external import settings
    data, record = checked_archive(state)
    workspace = Path(data['workspace'])
    subprocess.run([sys.executable, '-m', 'mobile_build.deployment.testflight_tools', 'export',
                    '--build-number', data['build_number']], cwd=tools.ROOT.parent, check=True)
    record_prepared_artifact(dict(provider='TestFlight', release=record,
        verified=json.loads((workspace / 'export-verified.json').read_text()),
        destination=settings(), workspace=str(workspace)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['archive', 'export-testflight'])
    parser.add_argument('--state', required=True, type=Path)
    args, rest = parser.parse_known_args()
    if args.action == 'archive':archive(args.state, rest)
    else:
        if rest:parser.error('Unexpected export arguments.')
        export_testflight(args.state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
