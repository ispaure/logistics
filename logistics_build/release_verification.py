"""Public source ZIP verification owned by the Logistics release policy."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryFile
from urllib.parse import urlparse
from urllib.request import urlopen
import zipfile


def verify_asset(asset, commit, dependency, cancelled, *, tag=None, opener=urlopen):
    expected = asset.get('digest', '')
    if len(expected) != 71 or not expected.startswith('sha256:'):
        raise ValueError('Release asset needs a SHA-256 digest.')
    url = asset['browser_download_url']
    if urlparse(url).scheme != 'https':
        raise ValueError('Public release download must use HTTPS.')
    digest = hashlib.sha256()
    size = 0
    with TemporaryFile() as archive:
        with opener(url, timeout=60) as incoming:
            while chunk := incoming.read(1024*1024):
                if cancelled.is_set():
                    raise RuntimeError('Public ZIP verification cancelled; no completion recorded.')
                size += len(chunk)
                if size > 2*1024**3:
                    raise ValueError('Source release exceeds the bounded verification size.')
                digest.update(chunk)
                archive.write(chunk)
        if digest.hexdigest() != expected.removeprefix('sha256:'):
            raise ValueError('Downloaded release ZIP SHA-256 differs from the published asset.')
        archive.seek(0)
        with zipfile.ZipFile(archive) as files:
            names = files.namelist()
            if len(names) != len(set(names)):
                raise ValueError('Release ZIP has duplicate member names.')
            manifest = json.loads(files.read('Logistics/.app-install.json'))
            version = json.loads(files.read('Logistics/.app-version.json'))
            if (manifest['revision'] != commit or version['revision'] != commit
                    or manifest.get('commonUtils_revision') != dependency):
                raise ValueError('Published ZIP source/dependency differs from the reviewed release.')
            if tag is not None and version.get('tag') != tag:
                raise ValueError('Published ZIP release tag differs from the reviewed release.')
            for name, checksum in manifest['files'].items():
                if Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name:
                    raise ValueError('Invalid release manifest member.')
                if hashlib.sha256(files.read('Logistics/'+name)).hexdigest() != checksum:
                    raise ValueError('Release ZIP member differs from its manifest: '+name)
    return dict(sha256=digest.hexdigest(), bytes=size, logistics_commit=commit, commonUtils_commit=dependency)
