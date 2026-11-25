"""Native v6 ink adapter. Original frames survive unless their stroke is edited."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass, replace
from io import BytesIO
import math
import struct
from uuid import uuid4

from ._vendor.rmscene import scene_stream as ss, scene_items as si
from ._vendor.rmscene.crdt_sequence import CrdtSequence, CrdtSequenceItem, END_MARKER
from ._vendor.rmscene.tagged_block_common import CrdtId, LwwValue, HEADER_V6
from ._vendor.rmscene.scene_tree import SceneTree
from .images import ImageResources, ImageItem, ImageQuad, Picture
from .brushes import BRUSHES, TOOLS, COLORS, WIDTHS, NATIVE_HIGHLIGHTS, PALETTE, native_color, native_scale, stroke_points

WIDTH, HEIGHT = 1404, 1872
MAX_POINTS = 100_000
MAX_PAGE_POINTS = 1_000_000
MAX_SCENE_FRAMES = 100_000
MAX_HIGHLIGHT_RECTS = 8192
MAX_NOTEBOOK_HEIGHT = HEIGHT * 8


def notebook_ink_height(ink):
    """Fit imported ink below the nominal page while bounding the canvas."""
    from math import ceil
    bottom = max((y + max(0, width) / 2 + 2 for stroke in ink.strokes
                  for _, y, _, width in stroke.points), default=HEIGHT)
    return max(HEIGHT, ceil(min(MAX_NOTEBOOK_HEIGHT, bottom)))


def encode(blocks):
    output = BytesIO()
    ss.write_blocks(output, blocks, options={'version': '3.4'})
    return output.getvalue()


def insertion_links(sequence):
    """Find each item's insertion anchors using only older sequence items."""
    end = END_MARKER
    neighbors = {key: [sequence[i - 1] if i else end,
                       sequence[i + 1] if i + 1 < len(sequence) else end]
                 for i, key in enumerate(sequence)}
    links = {}
    for key in sorted(sequence, key=lambda identity: (identity.part2, identity.part1), reverse=True):
        left, right = neighbors.pop(key)
        links[key] = left, right
        if left != end:
            neighbors[left][1] = right
        if right != end:
            neighbors[right][0] = left
    return links


def write_layer_stack(data, layers):
    """Reorder the live layer links without moving root-level artwork slots."""
    root = CrdtId(0, 1)
    blocks = list(ss.read_blocks(BytesIO(data)))
    root_items = {block.item.item_id: block for block in blocks
                  if isinstance(block, (ss.SceneGroupItemBlock, ImageItem))
                  and block.parent_id == root}
    layer_items = [(block.item.value, key) for key, block in root_items.items()
                   if isinstance(block, ss.SceneGroupItemBlock) and block.item.value is not None]
    groups = dict(layer_items)
    if len(groups) != len(layer_items):
        raise ValueError('This page has repeated native layer references.')
    layer_nodes = [(CrdtId(*map(int, key.split(':'))), visible) for key, _, visible in layers]
    ordered = [groups[node] for node, _ in layer_nodes]
    group_items = set(groups.values())
    deleted = group_items - set(ordered)
    deleted_nodes = {node for node, key in groups.items() if key in deleted}
    active = next((node for node, visible in reversed(layer_nodes) if visible), layer_nodes[-1][0])
    current = CrdtSequence(block.item for block in root_items.values())
    replacement = iter(ordered)
    sequence = [next(replacement) if key in group_items else key for key in current
                if key not in deleted and root_items[key].item.value is not None
                and (key in group_items or not root_items[key].item.deleted_length)]
    links = insertion_links(sequence)
    chunks = []
    for raw, block in zip(frames(data), blocks):
        if isinstance(block, (ss.SceneGroupItemBlock, ImageItem)) and block.parent_id == root:
            item = block.item
            left, right = links.get(item.item_id, (END_MARKER, END_MARKER))
            tombstone = item.item_id in deleted
            if tombstone or (left, right) != (item.left_id, item.right_id):
                block = deepcopy(block)
                block.item = replace(item, left_id=left, right_id=right,
                                     value=None if tombstone else item.value,
                                     deleted_length=1 if tombstone else item.deleted_length)
                raw = encode([block])[len(HEADER_V6):]
        elif isinstance(block, ss.SceneInfo) and block.current_layer.value in deleted_nodes:
            block = deepcopy(block)
            block.current_layer = replace(block.current_layer, value=active)
            raw = encode([block])[len(HEADER_V6):]
        chunks.append(raw)
    return HEADER_V6 + b''.join(chunks)


