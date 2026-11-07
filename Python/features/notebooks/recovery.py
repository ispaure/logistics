"""Atomic per-page recovery, revision guards and immutable notebook snapshots."""
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from weakref import WeakKeyDictionary

from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import serialize_mutation
from commonUtils.persistence.atomic import atomic_write_bytes
from .notebook import Notebook, Page, identifier
from .ink import InkPage
from .protocol import RecoveryIncomplete


class Repository:
    @serialize_mutation
    def delete(self, key, *, expected=None):
        """Remove this ordinary recovery identity after source deletion."""
        import shutil
        if expected is not None:
            manifest = self.root / identifier(key) / 'state.json'
            revision = sha256(manifest.read_bytes()).hexdigest()
            if self.revisions.get(expected, {}).get(key) != revision:
                raise ValueError('This notebook changed in another window. Reopen its draft before discarding.')
        try:
            shutil.rmtree(self.root / identifier(key))
        except FileNotFoundError:
            if (self.root / identifier(key)).exists():
                raise

    def __init__(self, root):
        self.revisions = WeakKeyDictionary()
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

    def create(self, notebook):
        key = uuid4().hex
        directory = self.root / key
        directory.mkdir()
        atomic_write_bytes(directory / 'base.rmdoc', notebook.to_bytes())
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
        manifest = self.root / identifier(key) / 'state.json'
        previous = manifest.read_bytes() if manifest.exists() else None
        revision = sha256(previous).hexdigest() if previous is not None else None
        if self.revisions.get(notebook, {}).get(key) != revision:
            raise ValueError('This notebook changed in another window. Reopen its saved copy before editing.')
        return previous

    @serialize_mutation
    def save(self, key, notebook, *, source_bytes=None):
        directory = self.root / identifier(key)
        manifest = directory / 'state.json'
        previous = self.check_revision(key, notebook)
        # Explicit source adoption preserves the archive exactly, including
        # missing legacy ink members. Loading a blank page may synthesize ink.
        source_baseline = Notebook.read(source_bytes) if source_bytes is not None else None
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
        for page, ink in normalized:
            page.ink = ink
        structural = notebook.structure_dirty
        baseline = None
        if structural or source_bytes is not None:
            base = source_bytes if source_bytes is not None else notebook.to_bytes()
            baseline = source_baseline if source_bytes is not None else Notebook.read(base)
            digest = sha256(base).hexdigest()
            target = directory / (digest + '.rmdoc')
            if not target.exists():
                atomic_write_bytes(target, base)
            base_name = target.name
        else:
            base_name = json.loads(previous).get('base', 'base.rmdoc') if previous is not None else 'base.rmdoc'
        state = dict(schema=1, name=notebook.name, base=base_name, pages=pages)
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
        self.revisions.setdefault(notebook, {})[key] = sha256(expected).hexdigest()
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
                if path.name not in retained and path.suffix in ('.rm', '.rmdoc'):
                    path.unlink(missing_ok=True)
        except OSError:
            pass  # Published recovery remains valid; retry pruning on the next save.

    @serialize_mutation
    def open(self, key):
        directory = self.root / identifier(key)
        state = json.loads((directory / 'state.json').read_text())
        base = state.get('base', 'base.rmdoc')
        if Path(base).name != base or not base.endswith('.rmdoc'):
            raise ValueError('Invalid notebook recovery base.')
        notebook = Notebook.read((directory / base).read_bytes())
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
        self.revisions.setdefault(notebook, {})[key] = sha256((directory / 'state.json').read_bytes()).hexdigest()
        notebook.pages = pages
        notebook.structure_dirty = True
        notebook.metadata['visibleName'] = state['name']
        notebook.metadata_dirty = True
        return notebook
