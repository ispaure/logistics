"""Restage a focused Python video probe into a built APK; use an owned emulator."""
import argparse
from hashlib import sha1, sha256
from io import BytesIO
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import time
from zipfile import ZipFile, ZIP_DEFLATED

from build_manager.android_emulators import AndroidEmulator
from logistics_build.build_retention import scratch
from mobile_build.deployment.android_deploy import deployment_environment, tools_environment, build_tools
from tests.readers.video_fixtures import codec_matrix
from mobile_build.tools import stage

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = 'io.github.ispaure.logisticsmobile'


def cloud_fixtures(workspace, *, rclone=None):
    from features.rclone import executable
    tool = Path(rclone or executable.get_rclone_path()).resolve()
    if not tool.is_file():
        raise FileNotFoundError('Cloud fixtures require the pinned rclone tool; supply --rclone when running a source snapshot.')
    root = workspace / 'video-cloud-fixtures'
    fixtures = codec_matrix(root / 'remote/plain')
    for _, _, _, path in fixtures:
        extended = workspace / ('extended-' + path.name)
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-stream_loop', '2',
            '-i', str(path), '-t', '6', '-c', 'copy', str(extended)],
            check=True, capture_output=True, timeout=45)
        shutil.move(extended, path)
    (root / 'remote/encrypted').mkdir()
    (root / 'remote/plain/h264-aac.srt').write_text('1\n00:00:00,000 --> 00:00:01,900\nCloud fixture caption\n')
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-stream_loop', '5',
        '-i', str(root / 'remote/plain/h264-aac.mp4'), '-t', '12', '-c', 'copy', str(root / 'remote/plain/long.mp4')],
        check=True, capture_output=True, timeout=45)
    config = workspace / 'synthetic-video.conf'
    config.write_text('[Secret]\ntype=crypt\nremote=' + str(root / 'remote/encrypted') + '\n'
        'password=E7Tt68UUDf297fEq6fQq6vjnnyj003Lrpf5FuniO2qlBJqGXXm5tIg\n')
    subprocess.run([str(tool), '--config', str(config), 'copy',
        str(root / 'remote/plain'), 'Secret:'], check=True, capture_output=True, timeout=90)
    (root / 'fixture-tool.json').write_text(json.dumps(dict(
        name='rclone', sha256=sha256(tool.read_bytes()).hexdigest(),
        scope='Synthetic fixture encryption only; not application playback'), indent=2))
    tls = root / 'tls'
    tls.mkdir()
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    from datetime import datetime, timedelta, timezone
    from ipaddress import ip_address
    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Disposable Video QA CA')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
        .sign(key, hashes.SHA256()))
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    certificate = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')]))
        .issuer_name(name).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=2))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address('127.0.0.1')), x509.DNSName('localhost')]), False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False).sign(key, hashes.SHA256()))
    (tls / 'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (tls / 'server.pem').write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    (tls / 'server.key').write_bytes(server_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    return root


def prepare(apk, workspace, *, cloud=False, rclone=None):
    fixtures = codec_matrix(workspace / 'fixtures', duration=12) if not cloud else []
    fixture_root = cloud_fixtures(workspace, rclone=rclone) if cloud else None
    with ZipFile(apk) as archive:
        if not any(b'Lio/github/ispaure/logistics/video/VideoPlayer$Listener;' in archive.read(name)
                   for name in archive.namelist() if name.startswith('classes') and name.endswith('.dex')):
            raise ValueError('The supplied APK has no native Video Player. Choose a managed video-enabled build.')
    stage(ROOT, workspace / 'payload', allow_dirty=True)
    staged = workspace / 'payload'
    module = 'video_cloud_probe' if cloud else 'video_probe' 
    payload = BytesIO()
    with ZipFile(apk) as original:
        with ZipFile(BytesIO(original.read('assets/chaquopy/app.imy'))) as app, ZipFile(payload, 'w', ZIP_DEFLATED) as result:
            replaced = ('mobile/', 'features/', 'services/', 'commonUtils/', 'logisticsmobile/')
            for entry in app.infolist():
                if not entry.filename.startswith(replaced) and not entry.filename.startswith('tests/logisticsmobile/'):
                    result.writestr(entry, app.read(entry.filename))
            for path in sorted(staged.rglob('*')):
                if path.is_file():
                    key = path.relative_to(staged).as_posix()
                    if key != 'logisticsmobile/__main__.py':
                        result.writestr(key, path.read_bytes())
            entrypoint = f'from tests.logisticsmobile.{module} import main\nmain().main_loop()\n'
            result.writestr('logisticsmobile/__main__.py', entrypoint)
            native_tests = ROOT / 'mobile_build/native_tests/tests/logisticsmobile'
            for path in native_tests.rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts and path.name != '__main__.py':
                    result.writestr('tests/logisticsmobile/' + path.relative_to(native_tests).as_posix(), path.read_bytes())
            result.writestr('tests/logisticsmobile/__main__.py', entrypoint)
            for _, _, _, path in fixtures:
                result.writestr('tests/logisticsmobile/video-fixtures/' + path.name, path.read_bytes())
            if fixture_root is not None:
                for path in fixture_root.rglob('*'):
                    if path.is_file():
                        result.writestr('tests/logisticsmobile/video-cloud-fixtures/' + path.relative_to(fixture_root).as_posix(), path.read_bytes())
        build = json.loads(original.read('assets/chaquopy/build.json'))
        build['assets']['app.imy'] = sha1(payload.getvalue()).hexdigest()
        unsigned = workspace / 'unsigned.apk'
        with ZipFile(unsigned, 'w') as output:
            for entry in original.infolist():
                if entry.filename.startswith('META-INF/') or entry.filename in {'assets/chaquopy/app.imy', 'assets/chaquopy/build.json'}:
                    continue
                output.writestr(entry, original.read(entry.filename))
            output.writestr('assets/chaquopy/app.imy', payload.getvalue())
            output.writestr('assets/chaquopy/build.json', json.dumps(build))
    return unsigned


def run(apk, output, *, cloud=False):
    output.mkdir(parents=True, exist_ok=False)
    environment, _ = tools_environment(deployment_environment())
    tools = build_tools(environment)
    with scratch() as workspace:
        unsigned = prepare(apk, workspace, cloud=cloud)
        shutil.copyfile(workspace / 'payload/source.json', output / 'source.json')
        key = workspace / 'debug.jks'
        subprocess.run(['keytool', '-genkeypair', '-keystore', str(key), '-storepass', 'android', '-keypass', 'android',
            '-alias', 'androiddebugkey', '-dname', 'CN=Disposable Video QA', '-keyalg', 'RSA', '-validity', '2'],
            env=environment, check=True, capture_output=True)
        aligned, signed = workspace / 'aligned.apk', workspace / 'video.apk'
        subprocess.run([str(tools / 'zipalign'), '-f', '-P', '16', '4', str(unsigned), str(aligned)], env=environment, check=True)
        subprocess.run([str(tools / 'apksigner'), 'sign', '--ks', str(key), '--ks-pass', 'pass:android',
            '--out', str(signed), str(aligned)], env=environment, check=True)
        emulator = AndroidEmulator(environment['ANDROID_HOME'], workspace / 'device', environment=environment)
        record = None
        try:
            record = emulator.start('system-images;android-36;google_apis;arm64-v8a', 'pixel_9')
            prefix = ('-s', record['serial'])
            emulator.invoke(*prefix, 'install', str(signed), timeout=180)
            if cloud:
                # Mount a disposable CA store inside this owned emulator. The SDK image
                # and other devices are untouched; deleting the AVD retires the trust.
                ca = workspace / 'video-cloud-fixtures/tls/ca.pem'
                name = subprocess.check_output(['openssl', 'x509', '-subject_hash_old', '-noout', '-in', str(ca)], text=True).strip() + '.0'
                emulator.invoke(*prefix, 'root')
                emulator.invoke(*prefix, 'wait-for-device')
                emulator.invoke(*prefix, 'shell', 'mkdir', '-p', '/data/local/tmp/video-ca-store')
                emulator.invoke(*prefix, 'shell', 'cp /system/etc/security/cacerts/* /data/local/tmp/video-ca-store/')
                emulator.invoke(*prefix, 'push', str(ca), '/data/local/tmp/video-ca-store/' + name)
                emulator.invoke(*prefix, 'shell', 'mount -t tmpfs -o mode=0755 tmpfs /system/etc/security/cacerts')
                emulator.invoke(*prefix, 'shell', 'cp /data/local/tmp/video-ca-store/* /system/etc/security/cacerts/')
                emulator.invoke(*prefix, 'shell', 'chcon -R u:object_r:system_file:s0 /system/etc/security/cacerts')
            emulator.invoke(*prefix, 'shell', 'am', 'start', '-W', '-n', BUNDLE + '/org.beeware.android.MainActivity')
            deadline = time.monotonic() + 360
            while time.monotonic() < deadline:
                try:
                    report = json.loads(emulator.invoke(*prefix, 'shell', 'run-as', BUNDLE, 'cat', 'cache/video-probe-result.json'))
                except (RuntimeError, ValueError):
                    time.sleep(.5)
                    continue
                report.update(apk_sha256=sha256(apk.read_bytes()).hexdigest(), restaged_python_probe=True,
                              native_binary_source='provided managed APK')
                (output / 'result.json').write_text(json.dumps(report, indent=2))
                if not report['success']:
                    raise RuntimeError(report.get('error', 'Native video probe failed'))
                print(json.dumps(dict(success=True, cases=len(report['cases']))))
                return
            raise TimeoutError('Focused native video probe did not finish within six minutes')
        finally:
            if record is not None:
                try:
                    (output / 'logcat.txt').write_text(emulator.invoke('-s', record['serial'], 'logcat', '-d', timeout=30))
                finally:
                    emulator.cleanup()
            else:
                emulator.cleanup()


def run_ios(source, output, *, cloud=False, model_name='iPad'):
    from uuid import uuid4
    from build_manager.apple_simulators import AppleSimulators
    from .duo_pose_tools import prepare as prepare_app
    output.mkdir(parents=True, exist_ok=False)
    client = AppleSimulators()
    runtime, model = next((runtime, row['deviceTypeIdentifier']) for runtime, rows in client.devices()['devices'].items()
                          for row in rows if row.get('isAvailable') and model_name in row['name'])
    name, bundle = 'Build Manager Video QA ' + uuid4().hex, 'io.github.ispaure.logisticsvideoqa'
    device = None
    cache = None
    with scratch() as workspace:
        app = prepare_app(source, workspace / 'build')
        shutil.copyfile(app / 'app/fold-source.json', output / 'source.json')
        module = 'video_cloud_probe' if cloud else 'video_probe'
        entrypoint = f'from tests.logisticsmobile.{module} import main\nmain().main_loop()\n'
        (app / 'app/logisticsmobile/__main__.py').write_text(entrypoint)
        tests = app / 'app/tests/logisticsmobile'
        (tests / '__main__.py').write_text(entrypoint)
        for bytecode in (tests / '__pycache__').glob('__main__*.pyc'):
            bytecode.unlink()
        if cloud:
            shutil.copytree(cloud_fixtures(workspace), tests / 'video-cloud-fixtures')
        else:
            codec_matrix(tests / 'video-fixtures', duration=12)
        # Video QA does not exercise app extensions. Remove only this scratch copy's
        # extensions, whose signed identities belong to the containing production app.
        for extension_directory in ('PlugIns', 'Extensions'):
            shutil.rmtree(app / extension_directory, ignore_errors=True)
        for info in [app / 'Info.plist']:
            value = plistlib.loads(info.read_bytes())
            value['CFBundleIdentifier'] = bundle if info == app / 'Info.plist' else value['CFBundleIdentifier'].replace('io.github.ispaure.logisticsmobile', bundle)
            info.write_bytes(plistlib.dumps(value))
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True, capture_output=True)
        try:
            device = client.create(name, model, runtime)
            client.boot(device)
            if cloud:
                client.invoke('keychain', device, 'add-root-cert', str(workspace / 'video-cloud-fixtures/tls/ca.pem'))
            client.invoke('install', device, str(app))
            client.invoke('launch', device, bundle)
            container = Path(client.invoke('get_app_container', device, bundle, 'data').strip())
            cache = container / 'Library/Caches'
            deadline = time.monotonic() + 360
            while time.monotonic() < deadline:
                paths = list(cache.rglob('video-probe-result.json'))
                if not paths:
                    time.sleep(.5)
                    continue
                report = json.loads(paths[0].read_text())
                frames = output / 'frames'
                frames.mkdir(exist_ok=True)
                for frame in cache.rglob('video-cloud-frames/*.png'):
                    shutil.copyfile(frame, frames / frame.name)
                if cloud and report['success']:
                    from PIL import Image
                    counts = {}
                    for frame in frames.glob('*.png'):
                        with Image.open(frame) as pixels:
                            counts[frame.name] = len(set(pixels.convert('RGB').getdata()))
                    if not counts or min(counts.values()) <= 5:
                        report.update(success=False, error='Native cloud frames did not contain a decoded test pattern.')
                    report['decoded_frame_colors'] = counts
                report.update(restaged_python_probe=True, native_binary_source=str(source))
                (output / 'result.json').write_text(json.dumps(report, indent=2))
                if not report['success']:
                    raise RuntimeError(report.get('error', 'Native iPad video probe failed'))
                print(json.dumps(dict(success=True, cases=len(report['cases']))))
                return
            raise TimeoutError('Focused iPad video probe did not finish within six minutes')
        finally:
            if cache is not None:
                for path in cache.rglob('video-probe-result.json'):
                    shutil.copyfile(path, output / 'device-result.json')
            if device is not None:
                client.remove(device, name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path)
    parser.add_argument('--ios-app', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cloud', action='store_true', help='Exercise real native WebDAV and crypt network ranges.')
    parser.add_argument('--ios-model', choices=('iPad', 'iPhone'), default='iPad')
    arguments = parser.parse_args()
    if bool(arguments.apk) == bool(arguments.ios_app):
        parser.error('Choose exactly one managed Android APK or iOS app.')
    if arguments.apk:
        run(arguments.apk.resolve(), arguments.output.resolve(), cloud=arguments.cloud)
    else:
        run_ios(arguments.ios_app.resolve(), arguments.output.resolve(), cloud=arguments.cloud, model_name=arguments.ios_model)
