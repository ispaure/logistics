"""Offline native-font bridge contracts, independent of an Android runtime."""
import struct
import sys
import unittest
import zlib
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mobile.android_markdown_font import FONT_ROOT, MARKER, font_response, standalone_font, style_markdown, web_font
from mobile.preview import markdown_preview
from features.text_editor.mobile.markdown_editor import editor_html


class MarkdownFontTests(unittest.TestCase):
    def test_older_android_keeps_css_fallback_without_importing_new_font_apis(self):
        content = markdown_preview('Still readable')
        impl = SimpleNamespace()
        with patch.dict(sys.modules, {'android.os': SimpleNamespace(
                Build=SimpleNamespace(VERSION=SimpleNamespace(SDK_INT=30)))}):
            self.assertEqual(style_markdown(content, impl=impl), content)
        self.assertIsNone(impl._markdown_font_resource)

    def test_large_font_stays_in_ram_and_is_retired_on_document_replacement(self):
        content = markdown_preview('Private draft')
        impl = SimpleNamespace(interface=SimpleNamespace(private_closed=False))
        font = b'font' * (1024 * 1024)
        with patch('mobile.android_markdown_font.native_font', return_value=(font, '')):
            styled = style_markdown(content, impl=impl)
        url, data = impl._markdown_font_resource
        self.assertIs(data, font)
        self.assertTrue(url.startswith(FONT_ROOT))
        self.assertIn('font-src ' + url, styled)
        self.assertLess(len(styled), len(content) + 500)
        self.assertNotIn('base64', styled)
        self.assertIsNone(font_response(impl, 'https://example.invalid/ordinary'))
        style_markdown('<p>Document closed.</p>', impl=impl)
        self.assertIsNone(impl._markdown_font_resource)

    def test_font_route_serves_only_current_bytes_and_never_fetches_stale_urls(self):
        url = FONT_ROOT + 'current.woff'
        impl = SimpleNamespace(interface=SimpleNamespace(private_closed=False), _markdown_font_resource=(url, b'font bytes'))
        response = Mock()
        stream = Mock(side_effect=lambda data: data)
        modules = {'android.webkit': SimpleNamespace(WebResourceResponse=Mock(return_value=response)),
                   'java.io': SimpleNamespace(ByteArrayInputStream=stream),
                   'java.util': SimpleNamespace(HashMap=Mock),
                   'java': SimpleNamespace(jarray=lambda kind: bytes, jbyte=object())}
        with patch.dict(sys.modules, modules):
            self.assertIs(font_response(impl, url), response)
            stream.assert_called_with(b'font bytes')
            response.setStatusCodeAndReasonPhrase.assert_not_called()
            font_response(impl, FONT_ROOT + 'retired.woff')
            stream.assert_called_with(b'')
            response.setStatusCodeAndReasonPhrase.assert_called_with(410, 'Gone')
            impl.interface.private_closed = True
            font_response(impl, url)
            stream.assert_called_with(b'')

    def test_both_surfaces_embed_font_without_opening_network_or_script_policy(self):
        for content in (markdown_preview('Hello `code`'), editor_html('Hello `code`', 'logistics-editor://test/')):
            with self.subTest(editor='nonce-' in content):
                self.assertIn(MARKER, content)
                styled = style_markdown(content, font_css='@font-face{font-family:LogisticsNative;src:url(data:font/ttf;base64,AA==)}')
                self.assertIn("font-src data:", styled)
                self.assertIn("default-src 'none'", styled)
                self.assertIn('id="logistics-native-font"', styled)
                self.assertNotIn('font-src https:', styled)
                self.assertEqual(styled.count('<script'), content.count('<script'))
                self.assertLess(styled.index('id="logistics-native-font"'), styled.index('</head>'))

    def test_unmarked_books_and_retirement_pages_never_access_native_font(self):
        with patch('mobile.android_markdown_font.native_font') as native:
            for content in ('<p>Document closed.</p>', '<html><head></head><body>EPUB</body></html>'):
                self.assertEqual(style_markdown(content), content)
            native.assert_not_called()

    def test_native_failure_keeps_readable_original_and_reports_the_failure(self):
        content = markdown_preview('Readable offline')
        with patch('mobile.android_markdown_font.native_font', side_effect=RuntimeError('OEM restriction')):
            with self.assertLogs('mobile.android_markdown_font', level='WARNING'):
                self.assertEqual(style_markdown(content), content)
        self.assertEqual(style_markdown(content, font_css=''), content)

    def test_collection_relocates_tables_and_recomputes_whole_font_checksum(self):
        # A tiny collection with the selected face at a nonzero collection index.
        data = bytearray(120)
        struct.pack_into('>4sIIII', data, 0, b'ttcf', 0x10000, 2, 20, 48)
        struct.pack_into('>4sHHHH', data, 48, b'\0\1\0\0', 1, 16, 0, 0)
        struct.pack_into('>4sIII', data, 60, b'head', 0, 96, 12)
        struct.pack_into('>III', data, 96, 123, 456, 999)
        result = standalone_font(bytes(data), 1)
        self.assertEqual(struct.unpack_from('>I', result, 20)[0], 28)
        self.assertEqual(struct.unpack_from('>II', result, 28), (123, 456))
        self.assertEqual(sum(struct.unpack('>10I', result)) & 0xFFFFFFFF, 0xB1B0AFBA)
        self.assertEqual(standalone_font(result), result)
        with self.assertRaises(ValueError):
            standalone_font(bytes(data), 2)
        with self.assertRaises(ValueError):
            standalone_font(b'not a font')

    def test_woff_compression_preserves_every_table_and_alignment(self):
        data = bytearray(44)
        struct.pack_into('>4sHHHH', data, 0, b'\0\1\0\0', 2, 32, 1, 0)
        for index, (tag, raw) in enumerate(((b'aaaa', b'x' * 500), (b'bbbb', b'abc'))):
            struct.pack_into('>4sIII', data, 12 + 16 * index, tag, 17 + index, len(data), len(raw))
            data.extend(raw)
            data.extend(b'\0' * (-len(data) % 4))
        result = web_font(bytes(data))
        self.assertLess(len(result), len(data))
        self.assertEqual(result[:4], b'wOFF')
        self.assertEqual(struct.unpack_from('>I', result, 8)[0], len(result))
        self.assertEqual(struct.unpack_from('>I', result, 16)[0], len(data))
        for index in range(2):
            tag, offset, compressed, original, checksum = struct.unpack_from('>4sIIII', result, 44 + 20 * index)
            source_tag, source_checksum, source_offset, source_length = struct.unpack_from('>4sIII', data, 12 + 16 * index)
            self.assertEqual((tag, checksum, original), (source_tag, source_checksum, source_length))
            self.assertEqual(offset % 4, 0)
            unpacked = result[offset:offset + compressed]
            if compressed < original:
                unpacked = zlib.decompress(unpacked)
            self.assertEqual(unpacked, data[source_offset:source_offset + source_length])
