"""Give offline Markdown WebViews the font actually used by Android labels.

Generic CSS families are resolved by Chromium, independently of OEM font
customization. Android 12's public text shaper exposes the selected native font,
including OEM replacements. Only marked Markdown surfaces opt into this bridge.
"""
import logging
import re
import struct
import zlib
from uuid import uuid4

MARKER = '<meta name="logistics-native-font" content="true">'
FONT_ROOT = 'https://logistics.invalid/native-font/'
MAX_NATIVE_FONT = 32 * 1024 * 1024
_cached = None


def standalone_font(data, index=0):
    """Extract one SFNT face from an Android TrueType collection for Chromium."""
    if data[:4] != b'ttcf':
        if index or data[:4] not in (b'\x00\x01\x00\x00', b'OTTO', b'true'):
            raise ValueError('Unsupported native font format.')
        return data
    count = struct.unpack_from('>I', data, 8)[0]
    if not 0 <= index < count:
        raise ValueError('Invalid native font collection index.')
    start = struct.unpack_from('>I', data, 12 + 4 * index)[0]
    tables = struct.unpack_from('>H', data, start + 4)[0]
    result = bytearray(data[start:start + 12 + tables * 16])
    head = None
    for number in range(tables):
        record = 12 + 16 * number
        tag, checksum, offset, length = struct.unpack_from('>4sIII', result, record)
        if offset + length > len(data):
            raise ValueError('Truncated native font table.')
        target = len(result)
        struct.pack_into('>I', result, record + 8, target)
        result.extend(data[offset:offset + length])
        result.extend(b'\0' * (-len(result) % 4))
        if tag == b'head':
            head = target
    if head is not None:
        struct.pack_into('>I', result, head + 8, 0)
        checksum = sum(struct.unpack('>' + 'I' * (len(result) // 4), result))
        struct.pack_into('>I', result, head + 8, (0xB1B0AFBA - checksum) & 0xFFFFFFFF)
    return bytes(result)


def web_font(data):
    """Losslessly package SFNT tables as WOFF 1, using only the standard library.

    Android's variable UI fonts can exceed 2 MiB uncompressed. Per-table zlib
    compression reduces transfer to Chromium without subsetting away glyphs or
    variation data needed by characters typed later. Bytes are served from RAM.
    """
    tables = struct.unpack_from('>H', data, 4)[0]
    result = bytearray(44 + 20 * tables)
    total = 12 + 16 * tables
    for number in range(tables):
        tag, checksum, offset, length = struct.unpack_from('>4sIII', data, 12 + 16 * number)
        if offset + length > len(data):
            raise ValueError('Truncated native font table.')
        raw = data[offset:offset + length]
        compressed = zlib.compress(raw)
        packed = compressed if len(compressed) < length else raw
        struct.pack_into('>4sIIII', result, 44 + 20 * number, tag, len(result), len(packed), length, checksum)
        result.extend(packed)
        result.extend(b'\0' * (-len(result) % 4))
        total += (length + 3) & ~3
    struct.pack_into('>4sIIHHIHHIIIII', result, 0, b'wOFF', struct.unpack_from('>I', data)[0],
                     len(result), tables, 0, total, 1, 0, 0, 0, 0, 0, 0)
    return bytes(result)


def native_font():
    """Read only the label's Latin face; retain browser fallback for other scripts."""
    global _cached
    from android.os import Build
    if Build.VERSION.SDK_INT < 31:
        return None
    import toga
    from android.graphics.text import TextRunShaper
    from java import cast, jarray, jbyte
    from java.nio import ByteBuffer
    # Use the same Toga construction/style path as app labels, rather than
    # guessing a file in /system/fonts or reflecting private Typeface fields.
    label = toga.Label('Ag')
    paint = label._impl.native.getPaint()
    key = (str(paint.getTypeface()), str(label._impl.native.getResources().getConfiguration()))
    if _cached is not None and _cached[0] == key:
        return _cached[1]
    glyphs = TextRunShaper.shapeTextRun('A', 0, 1, 0, 1, 0.0, 0.0, False, paint)
    font = glyphs.getFont(0)
    # MappedByteBuffer's covariant duplicate() is abstract on Android 15;
    # dispatch through ByteBuffer to avoid Chaquopy choosing that overload.
    buffer = cast(ByteBuffer, font.getBuffer()).duplicate()
    buffer.rewind()
    if buffer.remaining() > MAX_NATIVE_FONT:
        raise ValueError('Native font exceeds the Markdown embedding limit.')
    data = jarray(jbyte)(buffer.remaining())
    buffer.get(data)
    # Chaquopy converts a Java byte[] directly to bytes, preserving signed bytes.
    data = web_font(standalone_font(bytes(data), font.getTtcIndex()))
    axes = font.getAxes()
    variations = []
    if axes is not None:
        for axis in axes:
            tag = str(axis.getTag())
            # Let CSS bold/italic synthesis choose weight and slant per element.
            if re.fullmatch('[A-Za-z0-9]{4}', tag) and tag not in ('wght', 'ital', 'slnt'):
                variations.append('"' + tag + '" ' + str(float(axis.getStyleValue())))
    settings = 'font-variation-settings:' + ','.join(variations) + ';' if variations else ''
    _cached = key, (data, settings)
    return _cached[1]


def style_markdown(content, *, impl=None, font_css=None):
    """Add offline font CSS while keeping the font resource out of document HTML."""
    if impl is not None:
        impl._markdown_font_resource = None
    if MARKER not in content:
        return content
    policy = 'font-src data:'
    if font_css is None:
        try:
            font = native_font()
        except Exception:
            logging.getLogger(__name__).warning('Native Markdown font unavailable; using sans-serif.', exc_info=True)
            return content
        if font is None or impl is None:
            return content
        data, settings = font
        url = FONT_ROOT + uuid4().hex + '.woff'
        impl._markdown_font_resource = url, data
        font_css = ('@font-face{font-family:LogisticsNative;src:url(' + url + ')}'
                    'html body{font-family:LogisticsNative,sans-serif;' + settings + '}')
        policy = 'font-src ' + url
    if not font_css:
        return content
    # The unique font URL is intercepted inside this WebView and served from
    # RAM. Keeping font bytes out of HTML avoids Toga's >2 MiB disk fallback.
    content = re.sub(r'(content=")([^"]*)(")',
        lambda match: match[1] + match[2] + '; ' + policy + match[3]
        if "default-src 'none'" in match[2] else match[0], content, count=0)
    return content.replace('</head>', '<style id="logistics-native-font">' + font_css + '</style></head>', 1)


def font_response(impl, url):
    """Intercept only our reserved font path; never fetch retired font URLs."""
    if not url.startswith(FONT_ROOT):
        return None
    from android.webkit import WebResourceResponse
    from java.io import ByteArrayInputStream
    from java.util import HashMap
    from java import jarray, jbyte
    resource = getattr(impl, '_markdown_font_resource', None)
    current = resource is not None and resource[0] == url and not getattr(impl.interface, 'private_closed', False)
    response = WebResourceResponse('font/woff', None,
        ByteArrayInputStream(jarray(jbyte)(resource[1] if current else b'')))
    headers = HashMap()
    headers.put('Access-Control-Allow-Origin', '*')
    headers.put('Cache-Control', 'no-store')
    response.setResponseHeaders(headers)
    if not current:
        response.setStatusCodeAndReasonPhrase(410, 'Gone')
    return response


def install_font_responses():
    """Extend the pinned Toga client while preserving navigation/cache handling."""
    from toga_android.widgets.internal.webview import TogaWebClient
    original = TogaWebClient.shouldInterceptRequest

    def intercept(client, webview, request):
        try:
            response = font_response(client.impl, str(request.getUrl()))
        except ReferenceError:
            response = None
        return response if response is not None else original(client, webview, request)

    TogaWebClient.shouldInterceptRequest = intercept
