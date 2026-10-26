"""Native v6 ink adapter. Original frames survive unless their stroke is edited."""
from copy import deepcopy
from dataclasses import dataclass, field, replace
from io import BytesIO
import math
import struct
from uuid import uuid4

from ._vendor.rmscene import scene_stream as ss, scene_items as si
from ._vendor.rmscene.crdt_sequence import CrdtSequenceItem
from ._vendor.rmscene.tagged_block_common import CrdtId, LwwValue, HEADER_V6
from ._vendor.rmscene.scene_tree import SceneTree
from .brushes import TOOLS, COLORS, WIDTHS, native_color, stroke_points

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
    warning: str = ''
    _frames: list = field(default_factory=list, repr=False)
    _blocks: list = field(default_factory=list, repr=False)
    _baseline: dict = field(default_factory=dict, repr=False)
    _original_layers: list = field(default_factory=list, repr=False)

    @classmethod
    def read(cls, data):
        page = cls(raw=data)
        try:
            page._frames = frames(data)
            page._blocks = list(ss.read_blocks(BytesIO(data)))
            if len(page._blocks) != len(page._frames):
                raise ValueError('Inconsistent ink frame count.')
            tree = SceneTree()
            ss.build_tree(tree, page._blocks)
            if any(isinstance(b, (ss.UnreadableBlock, ss.SceneGlyphItemBlock))
                   or (isinstance(b, ss.RootTextBlock) and any(isinstance(v, str) and v.strip() for v in b.value.items.values()))
                   for b in page._blocks):
                raise ValueError('This page has text, highlights or unknown objects. Ink editing is disabled; all bytes are preserved.')
            mapping = {id(b.item.value): b for b in page._blocks if isinstance(b, ss.SceneLineItemBlock)}
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
                    elif isinstance(child, si.Line):
                        if depth == 0:
                            raise ValueError('Ink outside a layer is preserved but cannot yet be edited.')
                        block = mapping[id(child)]
                        if block.item.deleted_length:
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
            page._baseline = {s.id: deepcopy(s.payload()) for s in page.strokes}
            page._original_layers = list(page.layers)
        except Exception as error:
            page.warning = str(error)
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

    def add(self, points, tool=17, color=0, width=2, layer=None):
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
            if not 0 <= x <= WIDTH or not 0 <= y <= HEIGHT or not 0 <= pressure <= 1:
                raise ValueError('Stroke is outside the page.')
            clean.append([x, y, pressure])
        clean = stroke_points(clean, tool, int(width))
        visible = [key for key, name, shown in self.layers if shown]
        layer = layer or (visible[-1] if visible else None)
        if layer not in visible:
            raise ValueError('Choose a visible ink layer.')
        stroke = Stroke(uuid4().hex, layer, tool, native, clean, width, rgba)
        self.strokes.append(stroke)
        return stroke

    def add_layer(self, name):
        if self.warning:
            raise ValueError(self.warning)
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or len(self.layers) >= 32:
            raise ValueError('Choose a layer name of 1–80 characters; at most 32 layers are supported.')
        raw = self.to_bytes()
        page = InkPage.read(raw)
        authors = {key for b in page._blocks if isinstance(b, ss.AuthorIdsBlock) for key in b.author_uuids}
        author = next(n for n in range(1, 65536) if n not in authors)
        node, item, end, root = CrdtId(author, 1), CrdtId(author, 2), CrdtId(0, 0), CrdtId(0, 1)
        tree = SceneTree()
        ss.build_tree(tree, page._blocks)
        order = tree.root.children.keys()
        extra = [ss.AuthorIdsBlock({author: uuid4()}), ss.SceneTreeBlock(node, end, True, root),
                 ss.TreeNodeBlock(si.Group(node, label=LwwValue(CrdtId(author, 3), name.strip()))),
                 ss.SceneGroupItemBlock(root, CrdtSequenceItem(item, order[-1] if order else end, end, 0, node))]
        updated = InkPage.read(raw + encode(extra)[len(HEADER_V6):])
        self.__dict__.update(updated.__dict__)

    def to_bytes(self):
        if self.warning:
            return self.raw
        current = {s.id: s for s in self.strokes}
        if {s.id: s.payload() for s in self.strokes} == self._baseline and self.layers == self._original_layers:
            return self.raw
        chunks = []
        for raw, block in zip(self._frames, self._blocks):
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
                    if len(changed.points) != len(block.item.value.points):
                        raise ValueError('Invalid transformed stroke.')
                    for point, values in zip(block.item.value.points, changed.points):
                        point.x, point.y = values[0] - WIDTH / 2, values[1]
                    raw = encode([block])[len(HEADER_V6):]
            if isinstance(block, ss.TreeNodeBlock):
                key = f'{block.group.node_id.part1}:{block.group.node_id.part2}'
                layer = next((row for row in self.layers if row[0] == key), None)
                if layer and (layer[1] != block.group.label.value or layer[2] != block.group.visible.value):
                    block = deepcopy(block)
                    stamp = CrdtId(block.group.visible.timestamp.part1, max(block.group.visible.timestamp.part2, block.group.label.timestamp.part2) + 1)
                    block.group.label = LwwValue(stamp, layer[1])
                    block.group.visible = LwwValue(stamp, layer[2])
                    raw = encode([block])[len(HEADER_V6):]
            chunks.append(raw)
        # Allocate a fresh author, avoiding every existing author number.
        authors = {key for b in self._blocks if isinstance(b, ss.AuthorIdsBlock) for key in b.author_uuids}
        author = next((n for n in range(1, 65536) if n not in authors), None)
        if author is None:
            raise ValueError('Ink author space exhausted.')
        additions = [ss.AuthorIdsBlock({author: uuid4()})]
        tails = {}
        from ._vendor.rmscene.crdt_sequence import CrdtSequence
        for parent in {b.parent_id for b in self._blocks if isinstance(b, ss.SceneLineItemBlock)}:
            ordered = CrdtSequence([b.item for b in self._blocks if isinstance(b, ss.SceneLineItemBlock) and b.parent_id == parent]).keys()
            if ordered:
                tails[parent] = ordered[-1]
        for index, stroke in enumerate(self.strokes):
            if stroke.id in self._baseline:
                continue
            parent = CrdtId(*map(int, stroke.layer.split(':')))
            identity = CrdtId(author, index + 1)
            line = si.Line(si.PenColor(stroke.color), si.Pen(stroke.tool),
                [si.Point(x - WIDTH / 2, y, 0, 0, max(1, min(65535, round(w * 4))), round(p * 255))
                 for x, y, p, w in stroke.points], stroke.scale, 0, color_rgba=stroke.color_rgba)
            additions.append(ss.SceneLineItemBlock(parent, CrdtSequenceItem(identity,
                tails.get(parent, CrdtId(0, 0)), CrdtId(0, 0), 0, line)))
            tails[parent] = identity
        return HEADER_V6 + b''.join(chunks) + encode(additions)[len(HEADER_V6):]
