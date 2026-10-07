"""Compare pristine pre-password compression against the current worktree."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import mkdtemp

import argparse
import platform

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, help='New directory for disposable fixtures, traces and comparison.json')
args = parser.parse_args()
REPO = Path(__file__).resolve().parents[2]
ROOT = args.output_dir.resolve() if args.output_dir else Path(mkdtemp(prefix='logistics-zip-version-parity-'))
ROOT.mkdir(parents=True, exist_ok=True)
OLD = ROOT / 'before'
OLD.mkdir()
ref = '43e777cafe8c5bd45fece1538ba32ee75ca2db91'
shared_ref = subprocess.check_output(['git', 'rev-parse', f'{ref}:Python/commonUtils'], cwd=REPO, text=True).strip()
for repo, revision, destination, paths in [(REPO, ref, OLD, ['Python']), (REPO / 'Python/commonUtils', shared_ref, OLD / 'Python/commonUtils', [])]:
    destination.mkdir(parents=True, exist_ok=True)
    data = subprocess.check_output(['git', 'archive', revision, *paths], cwd=repo)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(destination, filter='data')

CHILD = ROOT / 'run_compression.py'
CHILD.write_text(r'''
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch
import zipfile
import pyzipper
from commonUtils import zipUtils
from features.comics import cbz

path, output, password, keep = sys.argv[1:]
path, output = Path(path), Path(output)
password = None if password == '-' else password
keep = keep == '1'
records = {}
def tree(root):
    return {item.relative_to(root).as_posix() + ('/' if item.is_dir() else ''):
            None if item.is_dir() else [item.stat().st_size, sha256(item.read_bytes()).hexdigest()]
            for item in sorted(root.rglob('*'))}
probe = path.parent / 'explicit-password-extraction'
records['explicit_extract_success'] = zipUtils.unzip_file(path, probe, pwd=password)
records['explicit_extraction'] = tree(probe) if probe.exists() else {}
real_unzip = zipUtils.unzip_file
real_sanitize = cbz.CBZFile.sanitize_extracted_cbz
real_replace = cbz.replace_archive
def unzip(source, destination, *args, **kwargs):
    result = real_unzip(source, destination, *args, **kwargs)
    records['compression_extraction_success'] = result
    records['compression_extraction'] = tree(Path(destination))
    return result
def sanitize(self, destination):
    result = real_sanitize(self, destination)
    records['sanitization_success'] = result
    records['sanitized'] = tree(Path(destination))
    return result
def replace(source, *args, **kwargs):
    records['staged_result'] = tree(Path(source))
    return real_replace(source, *args, **kwargs)
before = path.read_bytes()
with patch.object(zipUtils, 'unzip_file', side_effect=unzip), patch.object(cbz.CBZFile, 'sanitize_extracted_cbz', sanitize), patch.object(cbz, 'replace_archive', side_effect=replace), patch('features.comics.compression_stats.datetime') as clock:
    clock.now.return_value = datetime(2020, 1, 2, 3, 4, 5)
    records['compression_success'] = cbz.CBZFile(path).compress_to_webp(keep, not keep)
records['original_unchanged'] = path.read_bytes() == before
with zipfile.ZipFile(path) as headers:
    records['encrypted'] = any(info.flag_bits & 1 for info in headers.infolist())
if records['compression_success']:
    with pyzipper.AESZipFile(path) as archive:
        if password:
            archive.setpassword(password.encode())
        records['archive_comment'] = archive.comment.hex()
        records['final'] = {info.filename: None if info.is_dir() else [info.file_size, sha256(archive.read(info)).hexdigest()]
                            for info in archive.infolist()}
        records['all_aes256'] = all(getattr(info, 'wz_aes_strength', None) == 3 for info in archive.infolist() if not info.is_dir())
output.write_text(json.dumps(records, indent=2))
''')

# Actual valid CBZ files, generated locally rather than using someone's library.
from PIL import Image, ImageDraw
import pyzipper
import zipfile
pages = {}
image = Image.new('RGB', (512, 768), 'white')
draw = ImageDraw.Draw(image)
for n in range(8):
    y = 12 + n * 92
    draw.rectangle((12, y, 498, y + 80), fill=(n * 30, 80, 230 - n * 20), outline='black', width=4)
for filename, image, fmt in [('1.png', image, 'PNG'), ('2.jpg', image.convert('L'), 'JPEG'), ('3.webp', image, 'WEBP')]:
    stream = io.BytesIO()
    image.save(stream, fmt)
    pages[filename] = stream.getvalue()
stream = io.BytesIO()
image.save(stream, 'GIF', save_all=True, append_images=[Image.new('RGB', image.size, 'orange')], duration=100, loop=0)
pages['4.gif'] = stream.getvalue()
metadata = b'<ComicInfo><Series>Version parity fixture</Series><Writer>Test Writer</Writer><Pages><Page Image="0" Type="FrontCover"/><Page Image="1"/></Pages></ComicInfo>'
layouts = {
    'root': {name: data for name, data in pages.items()},
    'one-wrapper': {'Book/' + name: data for name, data in pages.items()},
    'two-wrappers': {'Book/Pages/' + name: data for name, data in pages.items()},
    'two-chapters': {('Chapter 1/' if n < 2 else 'Chapter 2/') + name: data for n, (name, data) in enumerate(pages.items())},
}
for entries in layouts.values():
    entries.update({'ComicInfo.xml': metadata, 'notes.txt': b'Original cleanup policy removes this', '.DS_Store': b'macOS sidecar', '__MACOSX/._1.png': b'macOS sidecar'})

results = {}
for layout, entries in layouts.items():
    for keep in (False, True):
        for version, source, password in [('before-plain', OLD, None), ('after-plain', REPO, None), ('after-aes256', REPO, 'test-only-comic-password')]:
            name = f'{layout}-keep{int(keep)}-{version}'
            folder = ROOT / 'runs' / name
            folder.mkdir(parents=True)
            path = folder / 'comic.cbz'
            with pyzipper.AESZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                if password:
                    archive.setpassword(password.encode())
                    archive.setencryption(pyzipper.WZ_AES, nbits=256)
                for filename, data in entries.items():
                    archive.writestr(filename, data)
            (folder / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password = test-only-comic-password\n')
            output = folder / 'trace.json'
            env = dict(os.environ, PYTHONPATH=str(source / 'Python'), QT_QPA_PLATFORM='offscreen')
            completed = subprocess.run([sys.executable, str(CHILD), str(path), str(output), password or '-', str(int(keep))], cwd=source, env=env, capture_output=True, text=True)
            (folder / 'run.log').write_text(completed.stdout + completed.stderr)
            if completed.returncode:
                raise RuntimeError(f'Run failed: {name}, see {folder / "run.log"}\n' + completed.stdout[-3000:] + completed.stderr[-3000:])
            records = json.loads(output.read_text())
            assert records['compression_success'], name
            assert records['explicit_extract_success'], name
            assert records['encrypted'] == bool(password), name
            if password:
                assert records['all_aes256'], name
            results[name] = records
        group = [results[f'{layout}-keep{int(keep)}-{version}'] for version in ('before-plain', 'after-plain', 'after-aes256')]
        for stage in ('explicit_extraction', 'compression_extraction', 'sanitized', 'staged_result', 'final', 'archive_comment'):
            assert all(record[stage] == group[0][stage] for record in group[1:]), (layout, keep, stage)
        print(f'PASS {layout}, always_keep={keep}: all extraction/sanitization/staging/final manifests equal', flush=True)

# The old application did not supply passwords during comic compression.
folder = ROOT / 'runs' / 'before-aes256-unsupported'
folder.mkdir(parents=True)
path = folder / 'comic.cbz'
with pyzipper.AESZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    archive.setpassword(b'test-only-comic-password')
    archive.setencryption(pyzipper.WZ_AES, nbits=256)
    for filename, data in layouts['root'].items():
        archive.writestr(filename, data)
output = folder / 'trace.json'
completed = subprocess.run([sys.executable, str(CHILD), str(path), str(output), 'test-only-comic-password', '0'], cwd=OLD, env=dict(os.environ, PYTHONPATH=str(OLD / 'Python'), QT_QPA_PLATFORM='offscreen'), capture_output=True, text=True)
(folder / 'run.log').write_text(completed.stdout + completed.stderr)
assert completed.returncode == 0, folder / 'run.log'
legacy = json.loads(output.read_text())
assert legacy['explicit_extract_success']
assert legacy['explicit_extraction'] == results['root-keep0-before-plain']['explicit_extraction']
assert not legacy['compression_success'] and legacy['original_unchanged']
summary = {'platform': platform.platform(), 'python': sys.version, 'baseline_logistics': ref, 'baseline_commonutils': shared_ref, 'successful_full_runs': 24, 'legacy_password_extraction_same_layout': True, 'legacy_encrypted_full_compression_unsupported_original_preserved': True, 'compared_stages': ['explicit extraction', 'compression extraction', 'sanitized', 'staged result', 'final archive'], 'results': results, 'legacy_encrypted': legacy}
(ROOT / 'comparison.json').write_text(json.dumps(summary, indent=2))
print('RESULT_ROOT=' + str(ROOT), flush=True)
print('All 24 full compression runs passed; old AES extraction matched, old encrypted compression safely failed.', flush=True)
