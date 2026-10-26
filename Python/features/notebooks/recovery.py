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


class Repository:
    @serialize_mutation
    def delete(self, key):
        """Remove this ordinary recovery identity after source deletion."""
        import shutil
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
    def save(self, key, notebook):
        directory = self.root / identifier(key)
        manifest = directory / 'state.json'
        revision = sha256(manifest.read_bytes()).hexdigest() if manifest.exists() else None
        if self.revisions.get(notebook, {}).get(key) != revision:
            raise ValueError('This notebook changed in another window. Reopen its saved copy before editing.')
        # Each immutable page snapshot precedes publication of its manifest.
        # Interrupted saves leave the previous manifest and pages recoverable.
        pages = []
        normalized = []
        for index, page in enumerate(notebook.pages):
            ink = notebook.page(index)
            raw = ink.to_bytes()
            decoded = ink if raw is ink.raw else InkPage.read(raw, previous=ink)
            if decoded.warning and not ink.warning:
                raise ValueError('This edit exceeds the supported ink scene: ' + decoded.warning)
            digest = sha256(raw).hexdigest()
            target = directory / (digest + '.rm')
            if not target.exists():
                atomic_write_bytes(target, raw)
            normalized.append(decoded)
            pages.append(dict(id=page.id, record=page.record, template=page.template, ink=digest))
        # Copied page sidecars and unknown document members remain in a bounded base.
        # This archive is updated only by structural changes, never per pen sample.
        for page, ink in zip(notebook.pages, normalized):
            page.ink = ink
        structural = notebook.structure_dirty
        if structural:
            base = notebook.to_bytes()
            digest = sha256(base).hexdigest()
            target = directory / (digest + '.rmdoc')
            if not target.exists():
                atomic_write_bytes(target, base)
            base_name = target.name
        else:
            previous = directory / 'state.json'
            base_name = json.loads(previous.read_text()).get('base', 'base.rmdoc') if previous.exists() else 'base.rmdoc'
        atomic_write_json(directory / 'state.json', dict(schema=1, name=notebook.name,
            base=base_name, pages=pages), durable_directory=True)
        self.revisions.setdefault(notebook, {})[key] = sha256((directory / 'state.json').read_bytes()).hexdigest()
        if structural:
            baseline = Notebook.read(base)
            notebook.members, notebook.content = baseline.members, baseline.content
        notebook.structure_dirty = False
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
            pages.append(Page(identifier(item['id']), item['record'], item['template'], InkPage.read(raw)))
        if not 1 <= len(pages) <= 1000:
            raise ValueError('Invalid notebook recovery page count.')
        self.revisions.setdefault(notebook, {})[key] = sha256((directory / 'state.json').read_bytes()).hexdigest()
        notebook.pages = pages
        notebook.structure_dirty = True
        notebook.metadata['visibleName'] = state['name']
        notebook.metadata_dirty = True
        return notebook
