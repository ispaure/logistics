"""Focused notebook acceptance through existing managed mobile build/device runners."""
import argparse
import base64
import json
import importlib.util
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

from logistics_build.build_retention import scratch
from logistics_build.build_snapshots import materialize
from mobile_build.deployment import manager_settings
from mobile_build.tools import stage


def compiled_payload(apk):
    """Identify DEX and native libraries which Python-only restaging must preserve."""
    with ZipFile(apk) as archive:
        return {name: sha256(archive.read(name)).hexdigest() for name in archive.namelist()
                if name.endswith('.dex') or name.startswith('lib/')}


def retain_palm_package(work, output, *, name='palm'):
    """Keep the new QA package and provenance before disposable build cleanup."""
    manifest = output / 'android-apk.json'
    if not manifest.exists():
        return  # Compilation never reached a runnable package.
    built = json.loads(manifest.read_text())
    original = Path(built['apk'])
    if sha256(original.read_bytes()).hexdigest() != built['sha256']:
        raise ValueError('Built palm QA package changed before evidence capture')
    target = output / f'notebook-{name}.apk'
    shutil.copyfile(original, target)
    target.chmod(0o444)
    names = {'NotebookInput', 'BooxBallpoint', 'BooxInk', 'BooxRefresh', 'ImageCanvasView'}
    classes = {str(path.relative_to(work)): sha256(path.read_bytes()).hexdigest()
               for path in (work / 'build').rglob('*.class') if path.stem.split('$')[0] in names}
    native = work / 'payload/features/notebooks/mobile/android'
    sources = {str(path.relative_to(native)): sha256(path.read_bytes()).hexdigest()
               for path in native.rglob('*.java')}
    shared = work / 'payload/commonUtils/ui/native/android'
    sources.update({'commonUtils/' + str(path.relative_to(shared)): sha256(path.read_bytes()).hexdigest()
                    for path in shared.rglob('*.java')})
    (output / 'android-shell.json').write_text(json.dumps(dict(
        apk=str(target), sha256=built['sha256'], source=json.loads((output / 'source.json').read_text()),
        native_class_hashes=classes, native_source_hashes=sources,
        compiled_payload=compiled_payload(target), read_only=True), indent=2))


