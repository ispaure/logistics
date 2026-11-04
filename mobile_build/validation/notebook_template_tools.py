"""Native template acceptance through existing managed mobile build/device runners."""
import argparse
import base64
import json
import importlib.util
import os
from pathlib import Path
import shutil

from logistics_build.build_retention import scratch
from logistics_build.build_snapshots import materialize
from mobile_build.deployment import manager_settings
from mobile_build.tools import stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('android', 'ios'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', default='HEAD', help='Committed Logistics revision; excludes concurrent working edits')
    parser.add_argument('--ios-shell-receipt', type=Path, help='Verified simulator shell receipt; iOS never compiles implicitly')
    args = parser.parse_args()
    if args.platform == 'ios' and args.ios_shell_receipt is None:
        parser.error('iOS requires --ios-shell-receipt (copy-only simulator shell)')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    options, _ = manager_settings.settings(root / 'mobile_build')
    env = dict(os.environ, DEVELOPER_DIR=options['tools.xcode'], ANDROID_HOME=options['tools.android_sdk'],
               ANDROID_SDK_ROOT=options['tools.android_sdk'], JAVA_HOME=options['tools.java'])
    env['PATH'] = str(root / 'mobile_build/.tools/go/bin') + os.pathsep + env['PATH']
    os.environ.update(env)
    with scratch(root) as work:
        env['LOGISTICS_DEPLOY_WORKSPACE'] = os.environ['LOGISTICS_DEPLOY_WORKSPACE'] = str(work)
        env['XDG_CACHE_HOME'] = str(work / 'probe-tools')
        shutil.copyfile(root / 'mobile_build/pyproject.toml', work / 'pyproject.toml')
        (output / 'workspace.json').write_text(json.dumps(dict(path=str(work), owned=True)))
        source = work / 'source'
        captured = materialize(root, source, revision=args.revision)
        (output / 'committed-source.json').write_text(json.dumps(captured, indent=2))
        spec = importlib.util.spec_from_file_location('notebook_native_driver', source / 'mobile_build/validation/document_storage_tools.py')
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        payload = work / 'payload'
        manifest = stage(source, payload)
        (output / 'source.json').write_text(json.dumps(manifest, indent=2))
        profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
            entry_point='tests.logisticsmobile.notebook_template_probe', result_name='notebook-template-result.json')
        try:
            if args.platform == 'ios':
                receipt = json.loads(args.ios_shell_receipt.read_text())
                source_app = Path(receipt['app'])
                if not source_app.is_dir():
                    raise ValueError('Verified simulator shell no longer exists')
                (output / 'compiled-shell.json').write_text(json.dumps(receipt, indent=2))
                driver.run_ios(work, payload, output, env, family='iPhone', source_app=source_app, **profile)
            else:
                driver.run_android(work, payload, output, env, options, **profile)
        finally:
            report_path = output / (args.platform + '-result.json')
            if report_path.exists():
                report = json.loads(report_path.read_text())
                artifacts = report.pop('artifacts', {})
                target = output / 'template-evidence'
                target.mkdir(exist_ok=True)
                for name, data in artifacts.items():
                    if Path(name).name != name or Path(name).suffix not in ('.png', '.rmdoc'):
                        raise ValueError('Unexpected template evidence name')
                    (target / name).write_bytes(base64.b64decode(data, validate=True))
                report['artifact_names'] = list(artifacts)
                report_path.write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
