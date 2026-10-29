"""Exercise the mobile speech extractor against a real rendered document."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import ast
import json
from pathlib import Path
import unittest

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.native.markdown_preview import markdown_preview
from PySide6.QtWebEngineCore import QWebEnginePage


class MarkdownSpeechDOMTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        # Importing the mobile module would initialize Toga. Read its actual JS
        # constant instead so this verifies production code without mobile UI.
        source = Path(__file__).parents[1] / 'mobile/markdown_speech.py'
        constants = {node.targets[0].id: ast.literal_eval(node.value)
                     for node in ast.parse(source.read_text()).body
                     if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                     and isinstance(node.value, ast.Constant)}
        self.script = constants['SOURCE_SCRIPT']
        self.highlight = constants['HIGHLIGHT_SCRIPT']
        self.page = QWebEnginePage()
        self.addCleanup(self.page.deleteLater)
        self.loaded = False
        self.page.loadFinished.connect(self.loaded_page)
        self.page.setHtml(markdown_preview(
            '# Heading\n\n[Readable **label**](https://example.invalid/hidden) '
            'and *emphasis*.\n\n[Reference][target]\n\n'
            '[target]: https://example.invalid/reference\n\n'
            'Visible https://visible.invalid/path\n\n'
            '`[literal](https://code.invalid)`\n\nFirst  \nSecond'))
        self.wait_until(lambda: self.loaded, timeout=10, message='Markdown DOM loads')

    def loaded_page(self, success):
        self.loaded = success

    def evaluate(self, script):
        result = []
        self.page.runJavaScript(script, lambda value: result.append(value))
        self.wait_until(lambda: bool(result), timeout=5, message='Speech JS completes')
        return result[0]

    def test_rendered_links_formatting_and_line_breaks(self):
        text = json.loads(self.evaluate(self.script))
        self.assertIn('Readable label and emphasis.', text)
        self.assertIn('Reference', text)
        self.assertNotIn('https://example.invalid', text)
        self.assertIn('https://visible.invalid/path', text)
        self.assertIn('[literal](https://code.invalid)', text)
        self.assertIn('First\nSecond', text)

    def test_selected_link_label_and_highlight_use_rendered_offsets(self):
        self.evaluate("""(() => {
            const p=document.querySelector('p'), range=document.createRange();
            range.setStart(p.firstChild.firstChild, 2);
            range.setEnd(p.querySelector('strong').firstChild, 3);
            getSelection().removeAllRanges();getSelection().addRange(range);
        })()""")
        self.assertEqual(json.loads(self.evaluate(self.script)), 'adable lab')
        self.evaluate(self.highlight.replace('START', '7').replace('END', '10'))
        self.assertEqual(self.evaluate("""(() => {
            const range=[...CSS.highlights.get('logistics-speech')][0];
            return range.toString();
        })()"""), 'lab')

    def test_hidden_content_is_excluded(self):
        self.evaluate("""(() => {
            for(const style of ['display:none','visibility:hidden']) {
                const p=document.createElement('p');p.style=style;
                p.textContent='Hidden URL https://hidden.invalid';
                document.body.appendChild(p);
            }
        })()""")
        self.assertNotIn('Hidden URL', json.loads(self.evaluate(self.script)))


if __name__ == '__main__':
    unittest.main()
