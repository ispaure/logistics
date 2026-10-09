"""Publish a release ZIP; existing assets are deliberately never overwritten."""
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote


def publish(repo, tag, archive):
    archive = Path(archive)
    if not tag.startswith('v') or archive.name != 'release.zip' or not archive.is_file():
        raise RuntimeError('Expected a v* tag and an existing release.zip')
    result = subprocess.run(
        ['gh', 'api', '--include', f'repos/{repo}/releases/tags/{quote(tag, safe="")}'],
        capture_output=True, text=True)
    if result.returncode:
        # Only a confirmed HTTP 404 means absent. Authentication/network errors abort.
        if not re.search(r'^HTTP/\S+ 404\b', result.stdout, re.MULTILINE):
            raise RuntimeError(f'Cannot check existing release: {result.stderr}')
        subprocess.run(['gh', 'release', 'create', tag, str(archive), '--repo', repo,
                        '--verify-tag', '--generate-notes'], check=True)
        return
    _, body = result.stdout.split('\r\n\r\n' if '\r\n\r\n' in result.stdout else '\n\n', 1)
    release = json.loads(body)
    if any(asset['name'] == archive.name for asset in release.get('assets', [])):
        raise RuntimeError('This release already has release.zip; refusing to overwrite it.')
    subprocess.run(['gh', 'release', 'upload', tag, str(archive), '--repo', repo], check=True)
    print('Uploaded release.zip to the existing release; its notes and draft state are unchanged.')


if __name__ == '__main__':
    publish(os.environ['GH_REPO'], os.environ['RELEASE_TAG'], os.environ['RELEASE_ZIP'])
