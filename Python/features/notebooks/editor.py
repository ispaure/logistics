"""Reversible notebook commands independent of hosts and storage backends."""
from collections import OrderedDict
from copy import copy, deepcopy

from .protocol import validate_action, RecoveryIncomplete
from .ink import WIDTH, HEIGHT, TOOLS, COLORS
from .brushes import BRUSHES, EXPANDED_BRUSHES, EXPANDED_INK_SCALE, PALETTE, HIGHLIGHTS, HIGHLIGHT_IDS, NATIVE_HIGHLIGHTS, SHADERS, WIDTHS


PDF_BACKGROUND_BYTES = 12 * 1024 * 1024
PDF_BACKGROUND_PAGES = 3


class Editor:
    def __init__(self, notebook, checkpoint=lambda book: None):
        self.notebook = notebook
        self.checkpoint = checkpoint
        self.checkpoint_unconfirmed = False
        self.index = 0
        self.brush_colors = {}
        self.eraser_kind = 'partial'
        self.undo = []
        self.redo = []
        self._selection_clipboard = []
        self._selection_ids = []
        self._backgrounds = OrderedDict()
        self._unlocked_pdf = None
        self._locked_pdf = None  # Encrypted source bytes only; never a password.
        self._pdf_geometry = (None, None)
        self._pdf_links = (None, None, [])

    def background_key(self, page_index):
        book = self.notebook
        if book.content.get('fileType') != 'pdf' or not 0 <= page_index < len(book.pages):
            return None
        index = book.pages[page_index].record.get('redir', {}).get('value', -1)
        data = self.pdf_data() if index >= 0 else None
        return (data, index) if data is not None else None

    @staticmethod
    def render_background(key):
        from base64 import b64encode
        from features.pdf.document import PDFDocument

        data, index = key
        pdf = PDFDocument(data)
        try:
            return 'data:image/png;base64,' + b64encode(pdf.page(index)).decode('ascii')
        finally:
            pdf.close()

    def cached_background(self, key):
        return self._backgrounds.get(key)

    def cache_background(self, key, image, *, keep=None):
        if keep is not None and key != keep:
            # Lookahead cannot evict the page already being displayed.
            if len(image) + len(self._backgrounds.get(keep, '')) > PDF_BACKGROUND_BYTES:
                return
        self._backgrounds[key] = image
        self._backgrounds.move_to_end(key)
        while len(self._backgrounds) > 1 and (len(self._backgrounds) > PDF_BACKGROUND_PAGES or
                sum(map(len, self._backgrounds.values())) > PDF_BACKGROUND_BYTES):
            oldest = next(candidate for candidate in self._backgrounds if candidate not in (keep, key))
            del self._backgrounds[oldest]

    def background(self):
        key = self.background_key(self.index)
        if key is None:
            return None
        image = self.cached_background(key)
        if image is None:
            image = self.render_background(key)
            self.cache_background(key, image)
        else:
            self._backgrounds.move_to_end(key)
        return image

    def expanded_pdf_layout(self):
        content = self.notebook.content
        return content.get('fileType') == 'pdf' and content.get('formatVersion') == 2 and content.get('zoomMode') == 'fitToHeight'

    def expanded_ink(self):
        return self.expanded_pdf_layout() and self.pdf_bounds() is not None

    def eraser_scale(self):
        return EXPANDED_INK_SCALE if self.expanded_ink() else 1

    def pdf_bounds(self, page_index=None, *, reader=None):
        """Place physical-size backgrounds in the original native ink units."""
        book = self.notebook
        if book.content.get('fileType') != 'pdf':
            return None
        page_index = self.index if page_index is None else page_index
        index = book.pages[page_index].record.get('redir', {}).get('value', -1)
        if index < 0:
            return None
        data = self.pdf_data()
        if data is None:
            return None
        key = (data, index)
        if self._pdf_geometry[0] != key:
            import math
            from .remarkable_export import PDF_SCALE
            if reader is None:
                from io import BytesIO
                from pypdf import PdfReader
                reader = PdfReader(BytesIO(data))
            marked_export = reader.metadata and reader.metadata.get('/LogisticsNativeUnits') == '226'
            if not marked_export and not self.expanded_pdf_layout():
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

    def pdf_data(self, password=None):
        """Decrypt solely for rendering; retain encrypted source bytes on Save."""
        from io import BytesIO
        from pypdf import PdfReader, PdfWriter
        if self.notebook.content.get('fileType') != 'pdf':
            self._locked_pdf = None
            return None
        data = self.notebook.members[self.notebook.id + '.pdf']
        if self._locked_pdf is not None and self._locked_pdf != data:
            self._locked_pdf = None
        if password is None and self._locked_pdf is not None:
            return None
        # Structural recovery re-reads unchanged members into fresh byte objects.
        # Keep the session unlock only for identical encrypted PDF contents.
        if self._unlocked_pdf and self._unlocked_pdf[0] == data:
            return self._unlocked_pdf[1]
        from .pdf_crypto import enable_aes
        enable_aes()
        reader = PdfReader(BytesIO(data))
        if not reader.is_encrypted:
            self._locked_pdf = None
            self._unlocked_pdf = (data, data)
            return data
        if not reader.decrypt(password if password is not None else ''):
            if password is not None:
                raise ValueError('Incorrect PDF password. Try again.')
            self._locked_pdf = data
            return None
        self._locked_pdf = None
        writer = PdfWriter(clone_from=reader)
        output = BytesIO()
        writer.write(output)
        self._unlocked_pdf = (data, output.getvalue())
        return self._unlocked_pdf[1]

    def page_links(self):
        from features.pdf.links import safe_page_links
        data = self.pdf_data()
        if data is None:
            return []
        pages = self.notebook.pages
        source = pages[self.index].record.get('redir', {}).get('value', -1)
        if source < 0:
            return []
        targets = {}
        for i, page in enumerate(pages):
            targets.setdefault(page.record.get('redir', {}).get('value', -1), i)
        if self._pdf_links[0] is not data or self._pdf_links[1] != source:
            self._pdf_links = (data, source, safe_page_links(data, source))
        return [dict(rect=link['rect'], index=targets[link['index']])
                for link in self._pdf_links[2] if link['index'] in targets]

    def page_height(self):
        bounds = self.pdf_bounds()
        return max(HEIGHT, bounds['height']) if bounds else HEIGHT

    def canvas_left(self):
        # The notebook model uses the legacy center at WIDTH / 2 even when
        # imported ink extends to negative x or past WIDTH. The canvas starts
        # at its visible left edge; the archive keeps the original coordinates.
        bounds = self.pdf_bounds()
        return min(0, bounds['x']) if bounds else 0

    def canvas_stroke(self, stroke):
        payload = stroke.payload()
        left = self.canvas_left()
        if left:
            payload['points'] = [[x - left, y, pressure, width] for x, y, pressure, width in payload['points']]
        return payload

    @staticmethod
    def native_action(action, left):
        if not left:
            return action
        op = action['op']
        if op == 'erase' and 'points' in action:
            return dict(action, points=[[x + left, y, pressure] for x, y, pressure in action['points']])
        if op in ('paste-image', 'image-transform'):
            from .images import validate_corners
            validate_corners(action['corners'])
            return dict(action, corners=[[x + left, y] for x, y in action['corners']])
        if op == 'transform':
            return dict(action, cx=action.get('cx', 0) + left)
        return action

    def page_previews(self, start):
        from .previews import page_previews
        data = self.pdf_data()
        if data is None:
            return page_previews(self.notebook, start)
        from base64 import b64encode
        from io import BytesIO
        from pypdf import PdfReader
        from features.pdf.document import PDFDocument
        from .previews import THUMBNAIL_EDGE

        reader = PdfReader(BytesIO(data))
        pdf = PDFDocument(data)
        try:
            with pdf.open() as renderer:
                def artwork(index):
                    if 0 <= index < renderer.count:
                        try:
                            png = renderer.render(index, edge=THUMBNAIL_EDGE)
                        except (OSError, ValueError):
                            return None
                        return 'data:image/png;base64,' + b64encode(png).decode('ascii')

                return page_previews(self.notebook, start, pdf_artwork=artwork,
                                     pdf_bounds=lambda index: self.pdf_bounds(index, reader=reader))
        finally:
            pdf.close()

    def snapshot(self):
        book = self.notebook
        pages = []
        for page in book.pages:
            item = copy(page)
            item.record = deepcopy(page.record)
            if item.ink is not None:
                item.ink = copy(item.ink)
                item.ink.strokes = list(item.ink.strokes)
                item.ink.images = list(item.ink.images)
                item.ink.image_resources = list(item.ink.image_resources)
            pages.append(item)
        return pages, dict(book.members), deepcopy(book.metadata), self.index

    def restore(self, snapshot):
        book = self.notebook
        pages, members, metadata, index = snapshot
        # Ink-only history can reuse the already published archive and page blobs.
        structure_changed = (len(book.pages) != len(pages) or book.members != members
                             or any((a.id, a.record, a.template) != (b.id, b.record, b.template)
                                    for a, b in zip(book.pages, pages)))
        book.pages, book.members, book.metadata, self.index = pages, members, metadata, index
        book.structure_dirty |= structure_changed
        book.metadata_dirty = True

    def apply(self, action):
        op = validate_action(action)
        book = self.notebook
        self._selection_ids = []
        if op == 'copy-strokes':
            self._selection_clipboard = self.copy_selection(action['ids'])
            self._selection_ids = [item.id for item, _ in self._selection_clipboard]
            return
        if op == 'unlock-pdf':
            self.pdf_data(action['password'])
            return
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
                    self.checkpoint_unconfirmed = False
                except Exception as error:
                    if isinstance(error, RecoveryIncomplete):
                        self.checkpoint_unconfirmed = error.published is not True
                        source.pop()
                        target.append(previous)
                        raise
                    self.restore(previous)
                    raise
                source.pop()
                target.append(previous)
            return
        selection_ids = []
        pasted_indexes = []
        clipboard = self._selection_clipboard
        try:
            left = self.canvas_left()
            right = WIDTH - left
            height = self.page_height()
            action = self.native_action(action, left)
            ink = book.page(self.index)
            if op == 'cut-strokes':
                if ink.warning:
                    raise ValueError(ink.warning)
                clipboard = self.copy_selection(action['ids'])
                self.remove_selection(ink, {item.id for item, _ in clipboard})
            elif op == 'paste-strokes':
                from uuid import uuid4
                from .images import add_picture
                from .ink import MAX_PAGE_POINTS
                if ink.warning:
                    raise ValueError(ink.warning)
                visible = [key for key, _, shown in ink.layers if shown]
                if not visible or not clipboard:
                    raise ValueError('Copy a selection and choose a visible layer first.')
                point_count = sum(len(s.points) for s in ink.strokes)
                point_count += sum(len(item.points) for item, data in clipboard if data is None)
                if point_count > MAX_PAGE_POINTS:
                    raise ValueError('Too many points on this page.')
                for item, data in clipboard:
                    if data is not None:
                        add_picture(book, self.index, data, visible[-1], item.corners)
                        pasted_indexes.append(('images', len(ink.images) - 1))
                        continue
                    stroke = deepcopy(item)
                    if any(not left <= x <= right or not 0 <= y <= height for x, y, _, _ in stroke.points):
                        raise ValueError('Keep pasted strokes inside the page.')
                    stroke.id, stroke.layer = uuid4().hex, visible[-1]
                    ink.strokes.append(stroke)
                    ink.order = [*ink.order, stroke.id]
                    pasted_indexes.append(('strokes', len(ink.strokes) - 1))
                if action.get('single_use') is True:
                    clipboard = []
                if ink.images:
                    ink.ordering_dirty = True
            elif op == 'stroke':
                ink.add(action['points'], action.get('tool', 17), action.get('color', 0),
                        action.get('width', 2), action.get('layer'), page_height=height,
                        x_bounds=(left, right), x_offset=left,
                        expanded=self.expanded_ink())
            elif op == 'paste-image':
                from .images import paste
                paste(book, self.index, action)
            elif op == 'image-transform':
                from .images import validate_corners
                validate_corners(action['corners'])
                if ink.warning:
                    raise ValueError(ink.warning)
                shown = {key for key, _, visible in ink.layers if visible}
                if not any(p.id == action['id'] and p.layer in shown for p in ink.images):
                    raise ValueError('Select a visible image.')
                ink.images = [type(p)(p.id, p.layer, p.resource, deepcopy(action['corners']))
                              if p.id == action['id'] else p for p in ink.images]
            elif op == 'arrange-image':
                if ink.warning:
                    raise ValueError(ink.warning)
                picture = next((p for p in ink.images if p.id == action['id']), None)
                shown = {key for key, _, visible in ink.layers if visible}
                if picture is None or picture.layer not in shown:
                    raise ValueError('Select a visible image.')
                members = {s.id for s in [*ink.strokes, *ink.images] if s.layer == picture.layer}
                order = [key for key in ink.order if key in members]
                order += [s.id for s in [*ink.strokes, *ink.images] if s.id in members and s.id not in order]
                old = order.index(picture.id)
                positions = {'front': len(order)-1, 'back': 0, 'forward': min(old+1, len(order)-1), 'backward': max(0, old-1)}
                if action['direction'] not in positions:
                    raise ValueError('Unknown image arrangement.')
                order.insert(positions[action['direction']], order.pop(old))
                other = [key for key in ink.order if key not in members]
                ink.order = [*other, *order]
                ink.ordering_dirty = True
            elif op == 'delete-image':
                if ink.warning:
                    raise ValueError(ink.warning)
                ink.images = [p for p in ink.images if p.id != action['id']]
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
                from .images import validate_corners
                self.selected_items(ink, action['ids'])
                selected_ids = set(action['ids'])
                dx, dy = action['dx'], action['dy']
                scale, angle = action.get('scale', 1), action.get('angle', 0)
                cx, cy = action.get('cx', 0), action.get('cy', 0)
                cosine, sine = math.cos(angle), math.sin(angle)
                def transform(x, y):
                    return [cx + scale * ((x-cx)*cosine - (y-cy)*sine) + dx,
                            cy + scale * ((x-cx)*sine + (y-cy)*cosine) + dy]

                selection_ids = action['ids']
                for index, stroke in enumerate(ink.strokes):
                    if stroke.id in selected_ids and (dx, dy, scale, angle) != (0, 0, 1, 0):
                        moved = deepcopy(stroke)
                        moved.points = [[*transform(x, y), p, w * scale] for x, y, p, w in moved.points]
                        moved.scale *= scale
                        if not math.isfinite(moved.scale) or moved.scale <= 0:
                            raise ValueError('Invalid native stroke scale.')
                        if any(not left <= x <= right or not 0 <= y <= height
                               or not math.isfinite(w) or not 0 <= w <= 65535 / 4
                               for x, y, p, w in moved.points):
                            raise ValueError('Keep transformed strokes inside the page and supported width range.')
                        ink.strokes[index] = moved
                for index, picture in enumerate(ink.images):
                    if picture.id in selected_ids and (dx, dy, scale, angle) != (0, 0, 1, 0):
                        corners = [transform(x, y) for x, y in picture.corners]
                        validate_corners(corners)
                        ink.images[index] = type(picture)(picture.id, picture.layer, picture.resource, corners)
            elif op == 'erase':
                old_ids = {s.id for s in ink.strokes}
                if ink.warning:
                    raise ValueError(ink.warning)
                if 'points' in action:
                    if any(not left <= x <= right or y > height for x, y, _ in action['points']):
                        raise ValueError('Eraser is outside the page.')
                    from .eraser import erase
                    ink.strokes = erase(ink.strokes, ink.layers, action['points'],
                                        action['radius'] * self.eraser_scale(), action.get('kind') == 'whole')
                else:
                    ids = set(action['ids'])
                    shown = {key for key, _, visible in ink.layers if visible}
                    ids.difference_update(p.id for p in ink.images if p.layer not in shown)
                    self.remove_selection(ink, ids)
                fragments, owner = {}, None
                for stroke in ink.strokes:
                    if stroke.id in old_ids:
                        owner = stroke.id
                    fragments.setdefault(owner, []).append(stroke.id)
                ink.order = [part for key in ink.order for part in
                             (fragments.get(key, []) if key in old_ids else [key])]
                if ink.images:
                    ink.ordering_dirty = True
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
            self.checkpoint_unconfirmed = False
        except Exception as error:
            if not isinstance(error, RecoveryIncomplete):
                self.restore(previous)
                raise
            self.checkpoint_unconfirmed = error.published is not True
            checkpoint_error = error
        else:
            checkpoint_error = None
        self._selection_clipboard = clipboard
        if pasted_indexes:
            ink = book.page(self.index)
            selection_ids = [getattr(ink, group)[i].id for group, i in pasted_indexes]
        self._selection_ids = selection_ids
        self.undo.append(previous)
        del self.undo[:-50]
        self.redo.clear()
        if checkpoint_error is not None:
            raise checkpoint_error

    @staticmethod
    def selected_items(ink, ids):
        shown = {key for key, _, visible in ink.layers if visible}
        wanted = set(ids)
        chosen = [s for s in [*ink.strokes, *ink.images] if s.id in wanted and s.layer in shown]
        if not wanted or {s.id for s in chosen} != wanted:
            raise ValueError('Select visible strokes or images first.')
        # Follow scene order when copied ink overlaps images or other strokes.
        order = {key: i for i, key in enumerate(ink.order)}
        return sorted(chosen, key=lambda s: order.get(s.id, len(order)))

    def copy_selection(self, ids):
        from .images import Picture, picture_assets
        ink = self.notebook.page(self.index)
        read = picture_assets(self.notebook, self.index)
        return [(deepcopy(item), read(item) if isinstance(item, Picture) else None)
                for item in self.selected_items(ink, ids)]

    @staticmethod
    def remove_selection(ink, ids):
        ink.ordering_dirty |= bool(ink.images)
        ink.strokes = [s for s in ink.strokes if s.id not in ids]
        ink.images = [p for p in ink.images if p.id not in ids]
        ink.order = [key for key in ink.order if key not in ids]

    def state(self):
        from .templates import CATALOG, FORM_TEMPLATES, settings, background, view_bounds, template_name, available, TEMPLATE_NOTICE, description
        ink = self.notebook.page(self.index)
        page = self.notebook.pages[self.index]
        paper = settings(self.notebook, page)
        pdf = self.notebook.content.get('fileType') == 'pdf'
        mapped_pdf = pdf and page.record.get('redir', {}).get('value', -1) >= 0
        template_available = available(self.notebook, page)
        template_description = ('This document has fixed PDF backgrounds. Notebook template changes are unavailable.'
            if pdf else description(page.template, artwork_available=template_available))
        from .images import image_payloads
        locked = pdf and self.pdf_data() is None
        paper_bounds = self.pdf_bounds()
        expanded = self.expanded_pdf_layout() and paper_bounds is not None
        move_paper = view_bounds([], True)
        compact_paper = move_paper
        if expanded:
            from .remarkable_export import PDF_SCALE
            compact_paper = dict(width=954 / PDF_SCALE, height=1696 / PDF_SCALE)
        left = self.canvas_left()
        images = image_payloads(self.notebook, self.index)
        if left:
            paper_bounds = dict(paper_bounds, x=paper_bounds['x'] - left)
            for image in images:
                image['corners'] = [[x - left, y] for x, y in image['corners']]
        return dict(stroke_clipboard=bool(self._selection_clipboard), selection_ids=self._selection_ids, links=self.page_links() if pdf and not locked else [], password_required=locked, images=images,
                    scene_order=ink.order, page_id=page.id, name=self.notebook.name, index=self.index, count=len(self.notebook.pages),
                    width=WIDTH - 2 * left, height=self.page_height(), pdf_paper=paper_bounds, tools=TOOLS, colors=COLORS,
                    brushes=EXPANDED_BRUSHES if expanded else BRUSHES, palette=PALETTE, highlights=HIGHLIGHTS,
                    highlight_ids=HIGHLIGHT_IDS, native_highlights=NATIVE_HIGHLIGHTS,
                    shaders=SHADERS, widths=WIDTHS, eraser_scale=self.eraser_scale(),
                    strokes=[self.canvas_stroke(s) for s in ink.strokes], layers=ink.layers,
                    warning=ink.warning, template=page.template,
                    template_name=template_name(page.template),
                    templates=CATALOG, template_formats=sorted(FORM_TEMPLATES), template_notice=TEMPLATE_NOTICE, template_description=template_description,
                    template_settings=paper, template_editable=not pdf,
                    template_available=template_available,
                    move_paper=move_paper, compact_paper=compact_paper,
                    background=self.background() if mapped_pdf else background(page.template, paper['format']) if paper['visible'] and template_available else None,
                    undo=bool(self.undo), redo=bool(self.redo))
