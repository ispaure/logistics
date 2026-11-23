"""Host side of the disposable Android ranged-download acceptance."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from contextlib import ExitStack, contextmanager
from hashlib import file_digest, shake_256
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import sys
from threading import Event, Thread
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.etree import ElementTree

from .download_recovery_probe import Server, MIB, ROOT

BUNDLE = 'io.github.ispaure.logisticsnotebookqa'
SIZE = 20 * MIB + 137
STOP = 16 * MIB


def digest(path, algorithm='sha256'):
    with path.open('rb') as stream:
        return file_digest(stream, algorithm).hexdigest()


def stored_offset(logical, crypt):
    return 32 + logical + 16 * ((logical + 65535) // 65536) if crypt else logical


def check_ranges(ranges, start, end, crypt):
    cursor = stored_offset(start, crypt)
    for offset, length in ranges:
        if crypt and (offset, length) == (0, 32):
            continue  # The crypt provider revalidates the nonce on each open.
        assert offset == cursor and length > 0, ranges
        cursor += length
    assert cursor == stored_offset(end, crypt), ranges


class Ranges(Server):
    def send_body(self, start, stop, source, tag):
        checkpoint = getattr(self.server, 'stop', None)
        if not self.server.armed or checkpoint is None or not start <= checkpoint < stop:
            return super().send_body(start, stop, source, tag)
        # The response is already open. Deliver exactly the bytes the app
        # can persist, then hold the unread tail for the process boundary.
        super().send_body(start, checkpoint, source, tag)
        self.wfile.flush()
        self.server.blocked.set()
        self.server.release.wait(100)
        self.close_connection = True


def ranged_server(stack, ca, key, file, *, ranged):
    server = ThreadingHTTPServer(('127.0.0.1', 0), Ranges)
    stack.callback(server.server_close)
    name = 'selected.bin' if ranged else 'restart.bin'
    server.items = {'/' + name: (SIZE, 'qa-fixture', file)}
    server.checksums = {'/' + name: digest(file, 'sha1')} if ranged else {}
    server.ranged = ranged
    server.counts = []
    server.armed = False
    server.blocked, server.release = Event(), Event()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(ca, key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever)
    thread.start()
    stack.callback(thread.join)
    stack.callback(server.shutdown)
    stack.callback(server.release.set)
    return server


def confirm_dialog(adb, title, accept, capture):
    from time import monotonic, sleep

    deadline = monotonic() + 30
    labels = []
    while monotonic() < deadline:
        try:
            adb('shell', 'uiautomator', 'dump', '/data/local/tmp/recovery-ui.xml')
            xml = adb('exec-out', 'cat', '/data/local/tmp/recovery-ui.xml')
            nodes = list(ElementTree.fromstring(xml).iter('node'))
        except (subprocess.CalledProcessError, ElementTree.ParseError):
            sleep(0.2)
            continue
        labels = [n.get('text') for n in nodes if n.get('text')]
        if title in labels:
            identity = 'android:id/button1' if accept else 'android:id/button2'
            node = next(n for n in nodes if n.get('resource-id') == identity)
            left, top, right, bottom = map(int, re.findall(r'\d+', node.get('bounds')))
            if not accept:
                capture('restart-prompt')
            adb('shell', 'input', 'tap', str((left + right) // 2), str((top + bottom) // 2))
            return node.get('text')
        sleep(0.2)
    raise AssertionError((title, labels))


@contextmanager
def android_fixture(workspace, output):
    if shutil.disk_usage(workspace).free < 12 * 1024**3:
        raise OSError('Insufficient free capacity for the disposable Android probe')
    with TemporaryDirectory(prefix='ranged-fixture-', dir=workspace) as directory:
        with prepared_fixture(Path(directory), output) as observe:
            yield observe


@contextmanager
def prepared_fixture(root, output):
    ca, key, payload = root / 'ca.pem', root / 'key.pem', root / 'payload'
    seed = os.urandom(24)
    payload.write_bytes(shake_256(seed).digest(SIZE))
    expected_digest = digest(payload)
    subprocess.run(
        [
            'openssl',
            'req',
            '-x509',
            '-newkey',
            'rsa:2048',
            '-nodes',
            '-days',
            '1',
            '-subj',
            '/CN=localhost',
            '-addext',
            'subjectAltName=IP:127.0.0.1',
            '-keyout',
            key,
            '-out',
            ca,
        ],
        check=True,
        capture_output=True,
    )
    with ExitStack() as stack:
        # Android c-shared Go starts with an empty environment. Add only a
        # private QA trust-file lookup to the disposable bridge compilation.
        extra = root / 'fixture_ca.go'
        extra.write_text(
            'package main\nimport "os"\nfunc init() { os.Setenv("SSL_CERT_FILE", '
            + json.dumps('/data/data/' + BUNDLE + '/cache/recovery/ca.pem')
            + ') }\n'
        )
        overlay = root / 'overlay.json'
        overlay.write_text(
            json.dumps({'Replace': {str(ROOT / 'mobile_build/rclone_bridge/fixture_ca.go'): str(extra)}})
        )
        stack.enter_context(
            patch.dict(os.environ, GOFLAGS=(os.getenv('GOFLAGS', '') + ' "-overlay=' + str(overlay) + '"').strip())
        )
        ranged = ranged_server(stack, ca, key, payload, ranged=True)
        unsupported = ranged_server(stack, ca, key, payload, ranged=False)
        password = secrets.token_urlsafe(24)
        urls = {
            name: f'https://127.0.0.1:{s.server_port}/'
            for name, s in (('Ranged', ranged), ('Unsupported', unsupported))
        }
        subprocess.run(
            [ROOT / '.venv/bin/python', '-m', 'mobile_build.validation.android_download_recovery', str(root)],
            cwd=ROOT,
            input=json.dumps(dict(password=password, urls=urls)),
            text=True,
            check=True,
            env=dict(os.environ, PYTHONPATH=str(ROOT / 'Python')),
        )
        (encrypted,) = (root / 'objects').iterdir()
        ranged.items['/objects/' + encrypted.name] = encrypted.stat().st_size, 'encrypted-fixture', encrypted
        ranged.checksums['/objects/' + encrypted.name] = digest(encrypted, 'sha1')
        config = dict(
            size=SIZE, stop=STOP, sha256=expected_digest, ciphertext_sha256=digest(encrypted), password=password
        )
        (root / 'config.json').write_text(json.dumps(config))
        evidence = dict(
            expected_sha256=expected_digest,
            expected_ciphertext_sha256=config['ciphertext_sha256'],
            bytes=SIZE,
            checkpoint=STOP,
            cases={},
            controls=[],
        )
        observer = RecoveryObserver(root, output, ranged, unsupported, evidence)
        yield observer.observe
        for mode, case in evidence['cases'].items():
            check_ranges(case['resumed_ranges'], STOP, SIZE, mode == 'localcrypt')
        assert (
            set(evidence['cases']) == {'session', 'saved', 'localcrypt'}
            and evidence['unsupported_payload_bytes'] == 0
        )


class RecoveryObserver:
    """Drive only the leased QA package, recording the ranges across each process boundary."""

    def __init__(self, root, output, ranged, unsupported, evidence):
        self.root, self.output = root, output
        self.ranged, self.unsupported = ranged, unsupported
        self.evidence = evidence
        self.seen = set()
        self.mode = None
        self.can_stop = False

    def adb(self, *args, check=True):
        process = subprocess.run([*self.command, *args], capture_output=True, check=check, timeout=35)
        return process.stdout.decode().strip() if process.returncode == 0 else ''

    def write(self, name, data):
        subprocess.run([*self.command, 'shell', '-T', 'run-as', BUNDLE, 'tee', 'cache/recovery/' + name],
                       input=data, stdout=subprocess.DEVNULL, check=True, timeout=15)

    def save(self):
        (self.output / 'android-ranges.json').write_text(json.dumps(self.evidence, indent=2))

    def capture(self, name):
        image = subprocess.check_output([*self.command, 'exec-out', 'screencap', '-p'], timeout=15)
        (self.output / (name + '.png')).write_bytes(image)

    def install_fixture(self, serial):
        self.adb('shell', 'run-as', BUNDLE, 'mkdir', '-p', 'cache/recovery')
        for server in (self.ranged, self.unsupported):
            port = 'tcp:' + str(server.server_port)
            self.adb('reverse', port, port)
        for name in ('Recovery.zip', 'ca.pem', 'config.json'):
            self.write(name, (self.root / name).read_bytes())
        self.evidence.update(serial=serial, android_sdk=self.adb('shell', 'getprop', 'ro.build.version.sdk'),
                             emulator=self.adb('shell', 'getprop', 'ro.kernel.qemu'),
                             abi=self.adb('shell', 'getprop', 'ro.product.cpu.abi'))
        self.save()

    def record_resume(self):
        if self.mode:
            self.evidence['cases'][self.mode]['resumed_ranges'] = list(self.ranged.counts)

    def arm(self, mode):
        self.record_resume()
        assert mode in ('session', 'saved', 'localcrypt') and mode not in self.evidence['cases']
        self.mode = mode
        self.evidence['cases'][mode] = {}
        self.ranged.counts.clear()
        self.ranged.blocked.clear()
        self.ranged.release.clear()
        self.ranged.stop = stored_offset(STOP, mode == 'localcrypt')
        self.ranged.armed = True

    def restart(self):
        case = self.evidence['cases'][self.mode]
        case['initial_ranges'] = list(self.ranged.counts)
        check_ranges(self.ranged.counts, 0, STOP, self.mode == 'localcrypt')
        case['force_stopped_pid'] = int(self.adb('shell', 'pidof', BUNDLE))
        self.adb('shell', 'am', 'force-stop', BUNDLE)
        assert not self.adb('shell', 'pidof', BUNDLE, check=False)
        self.ranged.armed = self.can_stop = False
        self.ranged.counts.clear()
        self.ranged.release.set()
        self.write('phase', (self.mode + '-resume').encode())
        self.adb('shell', 'am', 'start', '-n', BUNDLE + '/org.beeware.android.MainActivity')
        self.save()

    def handle(self, request):
        action = request['action']
        if action == 'tap':
            if self.mode != 'session' and request['text'] == 'Resume':
                self.capture(self.mode + '-restored')
            self.adb('shell', 'input', 'tap', str(request['x']), str(request['y']))
            self.evidence['controls'].append(request['text'])
        elif action == 'dialog':
            label = confirm_dialog(self.adb, request['title'], request['accept'], self.capture)
            self.evidence['controls'].append([request['title'], label])
        elif action == 'arm':
            self.arm(request['mode'])
        elif action == 'can-stop':
            assert self.mode == request['mode']
            self.can_stop = True
        else:
            raise ValueError(action)

    def observe(self, stage, emulator, device, output):
        serial = device['serial']
        if not device.get('token') or not re.fullmatch(r'emulator-\d+', serial):
            raise ValueError('Download recovery requires an owned emulator lease.')
        self.command = [str(emulator.adb), '-s', serial]
        if stage == 'installed':
            self.install_fixture(serial)
        elif stage == 'result':
            self.record_resume()
            self.evidence['unsupported_payload_bytes'] = sum(n for _, n in self.unsupported.counts)
            self.save()
        elif stage == 'poll':
            if self.can_stop and self.ranged.blocked.is_set():
                self.restart()
                return
            raw = self.adb('exec-out', 'run-as', BUNDLE, 'cat', 'cache/recovery/action.json', check=False)
            if raw.startswith('{'):
                request = json.loads(raw)
                token = request['token']
                if token not in self.seen:
                    self.handle(request)
                    self.seen.add(token)
                    self.write('ack-' + token, b'ok')
                    self.save()


def make_package(root, settings):
    """The desktop environment owns WinZip AES and the independent rclone writer."""
    from commonUtils.archives.zip_access import open_archive
    from features.rclone.executable import get_rclone_path

    rclone = get_rclone_path()
    obscure = subprocess.check_output([rclone, 'obscure', '-'], input=secrets.token_urlsafe(24), text=True).strip()
    objects = root / 'objects'
    objects.mkdir()
    with (root / 'payload').open('rb') as stream:
        subprocess.run(
            [rclone, '--config', os.devnull, 'rcat', 'Fixture:selected.bin'],
            stdin=stream,
            check=True,
            env=dict(
                os.environ,
                RCLONE_CONFIG_FIXTURE_TYPE='crypt',
                RCLONE_CONFIG_FIXTURE_REMOTE=str(objects),
                RCLONE_CONFIG_FIXTURE_PASSWORD=obscure,
            ),
        )
    with open_archive(root / 'Recovery.zip', 'w', password=settings['password']) as archive:
        for name, url in settings['urls'].items():
            vendor = 'owncloud' if name == 'Ranged' else 'other'
            archive.writestr(name + '.txt', f'[{name}]\ntype=webdav\nurl={url}\nvendor={vendor}\n')
        archive.writestr('Secret.txt', f'[Secret]\ntype=crypt\nremote=Ranged:objects\npassword={obscure}\n')


if __name__ == '__main__':
    make_package(Path(sys.argv[1]), json.load(sys.stdin))
