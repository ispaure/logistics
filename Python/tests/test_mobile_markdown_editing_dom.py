"""Exercise production mobile live editing in a real browser document."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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


def editor_html(source, *, image_source=None):
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
    return namespace['editor_html'](source, 'logistics-editor://test/', image_source=image_source)


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

    def select_offsets(self, first, last=None, section='root.lastElementChild'):
        last = first if last is None else last
        self.evaluate(f"""const section={section};section.focus();
            const range=document.createRange();range.setStart(...textPosition(section,{first}));
            range.setEnd(...textPosition(section,{last}));
            getSelection().removeAllRanges();getSelection().addRange(range);
            refreshSyntaxVisibility();""")

    def marker_sizes(self, section='root.lastElementChild'):
        return json.loads(self.evaluate(f"""return JSON.stringify([...{section}.querySelectorAll('.live-marker')]
            .map(marker => parseFloat(getComputedStyle(marker).fontSize)));"""))

    def test_inline_visibility_matches_desktop_boundaries_and_selection(self):
        from commonUtils.formats.markdown.editing import syntax_active
        text = '😀 **bold** and *other* after'
        self.type(text)
        before = json.loads(self.source())['changes']
        html = self.evaluate('return root.lastElementChild.innerHTML')
        # Section offsets include one paragraph boundary; the emoji uses UTF-16.
        for first, last in ((0, 0), (4, 4), (12, 12), (13, 13), (3, 4), (3, 5),
                            (12, 13), (11, 13), (18, 18), (0, 30)):
            with self.subTest(first=first, last=last):
                self.select_offsets(first, last)
                sizes = self.marker_sizes()
                self.assertEqual([size > 0 for size in sizes],
                    [syntax_active(4, 12, first, last)] * 2 +
                    [syntax_active(17, 24, first, last)] * 2)
        self.assertEqual(json.loads(self.source())['changes'], before)
        self.assertEqual(self.evaluate('return root.lastElementChild.innerHTML'), html)
        self.evaluate('command("undo")')
        self.assertEqual(self.evaluate('return root.lastElementChild.textContent'), '')

    def test_heading_hides_when_caret_moves_to_next_paragraph_in_same_section(self):
        self.type('# Heading **bold**')
        self.evaluate('document.execCommand("insertParagraph")')
        self.type('elsewhere')
        self.evaluate('refreshSyntaxVisibility()')
        self.assertTrue(all(size == 0 for size in self.marker_sizes()))
        self.select_offsets(3)
        self.assertGreater(self.marker_sizes()[0], 0)
        self.assertEqual(self.marker_sizes()[1:], [0, 0])

    def test_loaded_markers_reveal_and_navigation_preserves_original_source(self):
        self.loaded = False
        self.page.setHtml(editor_html('# Heading **bold**\r\n\r\nOther'))
        self.wait_until(lambda: self.loaded, timeout=10)
        self.assertTrue(all(size == 0 for size in self.marker_sizes('root.firstElementChild')))
        before = json.loads(self.source())['changes']
        self.select_offsets(4, section='root.firstElementChild')
        self.assertGreater(self.marker_sizes('root.firstElementChild')[0], 0)
        self.assertEqual(self.marker_sizes('root.firstElementChild')[1:], [0, 0])
        self.select_offsets(1, section='root.children[2]')
        self.assertTrue(all(size == 0 for size in self.marker_sizes('root.firstElementChild')))
        self.assertEqual(json.loads(self.source())['changes'], before)

    def test_toolbar_bold_uses_cursor_sensitive_source_and_undo(self):
        self.type('words after')
        self.select_offsets(1, 6)
        self.evaluate('command("bold")')
        self.assertIn('**words** after', self.source())
        self.assertTrue(all(size > 0 for size in self.marker_sizes()))
        self.select_offsets(15)
        self.assertEqual(self.marker_sizes(), [0, 0])
        self.evaluate('command("undo")')
        self.assertEqual(self.evaluate('return root.lastElementChild.textContent'), 'words after')
        self.evaluate('command("redo");refreshSyntaxVisibility()')
        self.assertEqual(len(self.marker_sizes()), 2)
        self.select_offsets(15)
        self.assertEqual(self.marker_sizes(), [0, 0])

    def test_toolbar_preserves_imported_literal_punctuation(self):
        self.loaded = False
        self.page.setHtml(editor_html(r'\*literal\*'))
        self.wait_until(lambda: self.loaded, timeout=10)
        self.evaluate('const section=root.firstElementChild;section.focus();'
                      'const r=document.createRange();r.selectNodeContents(section);'
                      'getSelection().removeAllRanges();getSelection().addRange(r);command("bold")')
        self.assertIn(r'**\*literal\***', json.loads(self.source())['changes'][0][1])
        self.assertFalse(self.evaluate('return Boolean(root.firstElementChild.querySelector(".live-italic"))'))

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

    def block_style(self, style):
        self.evaluate('const menu=document.getElementById("block-style");menu.value=' + json.dumps(style) +
                      ';menu.dispatchEvent(new Event("change", {bubbles:true}));')

    def test_toolbar_replaces_typed_heading_and_paragraph_removes_it(self):
        self.type('# Title **bold** 😀')
        for style, prefix, scale in [('h1', '# ', 2), ('h2', '## ', 1.55),
                                     ('h1', '# ', 2), ('h1', '# ', 2), ('p', '', 1)]:
            with self.subTest(style=style):
                self.block_style(style)
                self.assertEqual(json.loads(self.source())['changes'][-1][1].strip(),
                                 prefix + 'Title **bold** 😀')
                sizes = json.loads(self.evaluate('''const section=root.lastElementChild;
                    const node=[...section.querySelectorAll("*")].find(el=>el.textContent==="Title ") || section.firstElementChild;
                    return JSON.stringify([parseFloat(getComputedStyle(node).fontSize),
                        parseFloat(getComputedStyle(root).fontSize)]);'''))
                self.assertAlmostEqual(sizes[0] / sizes[1], scale, places=2)
        self.assertFalse(self.evaluate('return Boolean(root.lastElementChild.querySelector("[data-live-heading]"))'))

    def test_heading_conversion_is_one_undo_step_and_keeps_selection(self):
        self.type('## 😀 Title')
        self.evaluate('const r=document.createRange();r.selectNodeContents(root.lastElementChild);'
                      'getSelection().removeAllRanges();getSelection().addRange(r);')
        self.block_style('h3')
        self.assertEqual(self.evaluate('return getSelection().toString()'), '😀 Title')
        self.assertEqual(json.loads(self.source())['changes'][-1][1].strip(), '### 😀 Title')
        self.evaluate('command("undo")')
        self.assertEqual(self.evaluate('return root.lastElementChild.textContent'), '## 😀 Title')
        self.evaluate('command("redo")')
        self.assertEqual(json.loads(self.source())['changes'][-1][1].strip(), '### 😀 Title')

    def test_live_heading_level_updates_and_does_not_leak_to_next_paragraph(self):
        self.type('# Title')
        self.evaluate('const node=root.lastElementChild.querySelector(".live-marker").firstChild;'
                      'const r=document.createRange();r.setStart(node,0);r.collapse(true);'
                      'getSelection().removeAllRanges();getSelection().addRange(r);')
        self.type('##')
        self.assertEqual(self.evaluate('return root.lastElementChild.querySelector("[data-live-heading]").dataset.liveHeading'), '3')
        self.evaluate('const r=document.createRange();r.selectNodeContents(root.lastElementChild);r.collapse(false);'
                      'getSelection().removeAllRanges();getSelection().addRange(r);document.execCommand("insertParagraph");')
        self.type('body')
        self.assertEqual(self.evaluate('return getComputedStyle(root.lastElementChild.lastElementChild).fontSize'),
                         self.evaluate('return getComputedStyle(root).fontSize'))

    def test_loaded_heading_with_link_keeps_literal_hash_and_inline_content(self):
        self.loaded = False
        self.page.setHtml(editor_html('## Literal # [link](https://example.com) **bold**\n'))
        self.wait_until(lambda: self.loaded, timeout=10)
        self.evaluate('const section=root.firstElementChild;section.focus();'
                      'const r=document.createRange();r.selectNodeContents(section);r.collapse(false);'
                      'getSelection().removeAllRanges();getSelection().addRange(r);')
        for style, prefix in [('h1', '# '), ('h6', '###### '), ('p', '')]:
            self.block_style(style)
            self.assertEqual(json.loads(self.source())['changes'][0][1].strip(),
                             prefix + 'Literal # [link](https://example.com) **bold**')
            self.assertFalse(self.evaluate('return Boolean(root.firstElementChild.querySelector("[data-live-heading]"))'))

    def test_heading_selection_excludes_adjacent_blocks_and_scales_with_font(self):
        self.type('# First')
        self.evaluate('document.execCommand("insertParagraph")')
        self.type('## Second')
        self.evaluate('document.body.style.fontSize="32px";'
                      'const section=root.lastElementChild;const r=document.createRange();'
                      'r.setStart(section,1);r.setEnd(section,2);'
                      'getSelection().removeAllRanges();getSelection().addRange(r);')
        self.block_style('h3')
        self.assertEqual(json.loads(self.source())['changes'][-1][1].strip(), '# First\n\n### Second')
        self.assertEqual(self.evaluate('return getComputedStyle(root.lastElementChild.lastElementChild).fontSize'), '40px')
        self.assertEqual(self.evaluate('return root.lastElementChild.firstElementChild.dataset.liveHeading'), '1')

    def test_typed_heading_to_code_or_quote_does_not_retain_heading_size(self):
        for style in ['pre', 'blockquote']:
            with self.subTest(style=style):
                self.type('# Title')
                self.block_style(style)
                self.assertFalse(self.evaluate('return Boolean(root.lastElementChild.querySelector("[data-live-heading]"))'))
                source = json.loads(self.source())['changes'][-1][1].strip()
                self.assertEqual(source, '```\nTitle\n```' if style == 'pre' else '> Title')
                self.evaluate('command("undo");command("undo")')

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

    def test_enter_moves_caret_to_new_paragraph_and_keeps_following_text_there(self):
        self.type('first')
        self.evaluate('document.execCommand("insertParagraph")')
        self.type('second')
        source = json.loads(self.source())['changes'][-1][1]
        self.assertIn('first\n\nsecond', source)
        self.assertEqual(self.evaluate('return getSelection().anchorNode.textContent'), 'second')
        self.evaluate('command("undo")')
        self.evaluate('command("redo")')
        self.type('!')
        self.assertIn('first\n\nsecond!', json.loads(self.source())['changes'][-1][1])

    def test_shift_enter_and_blank_paragraphs_keep_distinct_caret_positions(self):
        self.type('line')
        self.evaluate('document.execCommand("insertLineBreak")')
        self.type('next')
        self.assertIn('line\nnext', json.loads(self.source())['changes'][-1][1])
        self.evaluate('document.execCommand("insertParagraph");document.execCommand("insertParagraph")')
        self.type('last')
        source = json.loads(self.source())['changes'][-1][1]
        self.assertRegex(source, r'next\n{3,}last')

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
