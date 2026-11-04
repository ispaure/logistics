"""Verify a copyable iOS shell and optionally run the two-drawer privacy probe."""
import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess

from logistics_build.build_retention import scratch
from logistics_build.build_snapshots import materialize
from logistics_build.ios_backend import bundle_digest
from mobile_build.deployment import manager_settings
from mobile_build.tools import stage

ROOT = Path(__file__).resolve().parents[2]
FIX = '97f26369ee0fb8624b2445169780d0ab06660aaa'


def git(*arguments, root=ROOT):
    return subprocess.check_output(['git', '-C', str(root), *arguments])


def verify_shell(receipt, revision):
    shared = git('ls-tree', revision, 'Python/commonUtils').decode().split()[2]
    paths = git('ls-tree', '-r', '--name-only', revision).decode().splitlines()
    inputs = {}
    for native in Path(receipt['support']).iterdir():
        if native.suffix not in ('.m', '.swift'):
            continue
        if native.name == 'ScrollingTitle.m':
            source = 'ui/native/ios/ScrollingTitle.m'
            data = git('show', shared + ':' + source, root=ROOT / 'Python/commonUtils')
        else:
            matches = [p for p in paths if p.endswith('/' + native.name)]
            if len(matches) != 1:
                raise ValueError('Native shell input is not uniquely declared: ' + native.name)
            source = matches[0]
            data = git('show', revision + ':' + source)
        if native.read_bytes() != data:
            raise ValueError('Compiled native source differs: ' + native.name)
        inputs[native.name] = dict(source=source, sha256=sha256(data).hexdigest())
    if git('diff', '--name-only', receipt['source'], revision, '--', 'mobile_build/rclone_bridge').strip():
        raise ValueError('Compiled credential bridge inputs changed')
    app = Path(receipt['app'])
    if bundle_digest(app) != receipt['bundle_sha256']:
        raise ValueError('Copyable shell bundle no longer matches its receipt')
    label = app / 'app_packages/toga_iOS/widgets/label.py'
    if sha256(label.read_bytes()).hexdigest() != receipt['label_sha256']:
        raise ValueError('Native toolkit label differs from receipt')
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', FIX, revision], check=True)
    return dict(source_commit=revision, commonUtils_commit=shared, fix_commit=FIX,
                native_inputs=inputs, native_bundle_sha256=receipt['bundle_sha256'],
                shell_receipt=receipt, scope='UIKit floating-panel privacy functional acceptance only')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shell-receipt', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source-revision', default='HEAD')
    parser.add_argument('--runtime', help='Optional explicit installed iOS simulator runtime identifier')
    parser.add_argument('--run', action='store_true', help='Explicitly consume one granted five-minute simulator slot')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    revision = git('rev-parse', args.source_revision + '^{commit}').decode().strip()
    receipt = json.loads(args.shell_receipt.read_text())
    proof = verify_shell(receipt, revision)
    proof.update(native_started=False, native_acceptance='unverified')
    (output / 'plan.json').write_text(json.dumps(proof, indent=2) + '\n')
    if not args.run:
        print('Shell verified; no simulator created, copied app signed or native job started.')
        return
    options, _ = manager_settings.settings(ROOT / 'mobile_build')
    env = dict(os.environ, DEVELOPER_DIR=options['tools.xcode'])
    with scratch(ROOT) as workspace:
        os.environ['LOGISTICS_DEPLOY_WORKSPACE'] = env['LOGISTICS_DEPLOY_WORKSPACE'] = str(workspace)
        os.environ['COMMONUTILS_STORAGE_ROOT'] = env['COMMONUTILS_STORAGE_ROOT'] = str(workspace / 'storage')
        frozen = workspace / 'source'
        captured = materialize(ROOT, frozen, revision=revision)
        payload = workspace / 'payload'
        staged = stage(frozen, payload)
        (output / 'source.json').write_text(json.dumps(dict(source=captured, payload=staged), indent=2))
        spec = importlib.util.spec_from_file_location('drawer_privacy_frozen_driver',
            frozen / 'mobile_build/validation/document_storage_tools.py')
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        def timed_out(number, frame):
            signal.alarm(0)
            raise TimeoutError('Granted five-minute drawer privacy slot expired')
        previous = signal.signal(signal.SIGALRM, timed_out)
        signal.alarm(300)
        try:
            driver.run_ios(workspace, payload, output, env,
                bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.drawer_privacy_probe',
                result_name='drawer-privacy-result.json', family='iPhone',
                source_app=Path(receipt['app']), runtime_id=args.runtime)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        proof.update(native_started=True, native_acceptance='passed')
        (output / 'plan.json').write_text(json.dumps(proof, indent=2) + '\n')


if __name__ == '__main__':
    main()