def frames(data):
    if not data.startswith(HEADER_V6):
        raise ValueError('Only reMarkable v6 ink is editable; this page is preserved unchanged.')
    offset = len(HEADER_V6)
    result = []
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError('Truncated ink frame.')
        size = struct.unpack_from('<I', data, offset)[0] + 8
        if size > len(data) - offset or len(result) >= MAX_SCENE_FRAMES:
            raise ValueError('Invalid or oversized ink scene.')
        result.append(data[offset:offset + size])
        offset += size
    return result


def allocation(blocks):
    """Reuse a registered byte-sized author and advance beyond all native IDs.

    References and tombstones reserve IDs too. Point arrays and group children
    contain no additional serialized IDs (children have their own scene blocks).
    """
    authors = {key for b in blocks if isinstance(b, ss.AuthorIdsBlock)
               for key in b.author_uuids if 0 < key < 256}
    author = max(authors, default=1)
    maximum = 0

    def visit(value):
        nonlocal maximum
        if isinstance(value, CrdtId):
            maximum = max(maximum, value.part2)
        elif is_dataclass(value):
            for member in fields(value):
                if member.name not in ('points', 'children'):
                    visit(getattr(value, member.name))
        elif isinstance(value, dict):
            for key, item in value.items():
                visit(key)
                visit(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                visit(item)

    visit(blocks)
    additions = [] if authors else [ss.AuthorIdsBlock({author: uuid4()})]
    return author, maximum + 1, additions


@dataclass
class Stroke:
    id: str
    layer: str
    tool: int
    color: int
    points: list  # [x, y, pressure, width]; page coordinates, top-left origin
    scale: float = 1.0
    color_rgba: tuple | None = None

    def payload(self):
        return dict(id=self.id, layer=self.layer, tool=self.tool, color=self.color,
                    points=self.points, scale=self.scale, color_rgba=self.color_rgba)


@dataclass(frozen=True)
class TextHighlight:
    id: str
    layer: str
    rectangles: tuple
    rgb: tuple
    opacity: float

    def payload(self, left=0):
        return dict(id=self.id, layer=self.layer, rgb=self.rgb, opacity=self.opacity,
                    rectangles=[[x - left, y, w, h] for x, y, w, h in self.rectangles])


@dataclass
class InkPage:
    raw: bytes = b''
    strokes: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    images: list = field(default_factory=list)
    text_highlights: tuple = ()
    image_resources: list = field(default_factory=list)
    _image_baseline: dict = field(default_factory=dict, repr=False)
    order: list = field(default_factory=list)
    ordering_dirty: bool = False
    warning: str = ''
    _frames: list = field(default_factory=list, repr=False)
    _blocks: list = field(default_factory=list, repr=False)
    _baseline: dict = field(default_factory=dict, repr=False)
    _original_layers: list = field(default_factory=list, repr=False)
    _original_highlights: tuple = field(default_factory=tuple, repr=False)

    @classmethod
    def read(cls, data, *, previous=None):
        page = cls(raw=data)
        try:
            page._frames = frames(data)
            # Checkpoint normalization must not duplicate every old point into
            # each undo snapshot. Native frames are immutable; reuse unchanged
            # frame bytes and parsed blocks, and decode only new/changed frames.
            if previous is None:
                page._blocks = list(ss.read_blocks(BytesIO(data)))
            else:
                reusable = {raw: (raw, block) for raw, block in zip(previous._frames, previous._blocks)}
                fresh = iter(ss.read_blocks(BytesIO(HEADER_V6 + b''.join(
                    raw for raw in page._frames if raw not in reusable))))
                blocks = []
                for index, raw in enumerate(page._frames):
                    if raw in reusable:
                        page._frames[index], block = reusable[raw]
                    else:
                        block = next(fresh)
                    blocks.append(block)
                if next(fresh, None) is not None:
                    raise ValueError('Inconsistent ink frame count.')
                page._blocks = blocks
            if len(page._blocks) != len(page._frames):
                raise ValueError('Inconsistent ink frame count.')
            tree = SceneTree()
            ss.build_tree(tree, page._blocks)
            for block in page._blocks:
                if isinstance(block, ImageItem):
                    tree.add_item(block.item, block.parent_id)
            if any(isinstance(b, ss.UnreadableBlock)
                   or (isinstance(b, ss.RootTextBlock) and any(isinstance(v, str) and v.strip() for v in b.value.items.values()))
                   for b in page._blocks):
                raise ValueError('This page has typed text or unknown objects. Ink editing is disabled; all bytes are preserved.')
            mapping = {id(b.item.value): b for b in page._blocks
                       if isinstance(b, (ss.SceneLineItemBlock, ss.SceneGlyphItemBlock, ImageItem))}
            prior_strokes = {s.id: s for s in previous.strokes} if previous else {}
            prior_blocks = {id(block) for block in previous._blocks} if previous else set()
            total = 0
            highlights, rectangle_count = [], 0
            def visit(group, depth=0):
                nonlocal total, rectangle_count
                if depth > 1:
                    raise ValueError('Nested ink groups are preserved but cannot yet be edited.')
                if group.anchor_id is not None:
                    raise ValueError('Text-anchored ink is preserved but cannot yet be edited.')
                key = f'{group.node_id.part1}:{group.node_id.part2}'
                if group.node_id != tree.root.node_id:
                    page.layers.append((key, group.label.value or 'Layer', group.visible.value))
                for child in group.children.values():
                    if isinstance(child, si.Group):
                        visit(child, depth + 1)
                    elif isinstance(child, ImageQuad):
                        block = mapping[id(child)]
                        if not block.item.deleted_length:
                            identity = f'{block.item.item_id.part1}:{block.item.item_id.part2}'
                            if len(page.images) >= 256:
                                raise ValueError('Too many image objects on this page.')
                            page.images.append(Picture(identity, key, child.resource,
                                [[p[0] + WIDTH / 2, p[1]] for p in child.vertices]))
                            page.order.append(identity)
                    elif isinstance(child, si.GlyphRange):
                        block = mapping[id(child)]
                        if block.item.deleted_length:
                            continue
                        if depth == 0:
                            raise ValueError('Text highlights outside a layer are preserved but cannot yet be edited.')
                        rectangle_count += len(child.rectangles)
                        if rectangle_count > MAX_HIGHLIGHT_RECTS:
                            raise ValueError('Too many text highlight rectangles on this page.')
                        rectangles = tuple((r.x + WIDTH / 2, r.y, r.w, r.h) for r in child.rectangles)
                        if any(not all(math.isfinite(v) and abs(v) <= 1_000_000 for v in rect)
                               or min(rect[2:]) < 0 for rect in rectangles):
                            raise ValueError('Invalid text highlight geometry.')
                        rgba = child.color_rgba or NATIVE_HIGHLIGHTS.get(int(child.color))
                        rgb = rgba[:3] if rgba else tuple(bytes.fromhex(PALETTE.get(int(child.color), '#fbf719')[1:]))
                        opacity = rgba[3] / 255 if rgba and rgba[3] < 255 else .30
                        identity = f'{block.item.item_id.part1}:{block.item.item_id.part2}'
                        highlights.append(TextHighlight(identity, key, rectangles, rgb, opacity))
                        page.order.append(identity)
                    elif isinstance(child, si.Line):
                        if depth == 0:
                            raise ValueError('Ink outside a layer is preserved but cannot yet be edited.')
                        block = mapping[id(child)]
                        if block.item.deleted_length:
                            continue
                        identity = f'{block.item.item_id.part1}:{block.item.item_id.part2}'
                        page.order.append(identity)
                        baseline = previous._baseline.get(identity) if previous and id(block) in prior_blocks else None
                        candidate = prior_strokes.get(identity)
                        if baseline is not None and candidate is not None and candidate.payload() == baseline:
                            total += len(candidate.points)
                            if total > MAX_PAGE_POINTS:
                                raise ValueError('Ink page exceeds the editable point limit.')
                            page.strokes.append(candidate)
                            page._baseline[identity] = baseline
                            continue
                        if child.tool in (si.Pen.ERASER, si.Pen.ERASER_AREA):
                            raise ValueError('Native eraser objects are preserved but cannot yet be rendered or edited.')
                        total += len(child.points)
                        if total > MAX_PAGE_POINTS:
                            raise ValueError('Too many ink points.')
                        if not math.isfinite(child.thickness_scale) or child.thickness_scale <= 0:
                            raise ValueError('Invalid ink thickness scale.')
                        points = [[p.x + WIDTH / 2, p.y, p.pressure / 255, p.width / 4] for p in child.points]
                        if any(not all(math.isfinite(v) for v in p) for p in points):
                            raise ValueError('Non-finite ink coordinates.')
                        page.strokes.append(Stroke(f'{block.item.item_id.part1}:{block.item.item_id.part2}', key,
                            int(child.tool), int(child.color), points, child.thickness_scale, child.color_rgba))
            visit(tree.root)
            page.text_highlights = tuple(highlights)
            page._original_highlights = page.text_highlights
            page._baseline.update({s.id: deepcopy(s.payload()) for s in page.strokes if s.id not in page._baseline})
            page._original_layers = list(page.layers)
            page._image_baseline = {p.id: deepcopy(p.payload()) for p in page.images}
        except Exception as error:
            page.warning = str(error)
            page.images = []
            page.text_highlights = ()
            page.order = []
            page.strokes = []
            page.layers = []
        return page

    @classmethod
    def blank(cls):
        root, layer, end = CrdtId(0, 1), CrdtId(0, 11), CrdtId(0, 0)
        return cls.read(encode([
            ss.AuthorIdsBlock({1: uuid4()}), ss.MigrationInfoBlock(CrdtId(1, 1), True),
            ss.PageInfoBlock(1, 0, 0, 0), ss.SceneTreeBlock(layer, end, True, root),
            ss.TreeNodeBlock(si.Group(root)),
            ss.TreeNodeBlock(si.Group(layer, label=LwwValue(CrdtId(0, 12), 'Layer 1'))),
            ss.SceneGroupItemBlock(root, CrdtSequenceItem(CrdtId(0, 13), end, end, 0, layer)),
        ]))

    def add(self, points, tool=17, color=0, width=2, layer=None, *, page_height=HEIGHT, x_bounds=(0, WIDTH), x_offset=0, expanded=False):
        if self.warning:
            raise ValueError(self.warning)
        if type(width) not in (int, float) or width not in WIDTHS.values():
            raise ValueError('Unsupported brush, color or width.')
        native, rgba = native_color(tool, color)
        if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
            raise ValueError('Invalid stroke length.')
        clean = []
        sizes = (3, 4) if 'tilt_widths' in BRUSHES[tool] else (3,)
        for point in points:
            if (not isinstance(point, (tuple, list)) or len(point) not in sizes
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)):
                raise ValueError('Invalid stroke point.')
            x, y, pressure = point[0], point[1], point[2]
            x += x_offset
            has_tilt = len(point) == 4
            if (not x_bounds[0] <= x <= x_bounds[1] or not 0 <= y <= page_height
                    or not 0 <= pressure <= 1 or (has_tilt and not 0 <= point[3] <= 1)):
                raise ValueError('Stroke is outside the page.')
            clean.append([x, y, pressure, point[3]] if has_tilt else [x, y, pressure])
        clean = stroke_points(clean, tool, int(width), expanded=expanded)
        from .sampling import simplify_stroke
        clean = simplify_stroke(clean, tool, native_x_origin=WIDTH / 2)
        visible = [key for key, name, shown in self.layers if shown]
        layer = layer or (visible[-1] if visible else None)
        if layer not in visible:
            raise ValueError('Choose a visible ink layer.')
        stroke = Stroke(uuid4().hex, layer, tool, native, clean, native_scale(tool, width, expanded=expanded), rgba)
        self.strokes.append(stroke)
        self.order = [*self.order, stroke.id]
        return stroke

    def add_layer(self, name):
        if self.warning:
            raise ValueError(self.warning)
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or len(self.layers) >= 32:
            raise ValueError('Choose a layer name of 1–80 characters; at most 32 layers are supported.')
        raw = self.to_bytes()
        page = InkPage.read(raw)
        author, first, extra = allocation(page._blocks)
        node, item, end, root = CrdtId(author, first), CrdtId(author, first + 1), CrdtId(0, 0), CrdtId(0, 1)
        tree = SceneTree()
        ss.build_tree(tree, page._blocks)
        order = tree.root.children.keys()
        extra += [ss.SceneTreeBlock(node, end, True, root),
                 ss.TreeNodeBlock(si.Group(node, label=LwwValue(CrdtId(author, first + 2), name.strip()))),
                 ss.SceneGroupItemBlock(root, CrdtSequenceItem(item, order[-1] if order else end, end, 0, node))]
        updated = InkPage.read(raw + encode(extra)[len(HEADER_V6):])
        self.__dict__.update(updated.__dict__)

    def add_text_highlight(self, text, rectangles, color, layer):
        if self.warning:
            raise ValueError(self.warning)
        if layer not in {key for key, _, shown in self.layers if shown}:
            raise ValueError('Choose a visible ink layer.')
        raw = self.to_bytes()
        page = InkPage.read(raw, previous=self)
        author, first, additions = allocation(page._blocks)
        parent = CrdtId(*map(int, layer.split(':')))
        ids = {item.id for item in (*page.strokes, *page.images, *page.text_highlights) if item.layer == layer}
        tail = next((CrdtId(*map(int, key.split(':'))) for key in reversed(page.order) if key in ids), END_MARKER)
        native, rgba = native_color(18, color)
        glyph = si.GlyphRange(None, len(text), text, si.PenColor(native),
                              [si.Rectangle(x - WIDTH / 2, y, w, h) for x, y, w, h in rectangles], rgba)
        additions.append(ss.SceneGlyphItemBlock(parent,
            CrdtSequenceItem(CrdtId(author, first), tail, END_MARKER, 0, glyph)))
        updated = InkPage.read(raw + encode(additions)[len(HEADER_V6):], previous=page)
        if updated.warning:
            raise ValueError(updated.warning)
        self.__dict__.update(updated.__dict__)

    def move_layer(self, key, target, *, after):
        if self.warning:
            raise ValueError(self.warning)
        if key == target or not {key, target}.issubset(row[0] for row in self.layers):
            raise ValueError('Choose two different layers on the current page.')
        moved = next(row for row in self.layers if row[0] == key)
        layers = [row for row in self.layers if row[0] != key]
        index = next(i for i, row in enumerate(layers) if row[0] == target)
        layers.insert(index + int(after), moved)
        self.layers = layers

    def delete_layer(self, key):
        if self.warning:
            raise ValueError(self.warning)
        remaining = [row for row in self.layers if row[0] != key]
        if len(remaining) == len(self.layers) or not remaining:
            raise ValueError('Keep at least one layer on the page.')
        removed = {item.id for item in (*self.strokes, *self.images, *self.text_highlights) if item.layer == key}
        self.layers = remaining
        self.strokes = [stroke for stroke in self.strokes if stroke.layer != key]
        self.images = [image for image in self.images if image.layer != key]
        self.text_highlights = tuple(item for item in self.text_highlights if item.layer != key)
        self.order = [identity for identity in self.order if identity not in removed]

    def to_bytes(self):
        if self.warning:
            return self.raw
        current = {s.id: s for s in self.strokes}
        if ({s.id: s.payload() for s in self.strokes} == self._baseline and self.layers == self._original_layers
                and self.text_highlights == self._original_highlights and not self.ordering_dirty
                and not self.image_resources and {p.id: p.payload() for p in self.images} == self._image_baseline):
            return self.raw
        author, first, additions = allocation(self._blocks)
        chunks = []
        pictures = {p.id: p for p in self.images}
        removed_highlights = {item.id for item in self._original_highlights} - {item.id for item in self.text_highlights}
        for raw, block in zip(self._frames, self._blocks):
            if isinstance(block, ss.SceneGlyphItemBlock):
                key = f'{block.item.item_id.part1}:{block.item.item_id.part2}'
                if key in removed_highlights:
                    block = deepcopy(block)
                    block.item = replace(block.item, value=None, deleted_length=1)
                    raw = encode([block])[len(HEADER_V6):]
            if isinstance(block, ImageItem):
                key = f'{block.item.item_id.part1}:{block.item.item_id.part2}'
                if key in self._image_baseline:
                    if key not in pictures:
                        block = deepcopy(block)
                        block.item = replace(block.item, value=None, deleted_length=1)
                        raw = encode([block])[len(HEADER_V6):]
                    elif pictures[key].payload() != self._image_baseline[key]:
                        block = deepcopy(block)
                        for vertex, corner in zip(block.item.value.vertices, pictures[key].corners):
                            vertex[:2] = [corner[0] - WIDTH / 2, corner[1]]
                        raw = encode([block])[len(HEADER_V6):]
            if isinstance(block, ss.SceneLineItemBlock):
                key = f'{block.item.item_id.part1}:{block.item.item_id.part2}'
                if key in self._baseline and key not in current:
                    # Retain the sequence identity/links as a tombstone.
                    block = deepcopy(block)
                    block.item = replace(block.item, value=None, deleted_length=1)
                    raw = encode([block])[len(HEADER_V6):]
                elif key in self._baseline and current[key].payload() != self._baseline[key]:
                    changed = current[key]
                    block = deepcopy(block)
                    original = block.item.value.points
                    block.item.value.thickness_scale = changed.scale
                    if len(changed.points) == len(original):
                        # Geometric transforms retain the native point dynamics;
                        # only explicitly edited positions/width/pressure change.
                        for point, values, baseline in zip(original, changed.points, self._baseline[key]['points']):
                            point.x, point.y = values[0] - WIDTH / 2, values[1]
                            if values[2] != baseline[2]:
                                point.pressure = round(values[2] * 255)
                            if values[3] != baseline[3]:
                                point.width = max(0, min(65535, round(values[3] * 4)))
                    else:
                        block.item.value.points = [si.Point(x - WIDTH / 2, y, 0, 0,
                            max(0, min(65535, round(w * 4))), round(p * 255))
                            for x, y, p, w in changed.points]
                    raw = encode([block])[len(HEADER_V6):]
            if isinstance(block, ss.TreeNodeBlock):
                key = f'{block.group.node_id.part1}:{block.group.node_id.part2}'
                layer = next((row for row in self.layers if row[0] == key), None)
                if layer and (layer[1] != block.group.label.value or layer[2] != block.group.visible.value):
                    block = deepcopy(block)
                    stamp = CrdtId(author, first)
                    first += 1
                    block.group.label = LwwValue(stamp, layer[1])
                    block.group.visible = LwwValue(stamp, layer[2])
                    raw = encode([block])[len(HEADER_V6):]
            chunks.append(raw)
        identities = {s.id: (CrdtId(*map(int, s.id.split(':'))) if s.id in self._baseline
                              else CrdtId(author, first + index))
                      for index, s in enumerate(self.strokes)}
        right_neighbors, next_by_layer = {}, {}
        for stroke in reversed(self.strokes):
            right_neighbors[stroke.id] = next_by_layer.get(stroke.layer, CrdtId(0, 0))
            if stroke.id in self._baseline:
                next_by_layer[stroke.layer] = identities[stroke.id]
        tails = {}
        for index, stroke in enumerate(self.strokes):
            if stroke.id in self._baseline:
                parent = CrdtId(*map(int, stroke.layer.split(':')))
                tails[parent] = identities[stroke.id]
                continue
            parent = CrdtId(*map(int, stroke.layer.split(':')))
            identity = identities[stroke.id]
            line = si.Line(si.PenColor(stroke.color), si.Pen(stroke.tool),
                [si.Point(x - WIDTH / 2, y, 0, 0, max(0, min(65535, round(w * 4))), round(p * 255))
                 for x, y, p, w in stroke.points], stroke.scale, 0, color_rgba=stroke.color_rgba)
            left = tails.get(parent, CrdtId(0, 0))
            additions.append(ss.SceneLineItemBlock(parent, CrdtSequenceItem(identity,
                left, right_neighbors[stroke.id], 0, line)))
            tails[parent] = identity
        # New image objects use the same resource table and quad format as native captures.
        cursor = first + len(self.strokes) + 1
        if self.image_resources:
            resources = [r for b in self._blocks if isinstance(b, ImageResources) for r in b.resources]
            resources += [replace(r, stamp=CrdtId(author, cursor + i)) for i, r in enumerate(self.image_resources)]
            cursor += len(self.image_resources)
            chunks = [raw for raw, b in zip(chunks, self._blocks) if not isinstance(b, ImageResources)]
            additions.append(ImageResources(resources))
        image_identities = {}
        for picture in self.images:
            if picture.id in self._image_baseline:
                continue
            parent = CrdtId(*map(int, picture.layer.split(':')))
            identity, stamp, geometry_id = [CrdtId(author, cursor + i) for i in range(3)]
            cursor += 3
            image_identities[picture.id] = identity
            original_tail = next((key for key in reversed(self.order)
                if key in self._image_baseline and key in pictures and pictures[key].layer == picture.layer), None)
            left = tails.get(parent, CrdtId(*map(int, original_tail.split(':'))) if original_tail else CrdtId(0, 0))
            vertices = [[p[0] - WIDTH / 2, p[1], *uv] for p, uv in
                        zip(picture.corners, [[0, 0], [1, 0], [1, 1], [0, 1]])]
            additions.append(ImageItem(parent, CrdtSequenceItem(identity, left, CrdtId(0, 0), 0,
                ImageQuad(stamp, picture.resource, geometry_id, vertices, [0, 1, 2, 2, 3, 0]))))
            tails[parent] = identity
        result = HEADER_V6 + b''.join(chunks) + encode(additions)[len(HEADER_V6):]
        if self.ordering_dirty or ((self.images or self.text_highlights) and any(s.id not in self._baseline for s in self.strokes)):
            from .images import reorder_native
            ids = {**identities, **image_identities}
            ids.update({p.id: CrdtId(*map(int, p.id.split(':'))) for p in self.images if p.id in self._image_baseline})
            ids.update({item.id: CrdtId(*map(int, item.id.split(':'))) for item in self.text_highlights})
            result = reorder_native(result, [ids[key] for key in self.order if key in ids])
        layer_ids = [key for key, _, _ in self.layers]
        if layer_ids != [key for key, _, _ in self._original_layers]:
            result = write_layer_stack(result, self.layers)
        return result
