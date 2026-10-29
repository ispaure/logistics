"""Disposable native Markdown search acceptance probe with synthetic documents."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
import toga
from commonUtils.ui.native.markdown import MarkdownWikiView

BUNDLE = 'io.github.ispaure.logisticsmarkdownsearchqa'


class MarkdownSearchProbe(toga.App):
    def startup(self):
        root = Path(self.paths.cache) / 'wiki'
        root.mkdir(exist_ok=True)
        (root / 'index.md').write_text('# Search Guide\n\nA needle **inside** text. Another NEEDLE.\n\nFind emoji 😀 needle.\n\n[Local link](next.md#target)\n')
        (root / 'next.md').write_text('# Next\n\nNeedle near the beginning.\n\n' + 'Paragraph.\n\n' * 40 + '## Target\n\nA needle at the target.\n')
        self.owner = MarkdownWikiView(root, root / 'index.md')
        self.main_window = toga.MainWindow(title='Markdown search QA')
        self.main_window.content = self.owner.view
        self.main_window.show()
        self.loop.create_task(self.check())

    async def check(self):
        report = {'success': False, 'width': self.main_window.size.width}
        output = Path(self.paths.cache) / 'search-proof'
        output.mkdir(exist_ok=True)
        try:
            owner, search = self.owner, self.owner.page_search
            owner.reflow(self.main_window.size.width)
            report['wide'] = owner.wide
            for _ in range(100):
                if search.ready and await owner.web.evaluate_javascript("!!document.querySelector('h1')"):
                    break
                await asyncio.sleep(.1)
            assert search.ready
            assert owner.mode not in owner.browse.children
            authored_body = "(()=>{const b=document.body.cloneNode(true);b.querySelectorAll('[data-native-search-overlay]').forEach(n=>n.remove());return b.innerHTML;})()"
            body = await owner.web.evaluate_javascript(authored_body)
            owner.search.value = 'needle'
            owner.mode.value = 'Page text'
            owner.filter()
            assert owner.mode in owner.browse.children
            await search.update(reveal=True)
            assert await owner.web.evaluate_javascript('window.__commonutilsMarkdownSearch.library.length') == 3
            owner.show_page_search()
            search.query.value = 'needle'
            await search.update(reveal=True)
            assert search.notice.text == 'This page · 1 of 3', search.notice.text
            await search.update(step=1, reveal=True)
            assert search.notice.text == 'This page · 2 of 3'
            await search.update(step=-1, reveal=True)
            await search.update(step=-1, reveal=True)
            assert search.notice.text == 'This page · 3 of 3'
            search.query.value = 'needle inside'
            await search.update(reveal=True)
            assert search.notice.text == 'This page · 1 of 1'
            search.query.value = '😀 needle'
            await search.update(reveal=True)
            assert search.notice.text == 'This page · 1 of 1'
            search.query.value = '[.*] <script>'
            await search.update()
            assert search.notice.text == 'This page · No matches'
            search.query.value = 'needle'
            await search.update(reveal=True)
            after = await owner.web.evaluate_javascript(authored_body)
            if after != body:
                report['before'], report['after'] = body, after
            assert after == body
            owner.open_page(owner.catalog.root / 'next.md', fragment='target')
            for _ in range(100):
                if search.ready and await owner.web.evaluate_javascript("!!document.getElementById('target')"):
                    break
                await asyncio.sleep(.1)
            await search.update(reveal=False)
            assert await owner.web.evaluate_javascript('window.scrollY') > 0
            report['heading_priority'] = True
            owner.open_page(owner.catalog.root / 'index.md')
            for _ in range(100):
                if search.ready and await owner.web.evaluate_javascript("!!document.getElementById('search-guide')"):
                    break
                await asyncio.sleep(.1)
            await search.update(reveal=True)
            body = await owner.web.evaluate_javascript(authored_body)
            # Search must not consume speech marks or user selection.
            await owner.web.evaluate_javascript("(()=>{if(window.CSS && CSS.highlights && window.Highlight)CSS.highlights.set('logistics-speech',new Highlight());return true;})()")
            search.hide()
            await search.update()
            assert await owner.web.evaluate_javascript('window.__commonutilsMarkdownSearch.page.length') == 0
            assert await owner.web.evaluate_javascript('window.__commonutilsMarkdownSearch.library.length') == 3
            assert await owner.web.evaluate_javascript("!window.CSS || !CSS.highlights || !window.Highlight || CSS.highlights.has('logistics-speech')")
            search.show()
            search.query.value = 'needle'
            await search.update(reveal=True)
            import sys
            if sys.platform == 'ios':
                search.query._impl.native.resignFirstResponder()
            report['css_highlights'] = await owner.web.evaluate_javascript('!!(window.CSS && CSS.highlights && window.Highlight)')
            await owner.web.evaluate_javascript('(()=>{window.__savedSearchHighlight=window.Highlight;window.Highlight=undefined;return true;})()')
            await search.update(reveal=True)
            assert await owner.web.evaluate_javascript("!!document.querySelector('[data-native-search-overlay]')")
            assert await owner.web.evaluate_javascript(authored_body) == body
            report['overlay_fallback'] = True
            await owner.web.evaluate_javascript('(()=>{window.Highlight=window.__savedSearchHighlight;delete window.__savedSearchHighlight;return true;})()')
            await search.update(reveal=True)
            report['css_highlights'] = await owner.web.evaluate_javascript('!!(window.CSS && CSS.highlights && window.Highlight)')
            await asyncio.sleep(.4)
            from tests.logisticsmobile.fixtures import capture_window
            await capture_window(self, output / 'page-search.png')
            owner.show_browse()
            await asyncio.sleep(.4)
            await capture_window(self, output / 'library-search.png')
            report['cases'] = ['library-highlights', 'page-count', 'next-previous-wrap',
                'inline-formatting', 'unicode', 'literal-input', 'DOM-preservation', 'independent-scopes', 'speech-marks-preserved']
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
            try:
                from tests.logisticsmobile.fixtures import capture_window
                await capture_window(self, output / 'failure.png')
            except Exception:
                pass
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('MARKDOWN_SEARCH_PROBE=' + json.dumps(report), flush=True)


def main():
    import sys
    if sys.platform == 'ios':
        from toga_iOS.app import PythonAppDelegate
        class LogisticsSceneAppDelegate(PythonAppDelegate):
            pass
    return MarkdownSearchProbe('Markdown Search QA', BUNDLE)
