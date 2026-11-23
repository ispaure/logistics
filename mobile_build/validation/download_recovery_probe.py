"""Exercise selected-file recovery across actual process exits on managed local storage."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import argparse
from contextlib import ExitStack
from hashlib import file_digest, sha1, sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote, unquote, urlsplit
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
MIB = 1024 * 1024
NAME = 'selected.bin'
PASSWORD = 'public-generated-fixture'


def blocks(seed, offset, length):
    from Cryptodome.Cipher import AES
    # Counter-mode fixture bytes depend on every absolute block position,
    # including positions within a download range or encrypted data block.
    counter, skip = divmod(offset, AES.block_size)
    cipher = AES.new(sha256(seed.encode()).digest(), AES.MODE_CTR, nonce=b'', initial_value=counter)
    cipher.encrypt(bytes(skip))
    zeroes = bytes(MIB)
    while length:
        count = min(length, MIB)
        yield cipher.encrypt(zeroes[:count])
        length -= count


class Server(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def item(self):
        return self.server.items.get(unquote(urlsplit(self.path).path))

    def do_PROPFIND(self):
        path = unquote(urlsplit(self.path).path).rstrip('/')
        items = self.server.items
        prefix = path + '/'
        children = {prefix + key[len(prefix):].split('/')[0] for key in items if key.startswith(prefix)}
        if path not in items and not children:
            return self.send_error(404)
        paths = [path, *sorted(children)] if self.headers.get('Depth') != '0' else [path]
        replies = []
        for key in paths:
            file = key in items
            kind = '<D:resourcetype/>' if file else '<D:resourcetype><D:collection/></D:resourcetype>'
            href = quote(key if file else key + '/')
            sha1_value = self.server.checksums.get(key)
            checksum = (f'<oc:checksums xmlns:oc="http://owncloud.org/ns"><oc:checksum>SHA1:{sha1_value}</oc:checksum></oc:checksums>'
                        if sha1_value else '')
            length = f'<D:getcontentlength>{items[key][0]}</D:getcontentlength>' if file else ''
            replies.append(f'<D:response><D:href>{escape(href)}</D:href><D:propstat><D:prop>{kind}{length}'
                           '<D:getlastmodified>Tue, 10 Nov 2026 12:00:00 GMT</D:getlastmodified>'
                           f'{checksum}</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>')
        body = ('<D:multistatus xmlns:D="DAV:">' + ''.join(replies) + '</D:multistatus>').encode()
        self.send_response(207)
        self.send_header('Content-Type', 'application/xml')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.serve(False)

    def do_GET(self):
        self.serve(True)

    def serve(self, body):
        item = self.item()
        if item is None:
            return self.send_error(404)
        size, tag, source = item
        etag = '"' + tag + '"'
        if self.headers.get('If-Match', etag) != etag:
            return self.send_error(412)
        interval = self.headers.get('Range')
        start, end = 0, size-1
        if interval:
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', interval)
            if not match:
                return self.send_error(416)
            start, end = int(match[1]), min(int(match[2] or end), end)
        self.send_response(206 if interval else 200)
        self.send_header('ETag', etag)
        self.send_header('Accept-Ranges', 'bytes' if self.server.ranged else 'none')
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Last-Modified', 'Tue, 10 Nov 2026 12:00:00 GMT')
        self.send_header('Content-Length', str(end-start+1))
        if interval:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if body:
            self.send_body(start, end + 1, source, tag)

    def send_body(self, start, stop, source, tag):
        if start == stop:
            return
        if source is None:
            for block in blocks(tag, start, stop - start):
                self.wfile.write(block)
        else:
            with source.open('rb') as stream:
                stream.seek(start)
                remaining = stop - start
                while remaining:
                    block = stream.read(min(MIB, remaining))
                    self.wfile.write(block)
                    remaining -= len(block)
        self.server.counts.append((start, stop - start))


def worker(workspace, mode, stop):
    from features.rclone.remote_access import NativeRemoteLocation
    root = Path(workspace)
    accept_restart = stop == -1
    package = root / 'Fixture.zip'
    def progress(done):
        if stop > 0 and done >= stop:
            os._exit(73)  # A real lost process, including live handles and locks.
    if mode.startswith('native'):
        from features.rclone.mobile.cloud import CloudClient
        from features.rclone.mobile.download_recovery import available_jobs, restored_destination
        from features.rclone.mobile.remote_downloads import RemoteDownload
        from features.rclone.mobile.service import native_service
        from features.rclone.localcrypt.mobile.resources import encrypted_storage
        from services.documents.locations import CollectionFiles
        import base64
        saved = mode == 'native-saved'
        vault = None
        if saved:
            # Substitute only the hardware key lookup. The native vault and
            # the production AES-GCM journal still run in separate processes.
            key = (root/'fixture-device-key').read_bytes()
            vault = SimpleNamespace(unlock=lambda **_: dict(path=str(root/'credentials.bin'),
                id=sha256(key).hexdigest()[:32], key=base64.b64encode(key).decode()))
        client = CloudClient(library=str(root / 'bridge.dylib'), vault=vault)
        app = SimpleNamespace(private_root=root/'App', cloud_client=client)
        assert not available_jobs(app), 'locked transfer visible'
        if not saved or not client.restore(create=True):
            client.request('import', package=base64.b64encode(package.read_bytes()).decode(),
                           password=PASSWORD, package_name=package.name, session_only=not saved)
        assert client.package_records[0]['saved'] == saved
        remote = 'Secret' if mode in ('native-crypt', 'native-local') else 'Server'
        source = native_service(client).remotes.open(NativeRemoteLocation(remote))
        jobs = available_jobs(app)
        local = CollectionFiles(app.private_root)
        app.ordinary_file_roots = lambda: {'Local files': local}
        destination = (restored_destination(app, source, jobs[0][1]) if jobs else
                       encrypted_storage(app.private_root, client, remote) if mode == 'native-crypt' else local)
        controls = []
        if jobs and not stop:
            from mobile_build.tests.support.app import mobile_app
            with mobile_app(root=app.private_root) as host:
                host.show_cloud(present=False)
                host.cloud_client = client
                host.show_locations()
                host.show_transfers()
                async def resume():
                    surface = host.transfer_controller().transfer_view
                    for prefix in ('Interrupted downloads', 'Resume '):
                        buttons = surface.native_fallback.buttons.children
                        button = next(b for b in buttons if b.text.startswith(prefix))
                        controls.append(button.text)
                        await button.on_press()
                    assert host.transfer_complete, host.transfer_message
                host.loop.run_until_complete(resume())
        elif mode == 'native-unsupported':
            from mobile_build.tests.support.app import mobile_app
            import toga
            with mobile_app(root=app.private_root) as host:
                host.show_cloud(present=False)
                host.cloud_client = client
                host.show_locations()
                host.main_window._impl.dialog_responses['ConfirmDialog'] = [accept_restart]
                with patch.object(toga, 'ConfirmDialog', wraps=toga.ConfirmDialog) as dialog:
                    result = host.loop.run_until_complete(RemoteDownload(source, NAME, False).complete(host, destination, NAME))
                    assert bool(result) == accept_restart, host.transfer_message
                    title, message = dialog.call_args.args
                    assert not host.main_window._impl.dialog_responses['ConfirmDialog']
                    if not accept_restart:
                        print(json.dumps(dict(fallback=message, control=title)))
                        return
                    controls.append(title)
        else:
            RemoteDownload(source, NAME, False).execute(client, destination, NAME, lambda: False,
                lambda **v: progress(v['done']), root=app.private_root, resume_key=jobs[0][1]['id'] if jobs else None)
        assert not available_jobs(app)
        with destination.open(NAME) as stream:
            digest = sha256()
            while block := stream.read(MIB):
                digest.update(block)
        print(json.dumps(dict(digest=digest.hexdigest(), restored=bool(jobs), accepted_restart=accept_restart, controls=controls)))
        return

    from features.rclone import session
    from features.rclone.remote_resources import RemoteResources
    from features.rclone.transfers.desktop_download_source import desktop_queue
    from features.rclone.transfers.remote_download import download_remote_item
    from features.rclone.executable import get_rclone_path
    config = root/'Fixture.session'
    try:
        RemoteResources(config, 'Server', binary=get_rclone_path())
    except ValueError:
        pass
    else:
        raise AssertionError('Locked source admitted')
    if mode == 'desktop-saved':
        config = root/'Fixture.conf'
    else:
        session.remember(config, session.read_package(package, PASSWORD), package_path=package,
                         state_password=PASSWORD, state_identity=sha256(package.read_bytes()).hexdigest())
    with patch('features.rclone.transfers.desktop_download_source.application_root', return_value=root/'App'), \
            patch('features.rclone.storage.crypt_root', return_value=root/'LocalCrypt'):
        source = RemoteResources(config, 'Secret' if mode == 'desktop-crypt' else 'Server', binary=get_rclone_path())
        release = source.acquire()
        jobs = desktop_queue(source).jobs()
        controls = []
        if (jobs and not stop) or mode == 'desktop-unsupported':
            from time import monotonic, sleep
            from commonUtils.ui import pyside as qt
            from commonUtils.ui.tasks.process_progress import ProcessProgressWindow
            from features.rclone.ui.remote_browser import RemoteBrowserView, RemoteLocation
            from features.rclone.transfers.ui.progress import open_download_progress
            app = qt.QApplication.instance() or qt.QApplication([])
            if jobs:
                published = []
                view = RemoteBrowserView(RemoteLocation(config, source.remote), published=published.append)
                menu = view.menuBar().actions()[0].menu()
                menu.aboutToShow.emit()
                interrupted = next(a for a in menu.actions() if a.text() == 'Interrupted downloads')
                item = interrupted.menu().actions()[0]
                resume = next(a for a in item.menu().actions() if a.text() == 'Resume')
                controls.extend([interrupted.text(), resume.text()])
                resume.trigger()
                window = next(w for w in app.topLevelWidgets() if isinstance(w, ProcessProgressWindow))
            else:
                window = open_download_progress(source, NAME, root/NAME, published=lambda dest: None)
            deadline = monotonic() + 600
            while window.result is None and monotonic() < deadline:
                app.processEvents()
                sleep(.01)
            assert window.result is not None, 'Timed out waiting for selected-file transfer'
            if mode == 'desktop-unsupported':
                button = next(b for b in window.findChildren(qt.QPushButton) if b.text() == 'Download from byte zero')
                if not accept_restart:
                    print(json.dumps(dict(fallback=window.details.text(), control=button.text())))
                    window.close()
                    return
                controls.append(button.text())
                button.click()
                window = next(w for w in app.topLevelWidgets() if isinstance(w, ProcessProgressWindow) and w is not window)
                while window.result is None and monotonic() < deadline:
                    app.processEvents()
                    sleep(.01)
                assert window.result and window.result.succeeded, window.details.text()
                window.close()
            else:
                assert window.result.succeeded and published == [root/NAME], window.details.text()
                window.close()
                while not view.prepare_close() and monotonic() < deadline:
                    app.processEvents()
                    sleep(.01)
                assert view.prepare_close()
                view.close()
            app.processEvents()
        else:
            download_remote_item(source, NAME, root/NAME, cancelled=lambda: False,
                progress=lambda stats: progress(stats['bytes']), resume_key=jobs[0]['id'] if jobs else None)
        assert not desktop_queue(source).jobs()
        release()
        with (root/NAME).open('rb') as stream:
            print(json.dumps(dict(digest=file_digest(stream, 'sha256').hexdigest(), restored=bool(jobs),
                                  accepted_restart=accept_restart, controls=controls)))


def exercise(root, size, mode):
    from commonUtils.archives.zip_access import open_archive
    from features.rclone.executable import get_rclone_path
    from mobile_build.cloud_build import run
    server = ThreadingHTTPServer(('127.0.0.1', 0), Server)
    native = mode.startswith('native')
    seed = os.urandom(16).hex()
    expected, checksum = sha256(), sha1()
    for block in blocks(seed, 0, size):
        expected.update(block)
        if mode in ('native-plain', 'native-saved'):
            checksum.update(block)
    server.items = {'/'+NAME: (size, seed, None)}
    server.checksums = {'/'+NAME: checksum.hexdigest()} if mode in ('native-plain', 'native-saved') else {}
    server.ranged = not mode.endswith('unsupported')
    server.counts = []
    with ExitStack() as stack:
        stack.callback(server.server_close)
        ca = root / 'ca.pem'
        binary = str(get_rclone_path())
        webdav = native or mode == 'desktop-crypt'
        if webdav:
            key = root/'key.pem'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1', '-keyout', key, '-out', ca],
                check=True, capture_output=True)
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(ca, key)
            server.socket = tls.wrap_socket(server.socket, server_side=True)
        if native:
            library = root/'bridge.dylib'
            run(str(ROOT/'mobile_build/.tools/go/bin/go'), 'build', '-buildmode=c-shared', '-o', str(library), '.')
            if mode == 'native-saved':
                (root/'fixture-device-key').write_bytes(os.urandom(32))
        url = f'{"https" if webdav else "http"}://127.0.0.1:{server.server_port}/'
        with open_archive(root/'Fixture.zip', 'w', password=PASSWORD) as archive:
            if webdav:
                archive.writestr('server.txt', f'[Server]\ntype=webdav\nurl={url}\nvendor={"owncloud" if server.checksums else "other"}\n')
            else:
                config = f'[Server]\ntype=http\nurl={url}\n'
                archive.writestr('server.txt', config)
                if mode == 'desktop-saved':
                    (root/'Fixture.conf').write_text(config)
            if mode in ('native-crypt', 'native-local', 'desktop-crypt'):
                password = subprocess.check_output([binary, 'obscure', PASSWORD], text=True).strip()
                archive.writestr('secret.txt', f'[Secret]\ntype=crypt\nremote=Server:objects\npassword={password}\n')
                # The desktop CLI produces the oracle ciphertext independently of the mobile reader.
                ciphertext = root/'objects'
                ciphertext.mkdir()
                env = dict(os.environ, RCLONE_CONFIG_FIXTURE_TYPE='crypt', RCLONE_CONFIG_FIXTURE_REMOTE=str(ciphertext),
                           RCLONE_CONFIG_FIXTURE_PASSWORD=password)
                with subprocess.Popen([binary, '--config', os.devnull, 'rcat', 'Fixture:'+NAME],
                                      stdin=subprocess.PIPE, env=env) as child:
                    for block in blocks(seed, 0, size):
                        child.stdin.write(block)
                    child.stdin.close()
                    if child.wait():
                        raise RuntimeError('Fixture encryption failed.')
                stored, = ciphertext.iterdir()
                server.items['/objects/'+stored.name] = stored.stat().st_size, seed, stored
        thread = Thread(target=server.serve_forever)
        thread.start()
        stack.callback(thread.join)
        stack.callback(server.shutdown)
        chunk = (4 if native else 16)*MIB
        first = (size*6//7//chunk)*chunk
        second = min(first + chunk, (size-1)//chunk*chunk)
        stops = [0, -1] if mode.endswith('unsupported') else list(dict.fromkeys([first, second, 0]))
        receipt = dict(mode=mode, size=size, expected_sha256=expected.hexdigest(), processes=[])
        for stop in stops:
            server.counts.clear()
            python = ROOT/('mobile_build/.venv/bin/python' if native else '.venv/bin/python')
            child = subprocess.run([python, __file__, '--worker', str(root), '--mode', mode, '--stop', str(stop)],
                env=dict(os.environ, COMMONUTILS_STORAGE_ROOT=str(root/'commonutils'),
                         **({'RCLONE_CA_CERT': str(ca)} if webdav else {}),
                         TOGA_BACKEND='toga_dummy', QT_QPA_PLATFORM='offscreen',
                         PYTHONPATH=os.pathsep.join([str(ROOT/'Python'), str(ROOT)])),
                capture_output=True, text=True)
            if child.returncode != (73 if stop > 0 else 0):
                raise RuntimeError(child.stderr[-2000:] + child.stdout[-500:])
            count = sum(n for _, n in server.counts)
            step = dict(exit=child.returncode, stop=stop, fetched=count,
                        ranges=len(server.counts), first_payload_range=next((pos for pos,n in server.counts if n > 32), None))
            receipt['processes'].append(step)
            if stop > 0:
                job, = (root/'App'/'DownloadQueue').glob('*/*.job')
                assert NAME.encode() not in job.read_bytes()
                assert not (root/NAME).exists()
            else:
                result = json.loads(child.stdout.strip().splitlines()[-1])
                step.update(result)
                if 'fallback' in result:
                    assert count == 0 and 'byte zero' in result['fallback']
                elif stop == -1:
                    assert count == size and result['accepted_restart'] and result['digest'] == expected.hexdigest(), step
                else:
                    assert result['digest'] == expected.hexdigest() and result['restored']
            if not mode.endswith('unsupported'):
                previous = receipt['processes'][-2]['stop'] if len(receipt['processes']) > 1 else 0
                end = stop or size
                if webdav:
                    # One authenticated 16-byte tag per 64 KiB block plus bounded
                    # header reads during range/version validation.
                    overhead = ((end-previous+65535)//65536)*16 + 32*(len(server.counts)+1)
                    assert end-previous <= count <= end-previous+overhead, step
                else:
                    assert count == end-previous, step
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--mode', required=True, choices=('desktop-http', 'desktop-crypt', 'desktop-saved', 'desktop-unsupported',
                        'native-local', 'native-crypt', 'native-plain', 'native-saved', 'native-unsupported'))
    parser.add_argument('--size', type=int, default=64*MIB + 137)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--stop', type=int, default=0)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker, args.mode, args.stop)
    from logistics_build.build_retention import scratch
    if not args.receipt or args.size < 4*16*MIB:
        parser.error('Provide a receipt path and at least 64 MiB.')
    with scratch() as root:
        free = shutil.disk_usage(root).free
        copies = 2 if args.mode in ('native-crypt', 'native-local', 'desktop-crypt') else 1
        if free < copies*args.size + 12*1024**3:
            raise OSError('Insufficient free space for the selected fixture.')
        result = exercise(root, args.size, args.mode)
    result.update(free_before=free, scratch_removed=not root.exists())
    result['revision'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    result['clean_checkout'] = not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
    assert result['scratch_removed']
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
