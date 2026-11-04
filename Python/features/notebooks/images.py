"""Native v6 PNG resources (0x0e) and textured image quads (0x0f).

Layout verified against the user's exported reMarkable image page. Unchanged
frames remain byte-identical; unsupported meshes stay under the ink safety gate.
"""
from dataclasses import dataclass, field
from io import BytesIO
import base64
import math
from uuid import uuid4

from ._vendor.rmscene.scene_stream import Block
from ._vendor.rmscene.crdt_sequence import CrdtSequenceItem
from ._vendor.rmscene.tagged_block_common import CrdtId


@dataclass
class Resource:
    uuid: bytes
    stamp: CrdtId
    name: str
    tail: bytes = b'\x2c\x0a\x00\x00\x00\x1f\x00\x00\x2c\x02\x00\x00\x00\x11\x00'


@dataclass
class ImageResources(Block):
    BLOCK_TYPE = 14
    resources: list = field(default_factory=list)

    def version_info(self, writer):
        return 3, 3

    @classmethod
    def from_stream(cls, r):
        resources = []
        with r.read_subblock(1):
            count = r.data.read_varuint()
            if count > 4096:
                raise ValueError('Too many image resources.')
            for _ in range(count):
                with r.read_subblock(0):
                    uuid = r.data.read_bytes(16)
                    with r.read_subblock(1) as info:
                        stamp, name = r.read_id(1), r.read_string(2)
                        tail = r.data.read_bytes(info.offset + info.size - r.data.tell())
                    resources.append(Resource(uuid, stamp, name, tail))
        return cls(resources)

    def to_stream(self, w):
        with w.write_subblock(1):
            w.data.write_varuint(len(self.resources))
            for resource in self.resources:
                with w.write_subblock(0):
                    w.data.write_bytes(resource.uuid)
                    with w.write_subblock(1):
                        w.write_id(1, resource.stamp)
                        w.write_string(2, resource.name)
                        w.data.write_bytes(resource.tail)


@dataclass
class ImageQuad:
    stamp: CrdtId
    resource: bytes
    geometry_id: CrdtId
    vertices: list
    indices: list


@dataclass
class ImageItem(Block):
    BLOCK_TYPE = 15
    parent_id: CrdtId
    item: CrdtSequenceItem
    move_id: CrdtId | None = None

    def version_info(self, writer):
        return 2, 2

    @classmethod
    def from_stream(cls, r):
        parent, identity, left, right = [r.read_id(i) for i in range(1, 5)]
        deleted = r.read_int(5)
        quad = None
        if r.has_subblock(6):
            with r.read_subblock(6):
                if r.data.read_uint8() != 7:
                    raise ValueError('Unsupported image object.')
                with r.read_subblock(1):
                    stamp = r.read_id(1)
                    with r.read_subblock(2):
                        resource = r.data.read_bytes(16)
                geometry_id = r.read_id(2)
                with r.read_subblock(3):
                    if r.data.read_varuint() != 16:
                        raise ValueError('Unsupported image mesh.')
                    vertices = [[r.data.read_float32() for _ in range(4)] for _ in range(4)]
                with r.read_subblock(4):
                    if r.data.read_varuint() != 6:
                        raise ValueError('Unsupported image triangles.')
                    indices = [r.data.read_uint32() for _ in range(6)]
                if indices != [0, 1, 2, 2, 3, 0] or any(not math.isfinite(v) for p in vertices for v in p):
                    raise ValueError('Invalid image geometry.')
                if [p[2:] for p in vertices] != [[0, 0], [1, 0], [1, 1], [0, 1]]:
                    raise ValueError('Unsupported image texture coordinates.')
                validate_corners([[p[0], p[1]] for p in vertices])
                quad = ImageQuad(stamp, resource, geometry_id, vertices, indices)
        return cls(parent, CrdtSequenceItem(identity, left, right, deleted, quad),
                   r.read_id_optional(5) if r.bytes_remaining_in_block() else None)

    def to_stream(self, w):
        for i, value in enumerate([self.parent_id, self.item.item_id, self.item.left_id, self.item.right_id], 1):
            w.write_id(i, value)
        w.write_int(5, self.item.deleted_length)
        q = self.item.value
        if q is not None:
            with w.write_subblock(6):
                w.data.write_uint8(7)
                with w.write_subblock(1):
                    w.write_id(1, q.stamp)
                    with w.write_subblock(2):
                        w.data.write_bytes(q.resource)
                w.write_id(2, q.geometry_id)
                with w.write_subblock(3):
                    w.data.write_varuint(16)
                    for p in q.vertices:
                        for v in p:
                            w.data.write_float32(v)
                with w.write_subblock(4):
                    w.data.write_varuint(6)
                    for i in q.indices:
                        w.data.write_uint32(i)

        if self.move_id is not None:
            w.write_id(5, self.move_id)


@dataclass
class Picture:
    id: str
    layer: str
    resource: bytes
    corners: list

    def payload(self):
        return dict(id=self.id, layer=self.layer, corners=self.corners)


def image_payloads(book, index):
    import re
    ink = book.page(index)
    resources = {r.uuid: r.name for b in ink._blocks if isinstance(b, ImageResources) for r in b.resources}
    resources.update({r.uuid: r.name for r in ink.image_resources})
    result = []
    for image in ink.images:
        name = resources.get(image.resource, '')
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.png', name):
            raise ValueError('Invalid image resource name.')
        data = book.members.get(f'{book.id}/{book.pages[index].id}/{name}')
        if data is None:
            raise ValueError('Missing notebook image resource.')
        result.append(dict(**image.payload(), src='data:image/png;base64,' + base64.b64encode(data).decode()))
    return result


