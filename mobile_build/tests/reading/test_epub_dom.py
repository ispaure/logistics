"""Optional headless evidence for the immutable chapter's DOM index."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from features.books.mobile.presentation import SCRIPT
from features.books.mobile.typography import css

NODE = os.environ.get('LOGISTICS_NODE') or shutil.which('node')


@skipUnless(NODE, 'Provide Node/Playwright for browser verification')
class EpubDOMTests(TestCase):
    def test_one_walk_for_repeated_unicode_selections_and_disposal(self):
        root = 'https://logistics.invalid/synthetic/'
        html = '<html><head><style>' + css(16, 16, 'light') + '</style><meta name="logistics-reader-root" content="' + root + '"></head><body>'
        html += '<p>First 😀 <strong>passage</strong> ends.</p>' * 2000 + '</body></html>'
        script = SCRIPT.replace('OPTIONS', json.dumps(dict(root=root, offset=0)))
        script = script.replace('window.location.href =', 'window.syntheticNotification =')
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.json'
            path.write_text(json.dumps(dict(html=html, script=script)))
            result = subprocess.run([NODE, str(Path(__file__).with_name('epub_index_dom.cjs')), str(path)],
                                    capture_output=True, text=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['count'], 1)
