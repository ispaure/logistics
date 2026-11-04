"""Reversible notebook commands independent of hosts and storage backends."""
from copy import copy, deepcopy

from .protocol import validate_action
from .ink import WIDTH, HEIGHT, TOOLS, COLORS
from .brushes import BRUSHES, PALETTE, HIGHLIGHTS, SHADERS, WIDTHS


class Editor:
    def __init__(self, notebook, checkpoint=lambda book: None):
        self.notebook = notebook
        self.checkpoint = checkpoint
        self.index = 0
        self.undo = []
        self.redo = []
        self._background = (None, None)
        self._pdf_geometry = (None, None)

    def background(self):
        book = self.notebook
        if book.content.get('fileType') != 'pdf':
            return None
        index = book.pages[self.index].record.get('redir', {}).get('value', -1)
        if index < 0:
            return None
        data = book.members[book.id + '.pdf']
        key = (data, index)
        if self._background[0] != key:
            import base64
            from features.pdf.document import PDFDocument
            pdf = PDFDocument(data)
            try:
                image = 'data:image/png;base64,' + base64.b64encode(pdf.page(index)).decode()
            finally:
                pdf.close()
            self._background = (key, image)
        return self._background[1]

    def pdf_bounds(self):
        """Recognize our physical-size exports without changing older PDF views."""
        book = self.notebook
        if book.content.get('fileType') != 'pdf':
            return None
        index = book.pages[self.index].record.get('redir', {}).get('value', -1)
        if index < 0:
            return None
        data = book.members[book.id + '.pdf']
        key = (data, index)
        if self._pdf_geometry[0] != key:
            from io import BytesIO
            import math
            from pypdf import PdfReader
            from .remarkable_export import PDF_SCALE
            reader = PdfReader(BytesIO(data))
            if not reader.metadata or reader.metadata.get('/LogisticsNativeUnits') != '226':
                self._pdf_geometry = (key, None)
                return None
            page = reader.pages[index]
            width = float(page.cropbox.width) * page.user_unit / PDF_SCALE
            height = float(page.cropbox.height) * page.user_unit / PDF_SCALE
            if page.rotation % 180:
                width, height = height, width
            if any(not math.isfinite(v) or not 0 < v <= 1_000_000 for v in (width, height)):
                raise ValueError('Invalid or oversized PDF page dimensions.')
            self._pdf_geometry = (key, dict(x=(WIDTH - width) / 2, y=0, width=width, height=height))
        return self._pdf_geometry[1]

    def page_height(self):
        bounds = self.pdf_bounds()
        return max(HEIGHT, bounds['height']) if bounds else HEIGHT

    def snapshot(self):
        book = self.notebook
        pages = []
        for page in book.pages:
            item = copy(page)
            item.record = deepcopy(page.record)
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
        op = validate_action(action)
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
                        action.get('width', 2), action.get('layer'), page_height=self.page_height())
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
                        if any(not 0 <= x <= WIDTH or not 0 <= y <= self.page_height() for x, y, p, w in moved.points):
                            raise ValueError('Keep moved strokes inside the page.')
                        ink.strokes[index] = moved
            elif op == 'erase':
                if ink.warning:
                    raise ValueError(ink.warning)
                if 'points' in action:
                    if any(p[1] > self.page_height() for p in action['points']):
                        raise ValueError('Eraser is outside the page.')
                    from .eraser import erase
                    ink.strokes = erase(ink.strokes, ink.layers, action['points'],
                                        action['radius'], action.get('kind') == 'whole')
                else:
                    ink.strokes = [s for s in ink.strokes if s.id not in action['ids']]
            elif op == 'add-page':
                from .templates import inherit
                current = book.pages[self.index]
                new_page = book.add_page(self.index + 1)
                self.index += 1
                if book.content.get('fileType') != 'pdf':
                    inherit(book, current, new_page)
            elif op == 'template':
                from .templates import select
                select(book, self.index, action['name'], action['format'], action['visible'])
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
        from .templates import CATALOG, settings, background, view_bounds, template_name, available, TEMPLATE_NOTICE, description
        ink = self.notebook.page(self.index)
        page = self.notebook.pages[self.index]
        paper = settings(self.notebook, page)
        pdf = self.notebook.content.get('fileType') == 'pdf'
        template_available = available(self.notebook, page)
        return dict(name=self.notebook.name, index=self.index, count=len(self.notebook.pages),
                    width=WIDTH, height=self.page_height(), pdf_paper=self.pdf_bounds(), tools=TOOLS, colors=COLORS,
                    brushes=BRUSHES, palette=PALETTE, highlights=HIGHLIGHTS, shaders=SHADERS, widths=WIDTHS,
                    strokes=[s.payload() for s in ink.strokes], layers=ink.layers,
                    warning=ink.warning, template=page.template,
                    template_name=template_name(page.template),
                    templates=CATALOG, template_notice=TEMPLATE_NOTICE, template_description=description(page.template), template_settings=paper, template_editable=not pdf,
                    template_available=template_available,
                    move_paper=view_bounds([], True),
                    background=self.background() if pdf else background(page.template, paper['format']) if paper['visible'] and template_available else None,
                    undo=bool(self.undo), redo=bool(self.redo))
