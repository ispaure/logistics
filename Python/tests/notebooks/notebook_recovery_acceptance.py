"""Kill disposable writer processes and verify acknowledged notebook recovery."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

from features.notebooks.recovery import Repository
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from logistics_build.build_retention import scratch


def digest(book):
    return [sha256(book.page(i).to_bytes()).hexdigest() for i in range(len(book.pages))]


def writer(root, phase):
    repository = Repository(root / 'recovery')
    if phase == 'checkpoint':
        book = Notebook.new('Synthetic killed process')
        key = repository.create(book)
        editor = Editor(book, lambda book: repository.save(key, book))
        editor.apply(dict(op='stroke', points=[[50, 50, .2], [75, 90, .8]]))
        (root / 'expected.json').write_text(json.dumps(dict(key=key, digest=digest(book))))
    else:
        expected = json.loads((root / 'expected.json').read_text())
        book = repository.open(expected['key'])
        editor = Editor(book, lambda book: repository.save(expected['key'], book))
        def interrupted(*args, **kwargs):
            (root / 'ready').write_text(phase)
            time.sleep(30)
        with patch('features.notebooks.recovery.atomic_write_json', interrupted):
            editor.apply(dict(op='stroke', points=[[100, 100, .5], [150, 160, .7]]))
    (root / 'ready').write_text(phase)
    time.sleep(30)


def main(output):
    with scratch() as root:
        for phase in ('checkpoint', 'interrupted-manifest'):
            ready = root / 'ready'
            ready.unlink(missing_ok=True)
            process = subprocess.Popen([sys.executable, __file__, '--writer', str(root), '--phase', phase])
            try:
                deadline = time.monotonic() + 20
                while not ready.exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Writer failed before checkpoint: ' + phase)
                    time.sleep(.05)
            finally:
                process.kill()
                process.wait(timeout=10)
            expected = json.loads((root / 'expected.json').read_text())
            recovered = Repository(root / 'recovery').open(expected['key'])
            assert digest(recovered) == expected['digest']
            assert len(recovered.page(0).strokes) == 1
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(dict(success=True, killed_after_checkpoint=True,
            killed_before_manifest=True, acknowledged_stroke_preserved=True), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--writer', type=Path)
    parser.add_argument('--phase')
    args = parser.parse_args()
    writer(args.writer, args.phase) if args.writer else main(args.output)
