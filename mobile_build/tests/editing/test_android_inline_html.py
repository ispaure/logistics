"""Regression coverage for Chromium's encoded inline HTML size limit."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import quote

from mobile.android_inline_html import DATA_URL_LIMIT, DATA_URL_PREFIX, load_inline_html


class InlineHTMLTests(unittest.TestCase):
    def test_html_below_toga_cutoff_can_exceed_chromium_limit_after_encoding(self):
        content = '<p>漢字 %</p>' * 80000
        self.assertLess(len(content), DATA_URL_LIMIT)
        self.assertGreater(len(quote(content)), DATA_URL_LIMIT)
        impl = SimpleNamespace(native=Mock(), loaded_future=object())
        fallback = Mock()
        load_inline_html(impl, 'https://logistics.invalid/notebooks/', content, fallback=fallback)
        impl.native.loadDataWithBaseURL.assert_called_once_with(
            'https://logistics.invalid/notebooks/', content, 'text/html', 'utf-8', None)
        self.assertIsNone(impl.loaded_future)
        fallback.assert_not_called()
        impl.native.loadData.assert_not_called()

    def test_small_content_keeps_existing_toolkit_path(self):
        impl = SimpleNamespace(native=Mock(), loaded_future=object())
        fallback = Mock()
        load_inline_html(impl, 'https://logistics.invalid/', '<p>Hello</p>', fallback=fallback)
        fallback.assert_called_once_with(impl, 'https://logistics.invalid/', '<p>Hello</p>')
        impl.native.loadDataWithBaseURL.assert_not_called()

    def test_data_url_header_counts_toward_limit(self):
        content = 'a' * (DATA_URL_LIMIT - len(DATA_URL_PREFIX))
        impl = SimpleNamespace(native=Mock(), loaded_future=None)
        fallback = Mock()
        load_inline_html(impl, 'https://logistics.invalid/', content, fallback=fallback)
        fallback.assert_not_called()
        impl.native.loadDataWithBaseURL.assert_called_once()
