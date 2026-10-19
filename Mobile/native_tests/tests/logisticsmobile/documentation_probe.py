"""Documentation navigation on native hosts using an isolated app/storage ID."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from logisticsmobile.app import LogisticsMobile
import toga
from types import SimpleNamespace


class DocumentationProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('documentation-proof-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        if getattr(self, '_documentation_probe_started', False):
            return
        self._documentation_probe_started = True
        from tests.logisticsmobile.fixtures import capture_window
        report = {'success': False, 'host': type(self).__name__, 'cases': []}
        output = Path(self.paths.cache) / 'documentation-evidence'
        output.mkdir(exist_ok=True)
        try:
            await asyncio.sleep(1)
            self.show_settings()
            if hasattr(self, 'settings_navigation'):
                self.settings_navigation.choose('Help')
                box = self.settings_navigation.sections['Help']
            else:
                box = self.body.children[0].content
            button = next(child for child in box.children if getattr(child, 'text', '') == 'Mobile documentation')
            button.on_press()
            owner = self.documentation
            root = Path(__file__).parent / 'help'
            scope = root / 'docs'
            assert owner.path == (scope / 'user_mobile/user_mobile.md').resolve()
            assert owner.catalog.root == scope.resolve()
            report['cases'].append('documentation_entry_opens_mobile_guide_and_logistics_tree')
            await asyncio.sleep(.7)
            assert await owner.web.evaluate_javascript('document.querySelector("h1").textContent') == 'Logistics on mobile'
            report['cases'].append('native_webview_renders_expected_article')
            await capture_window(self, output / 'mobile-guide.png')
            owner.show_browse()
            def choose(title):
                row = next(row for row in owner.rows.children if row.children[-1].text.removeprefix('✓ ') == title)
                row.children[-1].on_press()
            choose('Logistics on mobile')
            # Expand the audience folder and select the actual Workspaces row.
            owner.show_browse()
            row = next(row for row in owner.rows.children if row.children[-1].text.removeprefix('✓ ') == 'Logistics on mobile')
            if row.children[1].text == '+':
                row.children[1].on_press()
            choose('Workspaces on mobile')
            assert owner.path == (scope / 'user_mobile/folder_hub/folder_hub.md').resolve()
            assert owner.catalog.root == scope.resolve()
            assert owner.up()
            assert owner.path == (scope / 'user_mobile/user_mobile.md').resolve()
            report['cases'].append('native_folder_row_landing_and_up')
            # Follow an actual rendered HTML link, allowing WKWebView's navigation
            # delegate to resolve its encoded relative target.
            await asyncio.sleep(.6)
            clicked = await owner.web.evaluate_javascript('''(function(){const a=Array.from(document.querySelectorAll('a')).find(a=>a.textContent==='Chat on mobile');if(!a)return false;a.click();return true;})()''')
            assert clicked
            feature_scope = root / 'Python/features/lm/docs'
            target = feature_scope / 'user_mobile/conversations.md'
            for _ in range(60):
                if owner.path == target.resolve(): break
                await asyncio.sleep(.1)
            assert owner.path == target.resolve(), str(owner.path)
            assert owner.catalog.root == feature_scope.resolve()
            assert all(feature_scope.resolve() in page.parents for page in owner.catalog.pages)
            assert any(row.children[-1].text == '✓ Chat on mobile' for row in owner.rows.children)
            report['cases'].append('rendered_link_switches_to_feature_tree_and_reveals_article')
            owner.show_browse()
            await asyncio.sleep(.4)
            row_width = float(owner.rows.children[0].children[-1]._impl.native.frame.size.width)
            report['tree_title_width'] = row_width
            assert row_width >= 180, row_width
            await capture_window(self, output / 'feature-tree.png')
            assert owner.back()
            assert owner.catalog.root == scope.resolve()
            assert owner.forward()
            assert owner.catalog.root == feature_scope.resolve()
            report['cases'].append('native_back_forward_restore_scopes')
            report['width'] = self.main_window.size.width
            report['wide'] = owner.wide
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('DOCUMENTATION_PROBE=' + json.dumps(report), flush=True)


def main():
    return DocumentationProbe('Docs Probe', 'io.github.ispaure.logisticsdocsprobe')


class StandaloneDocumentationProbe(DocumentationProbe):
    """Exercise the native documentation host without unrelated editor startup."""
    def startup(self):
        self.preferences = SimpleNamespace(values={'font_size': '16'})
        self.adaptive = SimpleNamespace(content_width=lambda *args, **kwargs: self.main_window.size.width)
        self.main_window = toga.MainWindow(title='Documentation viewer proof')
        self.show_settings()
        self.main_window.show()
        self.loop.create_task(self.probe())

    def show_settings(self):
        from logisticsmobile.documentation_ui import show_documentation
        box = toga.Box(children=[toga.Button('Mobile documentation', on_press=lambda widget, **kw: show_documentation(self))])
        scroll = toga.ScrollContainer(content=box)
        self.body = toga.Box(children=[scroll])
        self.main_window.content = self.body

    def show_view(self, view, **kwargs):
        self.main_window.content = view
        return True


def standalone_main():
    return StandaloneDocumentationProbe('Docs Viewer Probe', 'io.github.ispaure.logisticsdocsviewerprobe')