def android_shell(receipt_path, source, work, output, env, *, probe='notebook_template_probe'):
    """Restage only Python into an immutable, source-verified isolated QA APK."""
    from mobile_build.deployment.android_deploy import build_tools
    receipt = json.loads(receipt_path.read_text())
    apk = Path(receipt['apk'])
    if sha256(apk.read_bytes()).hexdigest() != receipt['sha256']:
        raise ValueError('Android shell hash differs from its receipt')
    compiled = receipt['source']
    current = json.loads((output / 'source.json').read_text())
    if compiled['dirty'] or compiled['commonUtils_dirty'] or compiled['commonUtils_commit'] != current['commonUtils_commit']:
        raise ValueError('Android shell requires clean matching commonUtils source')
    changed = subprocess.check_output(['git', '-C', str(source), 'diff', '--name-only',
        compiled['logistics_commit'], current['logistics_commit'], '--', 'Python'], text=True).splitlines()
    if any('/android/' in name and Path(name).suffix in {'.java', '.kt', '.c', '.h'} for name in changed):
        raise ValueError('Android compiled source changed since the shell build')
    spec = importlib.util.spec_from_file_location('notebook_apk_restage', source / 'mobile_build/validation/video_probe_tools.py')
    repack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repack)
    # The existing repacker stages from its explicit source root and preserves
    # compiled classes/libraries. Never mutate the source APK or its workspace.
    repack.ROOT = source
    unsigned = repack.prepare(apk, work / 'repack', probe=probe)
    tools = build_tools(env)
    key, aligned, signed = work / 'debug.jks', work / 'aligned.apk', work / 'notebook.apk'
    subprocess.run(['keytool', '-genkeypair', '-keystore', str(key), '-storepass', 'android',
        '-keypass', 'android', '-alias', 'androiddebugkey', '-dname', 'CN=Disposable Notebook QA',
        '-keyalg', 'RSA', '-validity', '2'], env=env, check=True, capture_output=True)
    subprocess.run([str(tools / 'zipalign'), '-f', '-P', '16', '4', str(unsigned), str(aligned)], env=env, check=True, capture_output=True)
    subprocess.run([str(tools / 'apksigner'), 'sign', '--ks', str(key), '--ks-pass', 'pass:android',
        '--out', str(signed), str(aligned)], env=env, check=True, capture_output=True)
    before, after = compiled_payload(apk), compiled_payload(signed)
    if not before or before != after:
        raise ValueError('Python restaging changed the compiled Android payload')
    (output / 'compiled-payload.json').write_text(json.dumps(dict(
        unchanged=True, entries=before, original_sha256=receipt['sha256'],
        restaged_sha256=sha256(signed.read_bytes()).hexdigest(), probe=probe), indent=2))
    (output / 'compiled-shell.json').write_text(json.dumps(receipt, indent=2))
    return signed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('android', 'ios'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', default='HEAD', help='Committed Logistics revision; excludes concurrent working edits')
    parser.add_argument('--ios-shell-receipt', type=Path, help='Verified simulator shell receipt; iOS never compiles implicitly')
    parser.add_argument('--android-shell-receipt', type=Path, help='Copy/repackage a verified QA APK instead of compiling')
    parser.add_argument('--probe', choices=('templates', 'calibration', 'palm', 'links'), default='templates')
    parser.add_argument('--ios-family', choices=('iPhone', 'iPad', 'iPhone Duo'), default='iPhone')
    parser.add_argument('--duoctl', type=Path, help='Reviewed simulator-only touch helper for iOS link acceptance')
    args = parser.parse_args()
    if args.platform == 'ios' and args.ios_shell_receipt is None:
        parser.error('iOS requires --ios-shell-receipt (copy-only simulator shell)')
    if args.probe == 'calibration' and (args.platform != 'android' or args.android_shell_receipt is None):
        parser.error('Calibration requires Android and an explicit source-verified QA shell receipt')
    if args.probe == 'palm' and args.platform == 'ios' and args.ios_family != 'iPad':
        parser.error('Pencil hover observer acceptance requires --ios-family iPad')
    if args.probe == 'links' and args.platform == 'ios' and (args.ios_family != 'iPhone Duo' or args.duoctl is None):
        parser.error('iOS link acceptance requires --ios-family \'iPhone Duo\' and --duoctl for genuine simulator touches')
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
        if args.probe == 'calibration':
            profile.update(entry_point='tests.logisticsmobile.notebook_calibration_probe',
                           result_name='notebook-calibration-result.json')
        elif args.probe == 'palm':
            profile.update(entry_point='tests.logisticsmobile.notebook_palm_probe',
                           result_name='notebook-palm-result.json')
        if args.probe == 'links':
            profile.update(entry_point='tests.logisticsmobile.notebook_link_probe',
                           result_name='notebook-link-result.json')
        try:
            if args.platform == 'ios':
                receipt = json.loads(args.ios_shell_receipt.read_text())
                if args.probe == 'links':
                    from mobile_build.validation.drawer_privacy_tools import verify_shell
                    verified = verify_shell(receipt, captured['logistics_commit'])
                    verified['scope'] = 'PDF/notebook link simulator acceptance; no physical device input'
                    (output / 'verified-ios-shell.json').write_text(json.dumps(verified, indent=2))
                source_app = Path(receipt['app'])
                if not source_app.is_dir():
                    raise ValueError('Verified simulator shell no longer exists')
                (output / 'compiled-shell.json').write_text(json.dumps(receipt, indent=2))
                driver.run_ios(work, payload, output, env, family=args.ios_family, source_app=source_app, duoctl=args.duoctl, **profile)
            else:
                if args.android_shell_receipt is not None:
                    (work / 'repack').mkdir()
                    apk = android_shell(args.android_shell_receipt, source, work, output, env,
                                        probe=profile['entry_point'].rsplit('.', 1)[1])
                    driver.exercise_android_app(apk, work, output, env, options,
                        startup_timeout=240, install_timeout=90, probe_timeout=180, **profile)
                else:
                    driver.run_android(work, payload, output, env, options, **profile)
        finally:
            if args.platform == 'android' and args.probe in ('palm', 'links') and args.android_shell_receipt is None:
                retain_palm_package(work, output, name=args.probe)
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
