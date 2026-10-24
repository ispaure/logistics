"""Exercise production mobile live editing in a real browser document."""
import ast
from html import escape
import json
import os
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
from pathlib import Path
import re
import unittest
from uuid import uuid4

from markdown_it import MarkdownIt
from commonUtils.formats.markdown.editing import web_patterns
from commonUtils.ui.appearance.formatting_glyphs import formatting_svg
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView


def editor_html(source):
    # Load the HTML builder without importing/initializing the Toga backend.
    owner = Path(__file__).parents[1] / 'features/text_editor/mobile'
    namespace = dict(escape=escape, json=json, re=re, uuid4=uuid4,
                     MarkdownIt=MarkdownIt, web_patterns=web_patterns, formatting_svg=formatting_svg)
    for filename, name in [('markdown_script.py', 'SCRIPT'), ('markdown_live_script.py', 'LIVE_SCRIPT'),
                           ('markdown_style.py', 'EDITOR_CSS')]:
        tree = ast.parse((owner / filename).read_text())
        namespace[name] = next(ast.literal_eval(node.value) for node in tree.body
                               if isinstance(node, ast.Assign) and node.targets[0].id == name)
    namespace['_SCRIPT'] = namespace['SCRIPT']
    tree = ast.parse((owner / 'markdown_editor.py').read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('editor_html', 'editor_blocks')]
    exec(compile(tree, 'markdown_editor.py', 'exec'), namespace)
    return namespace['editor_html'](source, 'logistics-editor://test/')


class EditorPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, main_frame):
        return url.scheme() != 'logistics-editor'


class MobileMarkdownEditingDOMTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.view = QWebEngineView()
        self.addCleanup(self.view.deleteLater)
        self.view.resize(480, 700)
        self.page = EditorPage(self.view)
        self.view.setPage(self.page)
        self.view.show()
        self.addCleanup(self.page.deleteLater)
        self.loaded = False
        self.page.loadFinished.connect(lambda ok: setattr(self, 'loaded', ok))
        self.page.setHtml(editor_html('Untouched **bold**\n\n'))
        self.wait_until(lambda: self.loaded, timeout=10)
        self.evaluate("""const section=root.lastElementChild; section.focus();
            const range=document.createRange();range.selectNodeContents(section);range.collapse(true);
            getSelection().removeAllRanges();getSelection().addRange(range);""")

    def evaluate(self, script):
        result = []
        self.page.runJavaScript('(() => {' + script + '})()', lambda value: result.append(value))
        self.wait_until(lambda: bool(result), timeout=5)
        return result[0]

    def type(self, text):
        self.evaluate('document.execCommand("insertText", false, ' + json.dumps(text) + ')')

    def source(self):
        return self.evaluate('return JSON.stringify(window.markdownSnapshot())')

    def test_typed_heading_and_bold_render_and_keep_markdown(self):
        self.type('# Something')
        self.assertEqual(self.evaluate('return root.lastElementChild.querySelector("[data-live-heading]")?.dataset.liveHeading'), '1')
        self.type(' **bold**')
        self.assertIn('# Something **bold**', self.source())
        self.assertEqual(self.evaluate('return root.lastElementChild.querySelector(".live-bold")?.textContent'), 'bold')
        self.assertNotIn('Untouched', self.source())

    def test_selection_wraps_twice_and_undo_preserves_text(self):
        self.type('😀 words')
        self.evaluate('''const selected=document.createRange();selected.selectNodeContents(root.lastElementChild);
            getSelection().removeAllRanges();getSelection().addRange(selected);return getSelection().toString();''')
        self.assertEqual(self.evaluate('return getSelection().toString()'), '😀 words', self.evaluate('return root.lastElementChild.innerHTML'))
        for expected in ('*😀 words*', '**😀 words**'):
            self.evaluate('root.dispatchEvent(new InputEvent("beforeinput", {bubbles:true,cancelable:true,inputType:"insertText",data:"*"}))')
            self.assertEqual(self.evaluate('return root.lastElementChild.textContent'), expected)
            self.assertEqual(self.evaluate('return getSelection().toString()'), '😀 words')
        self.evaluate('command("undo")')
        self.assertEqual(self.evaluate('return root.lastElementChild.textContent'), '*😀 words*')

    def test_character_typing_deletion_redo_and_toolbar_formatting(self):
        for char in '**bold**':
            self.type(char)
        self.assertIn('**bold**', self.source())
        self.assertTrue(self.evaluate('return Boolean(root.lastElementChild.querySelector(".live-bold"))'))
        self.evaluate('document.execCommand("delete")')
        self.assertEqual(self.evaluate('return root.lastElementChild.textContent'), '**bold*')
        self.assertFalse(self.evaluate('return Boolean(root.lastElementChild.querySelector(".live-bold"))'))
        self.evaluate('command("undo")')
        self.assertEqual(self.evaluate('return root.lastElementChild.textContent'), '**bold**')
        self.evaluate('command("redo")')
        self.assertEqual(self.evaluate('return root.lastElementChild.textContent'), '**bold*')
        self.evaluate('const r=document.createRange();r.selectNodeContents(root.lastElementChild);'
                      'getSelection().removeAllRanges();getSelection().addRange(r);command("italic");')
        self.assertIn('***bold**', self.source())

    def test_imported_escaped_markers_stay_literal_when_appending_syntax(self):
        self.page.setHtml(editor_html(r'\*literal\*'))
        self.loaded = False
        self.wait_until(lambda: self.loaded, timeout=10)
        self.evaluate('const section=root.firstElementChild;section.focus();'
                      'const r=document.createRange();r.selectNodeContents(section);r.collapse(false);'
                      'getSelection().removeAllRanges();getSelection().addRange(r);')
        self.type(' **new**')
        patch = json.loads(self.source())
        self.assertIn(r'\*literal\* **new**', patch['changes'][0][1])
        self.assertFalse(self.evaluate('return Boolean(root.firstElementChild.querySelector(".live-italic"))'))

    def test_soft_keyboard_composition_and_untouched_code(self):
        self.evaluate('const section=root.lastElementChild;section.innerHTML="<p>**語😀**</p>";'
                      'const r=document.createRange();r.selectNodeContents(section);r.collapse(false);'
                      'getSelection().removeAllRanges();getSelection().addRange(r);'
                      'section.dispatchEvent(new CompositionEvent("compositionend", {bubbles:true}));')
        self.assertIn('**語😀**', self.source())
        self.assertEqual(self.evaluate('return root.lastElementChild.querySelector(".live-bold").textContent'), '語😀')

    def test_code_escapes_incomplete_and_intraword_markers(self):
        for text in (r'\*literal\* foo_bar_baz **unfinished', '`**literal**`'):
            self.evaluate('return root.lastElementChild.innerHTML="<p><br></p>"; root.lastElementChild.focus();'
                          'const r=document.createRange();r.selectNodeContents(root.lastElementChild);'
                          'getSelection().removeAllRanges();getSelection().addRange(r);')
            self.type(text)
            self.assertFalse(self.evaluate('return Boolean(root.lastElementChild.querySelector(".live-bold,.live-italic"))'))
            self.assertIn(text, json.loads(self.source())['changes'][-1][1])


if __name__ == '__main__':
    unittest.main()
