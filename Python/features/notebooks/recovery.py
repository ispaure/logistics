"""Atomic per-page recovery, revision guards and immutable notebook snapshots."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from functools import wraps
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from struct import Struct
from uuid import uuid4
from weakref import WeakKeyDictionary

from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import serialize_mutation
from commonUtils.persistence.locking import file_lock
from commonUtils.persistence.atomic import atomic_write_bytes
from commonUtils.runtime.streams import file_sha256, read_up_to
from .notebook import MAX_ARCHIVE, Notebook, Page, identifier
from .ink import InkPage, MAX_PAGE_POINTS, MAX_POINTS, MAX_SCENE_FRAMES, Stroke, WIDTH
from .protocol import RecoveryIncomplete

STROKES_PER_CHECKPOINT = 32
STROKE_RECORD_LIMIT = 1024 * 1024
STROKE_RECORD = re.compile(r'stroke-[0-9a-f]{64}-[0-9]{3}\.json')
NATIVE_COORDS = Struct('<ff')


def locked_draft(method):
    @wraps(method)
    @serialize_mutation
    def run(self, key, *args, **kwargs):
        with file_lock(self.root / ('.' + identifier(key) + '.lock'), timeout=3) as acquired:
            if not acquired:
                raise OSError('Another window is saving this notebook. Try again.')
            return method(self, key, *args, **kwargs)
    return run


def journal(directory, manifest):
    if manifest is None:
        return None, []
    digest = sha256(manifest).hexdigest()
    prefix = 'stroke-' + digest + '-'
    entries = sorted(path for path in directory.glob(prefix + '*.json') if STROKE_RECORD.fullmatch(path.name))
    if len(entries) >= STROKES_PER_CHECKPOINT or any(
            path.name != f'{prefix}{index:03d}.json' for index, path in enumerate(entries, 1)):
        raise ValueError('Notebook recovery stroke journal is incomplete.')
    return (digest, len(entries)), entries


def stroke_record(page, stroke):
    points = []
    for x, y, pressure, width in stroke.points:
        x, y = NATIVE_COORDS.unpack(NATIVE_COORDS.pack(x - WIDTH / 2, y))
        points.append([x + WIDTH / 2, y, round(pressure * 255) / 255, width])
    return dict(page=page.id, stroke=dict(stroke.payload(), points=points))


def replay_stroke(notebook, pages, path):
    with path.open('rb') as stream:
        raw = read_up_to(stream, STROKE_RECORD_LIMIT + 1)
    if len(raw) > STROKE_RECORD_LIMIT:
        raise ValueError('Notebook recovery stroke is too large.')
    entry = json.loads(raw)
    record = entry['record']
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False).encode()
    if sha256(payload).hexdigest() != entry['sha256'] or record['page'] not in pages:
        raise ValueError('Notebook recovery stroke failed its integrity check.')
    ink = notebook.page(pages[record['page']])
    stroke = Stroke(**record['stroke'])
    if (ink.warning or not re.fullmatch(r'[0-9a-f]{32}', stroke.id)
            or stroke.id in ink.order or stroke.layer not in {row[0] for row in ink.layers if row[2]}
            or not 1 <= len(stroke.points) <= MAX_POINTS
            or any(len(point) != 4 or not all(math.isfinite(value) for value in point) for point in stroke.points)
            or sum(len(item.points) for item in ink.strokes) + len(stroke.points) > MAX_PAGE_POINTS):
        raise ValueError('Invalid notebook recovery stroke.')
    if stroke.color_rgba is not None:
        stroke.color_rgba = tuple(stroke.color_rgba)
    ink.strokes.append(stroke)
    ink.order = [*ink.order, stroke.id]


class Repository:
    @locked_draft
    def delete(self, key, *, expected=None):
        """Remove this ordinary recovery identity after source deletion."""
        import shutil
        if expected is not None:
            directory = self.root / identifier(key)
            revision, _ = journal(directory, (directory / 'state.json').read_bytes())
            if self.revisions.get(expected, {}).get(key) != revision:
                raise ValueError('This notebook changed in another window. Reopen its draft before discarding.')
        try:
            shutil.rmtree(self.root / identifier(key))
        except FileNotFoundError:
            if (self.root / identifier(key)).exists():
                raise

    def __init__(self, root, *, max_bytes=MAX_ARCHIVE):
        self.max_bytes = max_bytes
        self.revisions = WeakKeyDictionary()
        self.pending_strokes = WeakKeyDictionary()
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self):
        result = []
        for path in self.root.glob('*/base.rmdoc'):
            try:
                state = json.loads((path.parent / 'state.json').read_text())
                result.append((path.parent.name, str(state['name'])))
            except (OSError, ValueError, KeyError):
                continue
        return sorted(result, key=lambda row: row[1].casefold())

    def create(self, notebook, *, source_bytes=None):
        key = uuid4().hex
        directory = self.root / key
        directory.mkdir()
        # Callers opening a validated source already hold its exact ZIP bytes.
        # Avoid recompressing a large PDF just to start its recovery draft.
        atomic_write_bytes(directory / 'base.rmdoc', notebook.to_bytes() if source_bytes is None else source_bytes)
        # A new recovery identity has no previous manifest, even when its model
        # was copied from another saved notebook.
        self.save(key, notebook)
        return key

    def adopt(self, key, notebook, recovered):
        """Bind freshly read source bytes to an explicitly observed recovery revision."""
        key = identifier(key)
        self.revisions.setdefault(notebook, {})[key] = self.revisions[recovered][key]

    @serialize_mutation
    def check_revision(self, key, notebook):
        _, previous, _, _ = self._checked_revision(key, notebook)
        return previous

    def _checked_revision(self, key, notebook):
        directory = self.root / identifier(key)
        manifest = directory / 'state.json'
        previous = manifest.read_bytes() if manifest.exists() else None
        revision, entries = journal(directory, previous)
        pending = self.pending_strokes.get(notebook, {})
        if key in pending:
            target, digest = pending[key]
            expected = self.revisions[notebook][key]
            if (revision == (expected[0], expected[1] + 1) and entries[-1] == target
                    and file_sha256(target) == digest):
                self.revisions[notebook][key] = revision
            if self.revisions[notebook][key] == revision:
                del pending[key]
        if self.revisions.get(notebook, {}).get(key) != revision:
            raise ValueError('This notebook changed in another window. Reopen its saved copy before editing.')
        return directory, previous, revision, entries

    @locked_draft
    def append_stroke(self, key, notebook, index):
        directory, previous, revision, entries = self._checked_revision(key, notebook)
        ink = notebook.page(index)
        if sum(len(stroke.points) for stroke in ink.strokes) > MAX_PAGE_POINTS:
            raise ValueError('Ink page exceeds the editable point limit.')
        stroke = ink.strokes[-1]
        record = stroke_record(notebook.pages[index], stroke)
        stroke.points = record['stroke']['points']
        extra_frames = len(ink.strokes) - len(ink._baseline)
        if (previous is None or notebook.structure_dirty or len(entries) + 1 >= STROKES_PER_CHECKPOINT
                or len(ink._frames) + extra_frames >= MAX_SCENE_FRAMES - 1):
            # Keep the living model's stroke IDs so the canvas can acknowledge
            # just the newest stroke instead of repainting the page.
            self._save(key, notebook, preserve_active_ink=True)
            return
        payload = json.dumps(record, ensure_ascii=False, allow_nan=False).encode()
        entry = dict(record=record, sha256=sha256(payload).hexdigest())
        target = directory / f'stroke-{revision[0]}-{len(entries) + 1:03d}.json'
        expected = json.dumps(entry, ensure_ascii=False, allow_nan=False).encode()
        if len(expected) > STROKE_RECORD_LIMIT:
            self._save(key, notebook, preserve_active_ink=True)
            return
        publication_error = None
        try:
            atomic_write_json(target, entry, durable_directory=True)
        except Exception as error:
            try:
                actual = target.read_bytes()
            except FileNotFoundError:
                raise error
            except OSError as read_error:
                self.pending_strokes.setdefault(notebook, {})[key] = target, sha256(expected).hexdigest()
                raise RecoveryIncomplete('Notebook stroke recovery could not be verified.', published=None) from read_error
            if actual != expected:
                raise RecoveryIncomplete('Notebook stroke recovery changed during publication.', published=None) from error
            publication_error = error
        self.revisions.setdefault(notebook, {})[key] = (revision[0], len(entries) + 1)
        if publication_error is not None:
            raise RecoveryIncomplete('The stroke was published, but recovery durability could not be confirmed.',
                                     published=True) from publication_error

    @locked_draft
    def save(self, key, notebook, *, source_bytes=None):
        return self._save(key, notebook, source_bytes=source_bytes)

    def _save(self, key, notebook, *, source_bytes=None, preserve_active_ink=False):
        directory = self.root / identifier(key)
        manifest = directory / 'state.json'
        previous = self.check_revision(key, notebook)
        # Explicit source adoption preserves the archive exactly, including
        # missing legacy ink members. Loading a blank page may synthesize ink.
        source_baseline = Notebook.read(source_bytes, max_bytes=self.max_bytes) if source_bytes is not None else None
        # Each immutable page snapshot precedes publication of its manifest.
        # Interrupted saves leave the previous manifest and pages recoverable.
        pages = []
        normalized = []
        blank = None
        for page in notebook.pages:
            ink = page.ink
            if ink is None:
                raw = notebook.unloaded_ink(page)
                if raw is None:
                    if blank is None:
                        blank = InkPage.blank().raw
                    raw = blank
            else:
                raw = ink.to_bytes()
                decoded = ink if raw is ink.raw else InkPage.read(raw, previous=ink)
                if decoded.warning and not ink.warning:
                    raise ValueError('This edit exceeds the supported ink scene: ' + decoded.warning)
                normalized.append((page, decoded))
            digest = sha256(raw).hexdigest()
            target = directory / (digest + '.rm')
            if not target.exists():
                atomic_write_bytes(target, raw)
            pages.append(dict(id=page.id, record=page.record, template=page.template, ink=digest))
        # Copied page sidecars and unknown document members remain in a bounded base.
        # Update it for structural changes or an explicit source replacement,
        # never per pen sample. Replacing a clean source must not mark its
        # structure dirty: its original archive members remain authoritative.
        if not preserve_active_ink:
            for page, ink in normalized:
                page.ink = ink
        structural = notebook.structure_dirty
        baseline = None
        if structural or source_bytes is not None:
            base = source_bytes if source_bytes is not None else notebook.to_bytes()
            baseline = source_baseline if source_bytes is not None else Notebook.read(base, max_bytes=self.max_bytes)
            digest = sha256(base).hexdigest()
            target = directory / (digest + '.rmdoc')
            if not target.exists():
                atomic_write_bytes(target, base)
            base_name = target.name
        else:
            base_name = json.loads(previous).get('base', 'base.rmdoc') if previous is not None else 'base.rmdoc'
        # A fresh identity prevents an old journal replaying if Undo makes
        # the notebook equal to an earlier checkpoint.
        state = dict(schema=1, name=notebook.name, base=base_name, pages=pages, publication=uuid4().hex)
        expected = json.dumps(state, ensure_ascii=False, allow_nan=False).encode('utf-8')
        publication_error = None
        try:
            atomic_write_json(manifest, state, durable_directory=True)
        except Exception as error:
            try:
                current = manifest.read_bytes() if manifest.exists() else None
            except OSError as read_error:
                raise RecoveryIncomplete('Notebook recovery could not be verified. Keep this draft open and use Save As.',
                                         published=None) from read_error
            if current != expected:
                if current == previous:
                    raise
                raise RecoveryIncomplete('Notebook recovery changed during publication. Keep this draft open and use Save As.',
                                         published=None) from error
            publication_error = error
        self.revisions.setdefault(notebook, {})[key] = (sha256(expected).hexdigest(), 0)
        if structural:
            notebook.members, notebook.content = baseline.members, baseline.content
        notebook.structure_dirty = False
        if publication_error is not None:
            # The previous manifest may still be durable. Retain its immutable
            # objects until a later checkpoint confirms directory publication.
            raise RecoveryIncomplete('Notebook recovery was published, but durability confirmation failed. '
                                     'The edit remains in this draft.', published=True) from publication_error
        # Keep only objects referenced by the published manifest. In-memory undo
        # owns its page objects and recreates their blobs if later restored.
        retained = {p['ink'] + '.rm' for p in pages} | {base_name, 'base.rmdoc', 'state.json'}
        try:
            for path in directory.iterdir():
                if path.name not in retained and (path.suffix in ('.rm', '.rmdoc') or STROKE_RECORD.fullmatch(path.name)):
                    path.unlink(missing_ok=True)
        except OSError:
            pass  # Published recovery remains valid; retry pruning on the next save.

    @locked_draft
    def open(self, key):
        directory = self.root / identifier(key)
        manifest = (directory / 'state.json').read_bytes()
        state = json.loads(manifest)
        base = state.get('base', 'base.rmdoc')
        if Path(base).name != base or not base.endswith('.rmdoc'):
            raise ValueError('Invalid notebook recovery base.')
        with (directory / base).open('rb') as stream:
            notebook = Notebook.read(read_up_to(stream, self.max_bytes + 1), max_bytes=self.max_bytes)
        pages = []
        for item in state['pages']:
            digest = item['ink']
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Invalid notebook recovery page.')
            raw = (directory / (digest + '.rm')).read_bytes()
            if sha256(raw).hexdigest() != digest:
                raise ValueError('Notebook recovery page failed its integrity check.')
            page = Page(identifier(item['id']), item['record'], item['template'])
            if raw != notebook.unloaded_ink(page):
                page.recovered_ink = raw
            pages.append(page)
        if not pages:
            raise ValueError('Invalid notebook recovery page count.')
        notebook.pages = pages
        revision, entries = journal(directory, manifest)
        if entries:
            positions = {page.id: index for index, page in enumerate(pages)}
            for entry in entries:
                replay_stroke(notebook, positions, entry)
        self.revisions.setdefault(notebook, {})[key] = revision
        notebook.structure_dirty = True
        notebook.metadata['visibleName'] = state['name']
        notebook.metadata_dirty = True
        return notebook