def paste(book, index, action):
    """Bound and decode PNG input before touching page state or archive members."""
    from .ink import allocation
    src = action.get('src')
    if not isinstance(src, str) or not src.startswith('data:image/png;base64,') or len(src) > 4 * 1024 * 1024:
        raise ValueError('Choose a PNG image smaller than 3 MiB.')
    data = base64.b64decode(src.split(',', 1)[1], validate=True)
    validate_png(data)
    corners = action.get('corners')
    validate_corners(corners)
    ink = book.page(index)
    if ink.warning:
        raise ValueError(ink.warning)
    visible = [key for key, _, shown in ink.layers if shown]
    layer = action.get('layer') or (visible[-1] if visible else None)
    if layer not in visible or len(ink.images) >= 256:
        raise ValueError('Choose a visible layer; at most 256 images fit on a page.')
    author, first, _ = allocation(ink._blocks)
    identity = uuid4()
    resource = Resource(identity.bytes, CrdtId(author, first), str(identity) + '.png')
    # A fresh resource block is merged with the existing table during encoding.
    ink.image_resources = [*ink.image_resources, resource]
    ink.images = [*ink.images, Picture(uuid4().hex, layer, identity.bytes, deepcopy_corners(corners))]
    ink.order = [*ink.order, ink.images[-1].id]
    ink.ordering_dirty = True
    book.members[f'{book.id}/{book.pages[index].id}/{resource.name}'] = data
    book.structure_dirty = True


def deepcopy_corners(corners):
    return [list(p) for p in corners]


def validate_corners(corners):
    if (not isinstance(corners, list) or len(corners) != 4 or any(
            not isinstance(p, list) or len(p) != 2 or any(type(v) not in (int, float)
            or not math.isfinite(v) or abs(v) > 1_000_000 for v in p) for p in corners)):
        raise ValueError('Invalid image corners.')
    a, b, c, d = corners
    if (math.hypot(b[0]-a[0], b[1]-a[1]) < 1 or math.hypot(d[0]-a[0], d[1]-a[1]) < 1
            or any(abs(a[i] + c[i] - b[i] - d[i]) > .1 for i in range(2))):
        raise ValueError('Image must be a nonempty affine quad.')


def reorder_native(data, order):
    """Rewrite only sequence links to arrange native image/stroke stacking."""
    from copy import deepcopy
    from dataclasses import replace
    from .ink import frames, encode
    from ._vendor.rmscene import scene_stream as ss
    from ._vendor.rmscene.tagged_block_common import HEADER_V6
    blocks = list(ss.read_blocks(BytesIO(data)))
    groups = {}
    for b in blocks:
        if isinstance(b, (ss.SceneLineItemBlock, ImageItem)) and b.item.value is not None and not b.item.deleted_length:
            groups.setdefault(b.parent_id, set()).add(b.item.item_id)
    links = {}
    end = CrdtId(0, 0)
    for members in groups.values():
        sequence = [key for key in order if key in members]
        sequence += [key for key in members if key not in sequence]
        for i, key in enumerate(sequence):
            links[key] = (sequence[i-1] if i else end, sequence[i+1] if i+1 < len(sequence) else end)
    chunks = []
    for raw, b in zip(frames(data), blocks):
        if isinstance(b, (ss.SceneLineItemBlock, ImageItem)):
            left, right = links.get(b.item.item_id, (end, end))
            if (left, right) != (b.item.left_id, b.item.right_id):
                b = deepcopy(b)
                b.item = replace(b.item, left_id=left, right_id=right)
                raw = encode([b])[len(HEADER_V6):]
        chunks.append(raw)
    return HEADER_V6 + b''.join(chunks)


def validate_png(data):
    """Validate bounded capture PNG chunks without a desktop image dependency."""
    import struct
    import zlib
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid PNG image.')
    offset, pixels, saw_data, ended = 8, None, False, False
    while offset + 12 <= len(data):
        length = struct.unpack_from('>I', data, offset)[0]
        kind = data[offset+4:offset+8]
        end = offset + 12 + length
        if end > len(data) or zlib.crc32(data[offset+4:end-4]) != struct.unpack_from('>I', data, end-4)[0]:
            raise ValueError('Invalid PNG chunk.')
        chunk = data[offset+8:end-4]
        if pixels is None:
            if kind != b'IHDR' or length != 13:
                raise ValueError('Missing PNG header.')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', chunk)
            if not width or not height or width*height > 4*1024*1024:
                raise ValueError('Image exceeds the four megapixel limit.')
            if depth != 8 or color not in (0,2,4,6) or compression or filtering or interlace:
                raise ValueError('Use a noninterlaced eight-bit PNG capture.')
            channels = {0:1,2:3,4:2,6:4}[color]
            pixels = height * (1 + width*channels)
            decoder = zlib.decompressobj()
            remaining = pixels
        elif kind == b'IHDR':
            raise ValueError('Duplicate PNG header.')
        if kind == b'IDAT':
            saw_data = True
            try:
                decoded = decoder.decompress(chunk, remaining+1)
            except zlib.error as error:
                raise ValueError('Invalid PNG pixels.') from error
            remaining -= len(decoded)
            if remaining < 0 or decoder.unconsumed_tail or decoder.unused_data:
                raise ValueError('Oversized PNG pixel stream.')
        if kind == b'IEND':
            if length or not saw_data or not decoder.eof or remaining or end != len(data):
                raise ValueError('Incomplete PNG pixels.')
            ended = True
            break
        offset = end
    if not ended:
        raise ValueError('Truncated PNG image.')
