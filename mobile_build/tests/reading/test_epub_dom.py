"""Optional headless evidence for the immutable chapter's DOM index."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import os
from pathlib import Path
import shutil
import struct
from types import SimpleNamespace
import zlib
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from features.books.mobile.content import chapter_html
from features.books.mobile.presentation import SCRIPT
from features.books.mobile.typography import css

NODE = os.environ.get('LOGISTICS_NODE') or shutil.which('node')


@skipUnless(NODE, 'Provide Node/Playwright for browser verification')
class EpubDOMTests(TestCase):
    def test_compact_vertical_gutters_preserve_horizontal_margin_and_page_counts(self):
        root = 'https://logistics.invalid/synthetic/'
        for margin in (8, 16, 24, 32):
            with self.subTest(margin=margin):
                html = ('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
                        '<style>' + css(24, margin, 'light') + '</style><meta name="logistics-reader-root" content="'
                        + root + '"></head><body><h1>Chapter title</h1>'
                        + '<p>A readable passage. </p>' * 400 + '</body></html>')
                script = SCRIPT.replace('OPTIONS', json.dumps(dict(root=root, offset=0)))
                script = script.replace('window.location.href =', 'window.syntheticNotification =')
                with TemporaryDirectory() as directory:
                    path = Path(directory) / 'fixture.json'
                    path.write_text(json.dumps(dict(html=html, script=script, compactMargin=margin)))
                    result = subprocess.run([NODE, str(Path(__file__).with_name('epub_index_dom.cjs')), str(path)],
                                            capture_output=True, text=True, timeout=40)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_images_fit_columns_after_sanitizing_and_reflow(self):
        root = 'https://logistics.invalid/synthetic/'
        cases = [
            (100, 1800, '<p>{image}</p>', 16, 16, True),
            (1200, 1800, '<blockquote><p>{image}</p></blockquote>', 32, 32, True),
            (1800, 100, '<div>{image}</div>', 12, 8, True),
            (100, 1800, '<p>' + 'Before the illustration. ' * 35 + '</p><p>{image}</p><p id="after">After the illustration.</p>', 16, 16, False),
            (320, 200, '<p>{image}</p>', 16, 16, True),
        ]
        for width, height, body, size, margin, single_cover in cases:
            with self.subTest(width=width, height=height, size=size, margin=margin, single_cover=single_cover):
                def chunk(kind, data):
                    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
                raster = (b'\x89PNG\r\n\x1a\n'
                          + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                          + chunk(b'IDAT', zlib.compress((b'\x00' + b'\x00\x00\x80' * width) * height))
                          + chunk(b'IEND', b''))
                resources = {'chapter.xhtml': ('<html><body>' + body.format(image='<img src="cover.png"/>')
                                              + '</body></html>').encode(), 'cover.png': raster}
                book = SimpleNamespace(spine=['chapter.xhtml'], members=resources,
                                       resource_sizes={key: len(value) for key, value in resources.items()},
                                       read=resources.__getitem__, values=lambda name: [])
                html = chapter_html(book, 0, size, margin=margin, theme='light')
                self.assertIn('data:image/png;base64,', html)
                html = html.replace('</head>', '<meta name="logistics-reader-root" content="' + root + '"></head>')
                script = SCRIPT.replace('OPTIONS', json.dumps(dict(root=root, offset=0)))
                script = script.replace('window.location.href =', 'window.syntheticNotification =')
                with TemporaryDirectory() as directory:
                    path = Path(directory) / 'fixture.json'
                    path.write_text(json.dumps(dict(html=html, script=script, images=True, singleCover=single_cover,
                                                    naturalWidth=width, naturalHeight=height, delayImage=width == 1200)))
                    result = subprocess.run([NODE, str(Path(__file__).with_name('epub_index_dom.cjs')), str(path)],
                                            capture_output=True, text=True, timeout=40)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_one_walk_for_repeated_unicode_selections_and_disposal(self):
        root = 'https://logistics.invalid/synthetic/'
        html = ('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
                '<style>' + css(16, 16, 'light') + '</style><meta name="logistics-reader-root" content="' + root + '"></head><body>')
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
