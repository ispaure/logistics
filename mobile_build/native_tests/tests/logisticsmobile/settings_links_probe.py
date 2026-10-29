"""Disposable native Settings hierarchy and Markdown link-dialog review."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback

import toga
from mobile.app import LogisticsMobile
from tests.logisticsmobile.fixtures import capture_window


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'isolated-settings-links'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'settings-links-evidence'
        output.mkdir(exist_ok=True)
        result = dict(success=False)
        try:
            for mode in (1, 2):
                if type(self._impl).__module__.startswith('toga_iOS.'):
                    self.main_window._impl.native.overrideUserInterfaceStyle = mode
                self.refresh_native_theme()
                self.show_settings()
                await asyncio.sleep(.3)
                for button in self.settings_navigation.buttons.values():
                    assert not button._impl._surface_roles[2]
                await capture_window(self, output / f'categories-{mode}.png')
                self.settings_navigation.choose('App')
                await asyncio.sleep(.3)
                await capture_window(self, output / f'options-{mode}.png')
            document = self.store.create('Links.md', b'Alpha beta gamma')
            self.refresh_documents()
            self.open_document(document.id)
            self.show_documents(edit=True)
            web = self.editor_view.formatted.view
            await asyncio.sleep(.7)
            checked = await web.evaluate_javascript("""JSON.stringify((() => {
                const root = document.getElementById('document');
                const original = root.textContent;
                const section = root.querySelector('[contenteditable=true]');
                const text = section.querySelector('p').firstChild;
                const select = () => {
                    section.focus();
                    const range = document.createRange(); range.setStart(text, 6); range.setEnd(text, 10);
                    const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
                };
                const dialog = document.getElementById('link-dialog');
                const target = document.getElementById('link-target');
                const open = document.getElementById('show-link');
                const check = (value, message) => { if (!value) throw Error(message); };
                check(!dialog.open && !document.querySelector('nav input'), 'URL field visible in toolbar');
                select(); open.click();
                check(dialog.open && document.activeElement === target, 'URL prompt did not receive focus');
                target.value = 'https://cancelled.invalid'; document.getElementById('cancel-link').click();
                check(!dialog.open && !root.querySelector('a') && getSelection().toString() === 'beta', 'Cancel changed text or selection');
                open.click(); target.value = 'javascript:alert(1)'; document.getElementById('apply-link').click();
                check(dialog.open && !root.querySelector('a') && document.getElementById('link-error').textContent, 'Invalid URL was accepted');
                target.value = 'https://example.invalid/my path';
                target.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
                const anchor = root.querySelector('a');
                check(!dialog.open && anchor.textContent === 'beta', 'Selected text was not linked');
                check(anchor.getAttribute('href') === 'https://example.invalid/my%20path', 'URL was not preserved');
                check(root.textContent === original, 'Link insertion changed adjacent text');
                return {cancel:true, invalid_url:true, selection:true, enter:true, toolbar_icon_only:true};
            })())""")
            result['checks'] = json.loads(checked)
            await asyncio.sleep(.3)
            await web.evaluate_javascript("document.querySelector('details').open=true; document.getElementById('show-link').click();")
            await asyncio.sleep(.3)
            visible = await web.evaluate_javascript("""(() => {
                const dialog = document.getElementById('link-dialog').getBoundingClientRect();
                return ['link-target', 'cancel-link', 'apply-link'].every(id => {
                    const rect = document.getElementById(id).getBoundingClientRect();
                    return rect.top >= dialog.top && rect.bottom <= dialog.bottom && rect.bottom <= innerHeight;
                });
            })()""")
            assert visible, 'Link dialog actions are clipped in the keyboard-sized viewport'
            await capture_window(self, output / 'link-dialog.png')
            await web.evaluate_javascript("document.getElementById('cancel-link').click();")
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(result, indent=2))


def main():
    return Probe('Settings and Links Probe', 'io.github.ispaure.logisticssettingslinksprobe')
