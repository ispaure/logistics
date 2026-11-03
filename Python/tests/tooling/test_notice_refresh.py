"""Upstream documentation navigation must not be mistaken for license text."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logistics_build.refresh_notices import refresh_webengine


class NoticeRefreshTests(unittest.TestCase):
    def test_webengine_keeps_license_blocks_and_checks_engine_version(self):
        index = b'<title>Qt WebEngine 6.140.0</title><a href="qtwebengine-3rdparty-example.html">Example</a>'
        article = b'<title>Example | Qt WebEngine 6.140.0</title><nav>Do not bundle navigation</nav><h1>Example library</h1><pre>Copyright Example &amp; contributors\nFull license text &amp;quot;AS IS&amp;quot;</pre>'
        with TemporaryDirectory() as temporary, patch('logistics_build.refresh_notices.fetch', side_effect=[index, article]):
            result = refresh_webengine('6.140.0', Path(temporary), 'https://example.org/qtwebengine-licensing.html')
            component = result['components'][0]
            self.assertEqual(component['name'], 'Example library')
            self.assertIn('Copyright Example & contributors', component['text'])
            self.assertNotIn('navigation', component['text'])
            self.assertIn('"AS IS"', component['text'])
            self.assertFalse(component['missing_notice'])
            self.assertEqual(json.loads((Path(temporary) / 'qtwebengine-source-notices.json').read_text())['version'], '6.140.0')
        with TemporaryDirectory() as temporary, patch('logistics_build.refresh_notices.fetch', return_value=index):
            with self.assertRaisesRegex(ValueError, 'version changed'):
                refresh_webengine('6.141.0', Path(temporary), 'https://example.org/index.html')
