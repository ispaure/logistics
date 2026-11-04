"""Native v6 ink adapter. Original frames survive unless their stroke is edited."""
from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass, replace
from io import BytesIO
import math
import struct
from uuid import uuid4

from ._vendor.rmscene import scene_stream as ss, scene_items as si
from ._vendor.rmscene.crdt_sequence import CrdtSequenceItem
from ._vendor.rmscene.tagged_block_common import CrdtId, LwwValue, HEADER_V6
from ._vendor.rmscene.scene_tree import SceneTree
from .images import ImageResources, ImageItem, ImageQuad, Picture
from .brushes import TOOLS, COLORS, WIDTHS, native_color, native_scale, stroke_points

WIDTH, HEIGHT = 1404, 1872
MAX_POINTS = 100_000
MAX_PAGE_POINTS = 1_000_000


def encode(blocks):
    output = BytesIO()
    ss.write_blocks(output, blocks, options={'version': '3.4'})
    return output.getvalue()


def frames(data):
    if not data.startswith(HEADER_V6):
        raise ValueError('Only reMarkable v6 ink is editable; this page is preserved unchanged.')
    offset = len(HEADER_V6)
    result = []
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError('Truncated ink frame.')
        size = struct.unpack_from('<I', data, offset)[0] + 8
        if size > len(data) - offset or len(result) >= 100_000:
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


@dataclass
class InkPage:
    raw: bytes = b''
    strokes: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    images: list = field(default_factory=list)
    image_resources: list = field(default_factory=list)
    _image_baseline: dict = field(default_factory=dict, repr=False)
    order: list = field(default_factory=list)
    ordering_dirty: bool = False
    warning: str = ''
    _frames: list = field(default_factory=list, repr=False)
    _blocks: list = field(default_factory=list, repr=False)
    _baseline: dict = field(default_factory=dict, repr=False)
    _original_layers: list = field(default_factory=list, repr=False)

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
            if any(isinstance(b, (ss.UnreadableBlock, ss.SceneGlyphItemBlock))
                   or (isinstance(b, ss.RootTextBlock) and any(isinstance(v, str) and v.strip() for v in b.value.items.values()))
                   for b in page._blocks):
                raise ValueError('This page has text, highlights or unknown objects. Ink editing is disabled; all bytes are preserved.')
            mapping = {id(b.item.value): b for b in page._blocks if isinstance(b, (ss.SceneLineItemBlock, ImageItem))}
            prior_strokes = {s.id: s for s in previous.strokes} if previous else {}
            prior_blocks = {id(block) for block in previous._blocks} if previous else set()
            total = 0
            def visit(group, depth=0):
                nonlocal total
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
            page._baseline.update({s.id: deepcopy(s.payload()) for s in page.strokes if s.id not in page._baseline})
            page._original_layers = list(page.layers)
            page._image_baseline = {p.id: deepcopy(p.payload()) for p in page.images}
        except Exception as error:
            page.warning = str(error)
            page.images = []
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

    def add(self, points, tool=17, color=0, width=2, layer=None, *, page_height=HEIGHT):
        if self.warning:
            raise ValueError(self.warning)
        if type(width) not in (int, float) or width not in WIDTHS.values():
            raise ValueError('Unsupported brush, color or width.')
        native, rgba = native_color(tool, color)
        if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
            raise ValueError('Invalid stroke length.')
        clean = []
        for point in points:
            if len(point) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point):
                raise ValueError('Invalid stroke point.')
            x, y, pressure = point
            if not 0 <= x <= WIDTH or not 0 <= y <= page_height or not 0 <= pressure <= 1:
                raise ValueError('Stroke is outside the page.')
            clean.append([x, y, pressure])
        clean = stroke_points(clean, tool, int(width))
        from .sampling import simplify_stroke
        clean = simplify_stroke(clean, tool, native_x_origin=WIDTH / 2)
        visible = [key for key, name, shown in self.layers if shown]
        layer = layer or (visible[-1] if visible else None)
        if layer not in visible:
            raise ValueError('Choose a visible ink layer.')
        stroke = Stroke(uuid4().hex, layer, tool, native, clean, native_scale(tool, width), rgba)
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

    def to_bytes(self):
        if self.warning:
            return self.raw
        current = {s.id: s for s in self.strokes}
        if {s.id: s.payload() for s in self.strokes} == self._baseline and self.layers == self._original_layers and not self.ordering_dirty and not self.image_resources and {p.id: p.payload() for p in self.images} == self._image_baseline:
            return self.raw
        author, first, additions = allocation(self._blocks)
        chunks = []
        pictures = {p.id: p for p in self.images}
        for raw, block in zip(self._frames, self._blocks):
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
        if self.ordering_dirty or (self.images and any(s.id not in self._baseline for s in self.strokes)):
            from .images import reorder_native
            ids = {**identities, **image_identities}
            ids.update({p.id: CrdtId(*map(int, p.id.split(':'))) for p in self.images if p.id in self._image_baseline})
            result = reorder_native(result, [ids[key] for key in self.order if key in ids])
        return result
