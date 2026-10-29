"""Measure the production mobile HTML with real raster decoding and panel resizing."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import ast
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
from PySide6.QtWebEngineWidgets import QWebEngineView
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui.native.markdown_preview import markdown_preview
from tests.test_mobile_markdown_editing_dom import editor_html


class MarkdownImageLayoutDOMTests(QtTestCase):
    def evaluate(self, script):
        values = []
        self.web.page().runJavaScript(script, values.append)
        self.wait_until(lambda: bool(values))
        return values[0]

    def test_formats_fit_reading_and_formatted_panels_without_tall_blank_space(self):
        self.web = QWebEngineView()
        self.web.show()
        loaded = []
        self.web.loadFinished.connect(loaded.append)
        style_path = Path(__file__).parents[2] / 'features/text_editor/mobile/markdown_style.py'
        tree = ast.parse(style_path.read_text())
        reading_css = next(ast.literal_eval(node.value) for node in tree.body
                           if isinstance(node, ast.Assign) and node.targets[0].id == 'READING_CSS')
        for kind in ('PNG', 'JPEG', 'WEBP', 'GIF'):
            buffer = BytesIO()
            Image.new('RGB', (1600, 800), 'blue').save(buffer, kind)
            source = '![[photo.' + kind.lower() + '|1200x600]]\n\nFollowing text\n'
            image_source = lambda target: ('image/' + kind.lower(), buffer.getvalue())
            for mode in ('reading', 'formatted'):
                html = (markdown_preview(source, image_source=image_source, stylesheet=reading_css)
                        if mode == 'reading' else editor_html(source, image_source=image_source))
                loaded.clear()
                self.web.setHtml(html)
                self.wait_until(lambda: bool(loaded), timeout=15)
                self.assertTrue(loaded[-1])
                self.wait_until(lambda: self.evaluate("Boolean(document.querySelector('img')?.naturalWidth)"))
                for width in (700, 320, 500):
                    with self.subTest(kind=kind, mode=mode, width=width):
                        self.web.resize(width, 700)
                        self.wait_until(lambda: self.evaluate("innerWidth") == width)
                        measurement = json.loads(self.evaluate('''JSON.stringify((()=>{
                            const image=document.querySelector('img'), r=image.getBoundingClientRect();
                            const following=[...document.querySelectorAll('p')].find(p=>p.textContent==='Following text');
                            return {width:r.width,height:r.height,right:r.right,viewport:innerWidth,
                                gap:following.getBoundingClientRect().top-r.bottom};
                        })())'''))
                        self.assertLessEqual(measurement['right'], measurement['viewport'])
                        self.assertLessEqual(measurement['width'], width)
                        self.assertAlmostEqual(measurement['width'] / measurement['height'], 2, delta=.03)
                        self.assertGreaterEqual(measurement['gap'], 0)
                        self.assertLess(measurement['gap'], 70)
