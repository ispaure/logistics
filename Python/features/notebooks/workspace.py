"""Private notebook copies, atomic per-page recovery and reversible editing."""
from copy import copy, deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import serialize_mutation
from commonUtils.persistence.atomic import atomic_write_bytes
from .notebook import Notebook, Page, MAX_ARCHIVE, identifier
from .ink import InkPage, WIDTH, HEIGHT, TOOLS, COLORS


class Repository:
    def __init__(self, root):
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
        self.save(key, notebook)
        return key

    @serialize_mutation
    def save(self, key, notebook):
        directory = self.root / identifier(key)
        manifest = directory / 'state.json'
        revision = sha256(manifest.read_bytes()).hexdigest() if manifest.exists() else None
        if getattr(notebook, '_recovery_revision', None) != revision:
            raise ValueError('This notebook changed in another window. Reopen its saved copy before editing.')
        # Each immutable page snapshot precedes publication of its manifest.
        # Interrupted saves leave the previous manifest and pages recoverable.
        pages = []
        normalized = []
        for index, page in enumerate(notebook.pages):
            ink = notebook.page(index)
            raw = ink.to_bytes()
            decoded = InkPage.read(raw)
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
        notebook._recovery_revision = sha256((directory / 'state.json').read_bytes()).hexdigest()
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
        notebook._recovery_revision = sha256((directory / 'state.json').read_bytes()).hexdigest()
        notebook.pages = pages
        notebook.structure_dirty = True
        notebook.metadata['visibleName'] = state['name']
        notebook.metadata_dirty = True
        return notebook


class Editor:
    def __init__(self, notebook, checkpoint=lambda book: None):
        self.notebook = notebook
        self.checkpoint = checkpoint
        self.index = 0
        self.undo = []
        self.redo = []

    def snapshot(self):
        book = self.notebook
        pages = []
        for page in book.pages:
            item = copy(page)
            if item.ink is not None:
                item.ink = copy(item.ink)
                item.ink.strokes = list(item.ink.strokes)
            pages.append(item)
        return pages, dict(book.members), deepcopy(book.metadata), self.index

    def restore(self, snapshot):
        book = self.notebook
        book.pages, book.members, book.metadata, self.index = snapshot
        book.structure_dirty = book.metadata_dirty = True

    def apply(self, action):
        op = action['op']
        book = self.notebook
        if op == 'page':
            index = action['index']
            if type(index) is not int or not 0 <= index < len(book.pages):
                raise ValueError('Invalid page number.')
            self.index = index
            return
        previous = self.snapshot()
        if op in ('undo', 'redo'):
            source, target = (self.undo, self.redo) if op == 'undo' else (self.redo, self.undo)
            if source:
                self.restore(source[-1])
                try:
                    self.checkpoint(book)
                except Exception:
                    self.restore(previous)
                    raise
                source.pop()
                target.append(previous)
            return
        try:
            ink = book.page(self.index)
            if op == 'stroke':
                ink.add(action['points'], action.get('tool', 17), action.get('color', 0),
                        action.get('width', 2), action.get('layer'))
            elif op == 'add-layer':
                ink.add_layer(action['name'])
            elif op == 'layer-visible':
                if ink.warning:
                    raise ValueError(ink.warning)
                ink.layers = [(key, name, bool(action['visible']) if key == action['layer'] else shown)
                              for key, name, shown in ink.layers]
            elif op == 'transform':
                if ink.warning:
                    raise ValueError(ink.warning)
                import math
                dx, dy = action['dx'], action['dy']
                if any(type(v) not in (float, int) or not math.isfinite(v) for v in (dx, dy)):
                    raise ValueError('Invalid stroke movement.')
                for index, stroke in enumerate(ink.strokes):
                    if stroke.id in action['ids']:
                        moved = deepcopy(stroke)
                        moved.points = [[x + dx, y + dy, p, w] for x, y, p, w in stroke.points]
                        if any(not 0 <= x <= WIDTH or not 0 <= y <= HEIGHT for x, y, p, w in moved.points):
                            raise ValueError('Keep moved strokes inside the page.')
                        ink.strokes[index] = moved
            elif op == 'erase':
                if ink.warning:
                    raise ValueError(ink.warning)
                ids = action['ids']
                if not isinstance(ids, list) or len(ids) > 100_000:
                    raise ValueError('Invalid stroke selection.')
                ink.strokes = [s for s in ink.strokes if s.id not in ids]
            elif op == 'add-page':
                book.add_page(self.index + 1)
                self.index += 1
            elif op == 'duplicate-page':
                book.copy_page(book, self.index, self.index + 1)
                self.index += 1
            elif op == 'delete-page':
                book.delete_page(self.index)
                self.index = min(self.index, len(book.pages) - 1)
            elif op == 'move-page':
                book.move_page(self.index, action['index'])
                self.index = action['index']
            elif op == 'rename':
                name = action['name'].strip()
                if not name or len(name) > 120 or any(ord(c) < 32 or c in '/\\' for c in name):
                    raise ValueError('Choose a notebook name of 1–120 characters without slashes.')
                book.metadata['visibleName'] = name
                book.metadata_dirty = True
            else:
                raise ValueError('Unknown notebook command.')
            self.checkpoint(book)
        except Exception:
            self.restore(previous)
            raise
        self.undo.append(previous)
        del self.undo[:-50]
        self.redo.clear()

    def state(self):
        ink = self.notebook.page(self.index)
        return dict(name=self.notebook.name, index=self.index, count=len(self.notebook.pages),
                    width=WIDTH, height=HEIGHT, tools=TOOLS, colors=COLORS,
                    strokes=[s.payload() for s in ink.strokes], layers=ink.layers,
                    warning=ink.warning, template=self.notebook.pages[self.index].template,
                    undo=bool(self.undo), redo=bool(self.redo))
