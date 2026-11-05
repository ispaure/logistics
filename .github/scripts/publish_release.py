"""Publish reviewed release metadata; existing assets are never overwritten."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import quote

NOTES_DIR = Path(__file__).resolve().parents[1] / 'release-notes'
VERSIONED_TAG = re.compile(r'(v\d+\.\d+\.\d+)(?:-(alpha|beta|main)[.-](\d+))?')


def expected_metadata(tag, *, notes_dir=None):
    """Select reviewed notes within this version/channel, without API effects.

    Callers verifying retained publication must supply the captured source's
    notes directory, rather than an unrelated newer checkout.
    """
    directory = Path(notes_dir) if notes_dir is not None else NOTES_DIR
    if not re.fullmatch(r'v[\w.-]+', tag):
        raise RuntimeError('Invalid release notes tag.')
    exact = directory / (tag + '.md')
    if exact.is_symlink() or exact.exists() and not exact.is_file():
        raise RuntimeError('Exact reviewed notes path is not a regular file.')
    selected = exact if exact.is_file() else None
    parsed = VERSIONED_TAG.fullmatch(tag)
    if selected is None and parsed:
        version, channel, number = parsed.groups()
        if channel:
            candidates = []
            for path in directory.glob(version + '-' + channel + '*.md'):
                match = VERSIONED_TAG.fullmatch(path.stem)
                if match and match[1] == version and match[2] == channel and int(match[3]) < int(number):
                    candidates.append((int(match[3]), path))
            if candidates:
                latest = max(number for number, _ in candidates)
                eligible = [path for number, path in candidates if number == latest]
                if len(eligible) != 1:
                    raise RuntimeError('Ambiguous reviewed release notes; add an exact tag file.')
                selected = eligible[0]
            elif channel == 'main' and (directory / (version + '.md')).is_file():
                selected = directory / (version + '.md')
        if selected is None:
            raise RuntimeError('Missing reviewed release notes for this version/channel; add an exact tag file before publishing.')
    if selected is None:
        return None  # Historical non-three-part tags retain generated notes.
    if selected.is_symlink() or not stat.S_ISREG(selected.stat().st_mode) or selected.stat().st_size > 65536:
        raise RuntimeError('Reviewed release notes must be a bounded regular file.')
    try:
        text = selected.read_bytes().decode('utf-8')
    except UnicodeError as error:
        raise RuntimeError('Reviewed release notes require UTF-8 text.') from error
    lines = text.splitlines(keepends=True)
    if not lines or not lines[0].startswith('# ') or not lines[0][2:].strip():
        raise RuntimeError('Release notes require a title on the first line.')
    if '\0' in text or not ''.join(lines[1:]).strip():
        raise RuntimeError('Reviewed release notes require a nonempty description.')
    if selected != exact:
        lines[0] = '# Logistics ' + tag.removeprefix('v') + '\n'
        text = ''.join(lines)
    return dict(name=lines[0][2:].strip(), body=text)


def verify_metadata(release, expected):
    """Require reviewed title/body without changing release state or assets."""
    if expected is not None and (not isinstance(release, dict) or any(release.get(key) != expected[key] for key in ('name', 'body'))):
        raise RuntimeError('Published release title/body does not match the reviewed notes.')


def read_release(repo, tag):
    result = subprocess.run(
        ['gh', 'api', '--include', f'repos/{repo}/releases/tags/{quote(tag, safe="")}'],
        capture_output=True, text=True)
    if result.returncode:
        if re.search(r'^HTTP/\S+ 404\b', result.stdout, re.MULTILINE):
            return None
        raise RuntimeError(f'Cannot check existing release: {result.stderr}')
    _, body = result.stdout.split('\r\n\r\n' if '\r\n\r\n' in result.stdout else '\n\n', 1)
    return json.loads(body)


def asset_identities(release):
    # Downloads may advance while metadata is repaired. Asset identity/bytes must
    # remain fixed; volatile counters are not evidence of asset replacement.
    return sorted((tuple(asset.get(key) for key in ('id', 'name', 'size', 'digest'))
                   for asset in release.get('assets', [])), key=repr)


def publish(repo, tag, archive):
    archive = Path(archive)
    if not tag.startswith('v') or archive.name != 'release.zip' or not archive.is_file():
        raise RuntimeError('Expected a v* tag and an existing release.zip')
    release = read_release(repo, tag)
    expected = expected_metadata(tag)
    if release is None:
        command = ['gh', 'release', 'create', tag, str(archive), '--repo', repo, '--verify-tag']
        if re.fullmatch(r'v\d+(?:\.\d+){1,2}-(alpha|beta)(?:[.-]\d+)?', tag):
            command.append('--prerelease')
        if expected is None:
            subprocess.run([*command, '--generate-notes'], check=True)
        else:
            # Only this owned temporary note is normalized; curated sources stay immutable.
            with TemporaryDirectory(prefix='logistics-release-notes-') as temporary:
                notes = Path(temporary) / 'reviewed.md'
                notes.write_text(expected['body'], encoding='utf-8')
                subprocess.run([*command, '--title', expected['name'], '--notes-file', str(notes)], check=True)
            verify_metadata(read_release(repo, tag), expected)
        return
    if expected is not None:
        if any(release.get(key) != expected[key] for key in ('name', 'body')):
            release_id = release.get('id')
            if type(release_id) is not int or release_id <= 0:
                raise RuntimeError('Existing release has no valid metadata update identity.')
            subprocess.run(['gh', 'api', '--method', 'PATCH', f'repos/{repo}/releases/{release_id}', '--input', '-'],
                input=json.dumps(expected), text=True, capture_output=True, check=True)
            refreshed = read_release(repo, tag)
            verify_metadata(refreshed, expected)
            # A metadata repair must never publish a draft, change its channel,
            # or replace/upload/delete any existing asset.
            if (any(refreshed.get(key) != release.get(key) for key in ('id', 'draft', 'prerelease'))
                    or asset_identities(refreshed) != asset_identities(release)):
                raise RuntimeError('Release state/assets changed during metadata reconciliation; inspect before continuing.')
            release = refreshed
        else:
            verify_metadata(release, expected)
    if any(asset['name'] == archive.name for asset in release.get('assets', [])):
        raise RuntimeError('This release already has release.zip; refusing to overwrite it.')
    subprocess.run(['gh', 'release', 'upload', tag, str(archive), '--repo', repo], check=True)
    print('Uploaded release.zip to the existing release without replacing assets or changing draft state.')


if __name__ == '__main__':
    publish(os.environ['GH_REPO'], os.environ['RELEASE_TAG'], os.environ['RELEASE_ZIP'])
