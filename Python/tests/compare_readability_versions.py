"""Compare cleanup operations and encoded bytes against an archived implementation.

Run from the repository root with PYTHONPATH=Python and the desktop interpreter.
Evidence belongs in ignored test-results; fixtures contain generated images only.
"""
import argparse
from contextlib import redirect_stdout
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch

from PIL import Image, ImageCms
from commonUtils.filesystem import files, directories
from commonUtils.runtime.diagnostics import noninteractive_logging
from features.comics import sanitization
from features.images import processing

ROOT = Path(__file__).resolve().parents[2]


def archived_module(ref, path):
    source = subprocess.check_output(['git', 'show', f'{ref}:{path}'], cwd=ROOT, text=True)
    module = ModuleType('baseline_' + Path(path).stem)
    module.__file__ = str(ROOT / path)
    exec(compile(source, str(ROOT / path), 'exec'), module.__dict__)
    return module


def snapshot(root):
    return {str(path.relative_to(root)): None if path.is_dir() else sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob('*'))}


def cleanup_run(module, root, entries, failure=None):
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir()
    for name, data in entries.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    operations, logs = [], []

    def trace(original, operation):
        def invoke(owner, *args, **kwargs):
            operations.append((operation, str(owner.path.relative_to(root)),
                               [str(arg).replace(str(root), '<root>') for arg in args]))
            if failure == operation:
                if operation in ('move', 'rename'):
                    raise OSError('fixture failure')
                return False
            return original(owner, *args, **kwargs)
        return invoke

    owner = module.CBZSanitizationMixin()
    owner.path = root / 'source.cbz'
    with patch.object(files.File, 'move_file', trace(files.File.move_file, 'move')), \
            patch.object(files.File, 'rename_file', trace(files.File.rename_file, 'rename')), \
            patch.object(files.File, 'delete_file', trace(files.File.delete_file, 'delete')), \
            patch.object(directories.Directory, 'delete', trace(directories.Directory.delete, 'rmdir')), \
            patch.object(module, 'log', lambda severity, tool, message: logs.append(
                (severity.name, tool, str(message).replace(str(root), '<root>')))):
        try:
            result = owner.sanitize_extracted_cbz(root)
        except Exception as error:
            result = {'exception': type(error).__name__}
    return dict(result=result, tree=snapshot(root), operations=operations, logs=logs)


def compare_cleanup(baseline, root):
    page = b'generated page placeholder'
    cases = {
        'root-padding': {'1.png': page, '2.jpg': page},
        'nuisance-files': {'01.png': page, '.DS_Store': b'x', 'Thumbs.db': b'x',
                           'Thumbs1.db': b'x', 'notes.txt': b'x', '__MACOSX/._01.png': b'x'},
        'preserved-metadata': {'01.png': page, 'ComicInfo.xml': b'<ComicInfo/>', 'CompressionLog.txt': b'log'},
        'one-wrapper': {'Book/1.png': page},
        'two-wrappers': {'Book/Pages/1.png': page},
        'three-wrappers-rejected': {'Book/Pages/Deep/1.png': page},
        'siblings': {'One/01.png': page, 'Two/01.png': page},
        'mixed-root-rejected': {'Book/01.png': page, '02.png': page, 'notes.txt': b'x'},
        'unsupported-after-cleanup': {'notes.txt': b'x', 'file.bin': b'x', '01.png': page},
        'padding-nonnumeric': {'1.png': page, 'cover.png': page},
        'padding-collision': {'1.png': page, '01.png': page},
        'padding-case-collision': {'1.png': page, '1.PNG': page},
    }
    for count in (89, 90, 949, 950):
        cases[f'padding-width-{count}'] = {f'{index}.png': page for index in range(count)}
    results = {}
    for name, entries in cases.items():
        for failure in (None, 'move', 'rename', 'delete', 'rmdir'):
            before = cleanup_run(baseline, root, entries, failure)
            after = cleanup_run(sanitization, root, entries, failure)
            assert after == before, (name, failure, before, after)
            results[f'{name}/{failure}'] = dict(success=after['result'], paths=len(after['tree']),
                                               operations=len(after['operations']))
    return results


def compare_encoding(baseline, root):
    results = {}
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    for mode, color in [('RGB', 'red'), ('RGB', (120, 120, 120)), ('RGBA', (40, 90, 150, 80)),
                        ('L', 120), ('P', 0), ('CMYK', (0, 50, 20, 0))]:
        source = root / 'source.tiff'
        image = Image.new(mode, (80, 120), color)
        exif = Image.Exif()
        exif[274] = 6
        exif[256], exif[257] = image.size
        image.save(source, exif=exif, **({'icc_profile': profile} if mode in ('RGB', 'RGBA') else {}))
        for extension in ('.jpg', '.webp'):
            for alpha in (False, True):
                key = f'{mode}/{color}/{extension}/{alpha}'
                outcomes = []
                for label, module in [('before', baseline), ('after', processing)]:
                    destination = root / (label + extension)
                    owner = module.ImageFile(source)
                    result = owner.compress(destination, quality_grayscale=35, quality_color=60,
                                            max_long_edge=90, max_height=100, preserve_alpha=alpha)
                    outcomes.append((result, owner.color, destination.read_bytes() if destination.exists() else None))
                    destination.unlink(missing_ok=True)
                assert outcomes[0] == outcomes[1], key
                assert outcomes[0][0], key
                results[key] = sha256(outcomes[0][2]).hexdigest()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline_cleanup = archived_module(args.baseline_ref, 'Python/features/comics/sanitization.py')
    baseline_images = archived_module(args.baseline_ref, 'Python/features/images/processing.py')
    with TemporaryDirectory(prefix='logistics-readability-parity-') as temporary, redirect_stdout(StringIO()), noninteractive_logging():
        root = Path(temporary)
        cleanup = compare_cleanup(baseline_cleanup, root / 'cleanup')
        encoding = compare_encoding(baseline_images, root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(baseline=args.baseline_ref, cleanup=cleanup, encoding=encoding), indent=2))
    print(f'Identical cleanup outcomes/traces: {len(cleanup)}; byte-identical encodings: {len(encoding)}')


if __name__ == '__main__':
    main()
