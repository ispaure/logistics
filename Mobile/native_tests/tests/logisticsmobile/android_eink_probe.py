"""Three-launch Android E Ink opt-in, restoration and private-WebView checks."""
import asyncio
import json
import os
from pathlib import Path
import traceback
import toga
from toga.style import Pack
from logisticsmobile.app import LogisticsMobile
from logisticsmobile import palette
from logisticsmobile.preferences import Preferences
from .fixtures import capture_window

BUNDLE = 'io.github.ispaure.logisticsremoteprobe'
DRAFT = 'E Ink toggle must preserve this draft.'


class EInkProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'android-eink-validation'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def until(self, predicate):
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(.1)
        raise AssertionError('Native appearance did not settle')

    async def probe(self):
        output = Path(self.paths.cache) / 'eink-evidence'
        output.mkdir(exist_ok=True)
        report_path = output / 'result.json'
        report = json.loads(report_path.read_text()) if report_path.exists() else dict(cases=[], phase=0)
        report['success'] = False
        report['source'] = json.loads((Path(__file__).parents[2] / 'source.json').read_text())
        try:
            assert type(self._impl).__module__.startswith('toga_android.')
            phase = report['phase']
            self.show_settings()
            if phase == 0:
                assert not self.android_eink_choice.value and not palette.eink_enabled()
                self.new_document()
                self.editor.value = DRAFT
                self.show_settings()
                original_ink = self.editor._impl.native.getCurrentTextColor()
                report['original_ink'] = original_ink
                await asyncio.sleep(.5)
                await capture_window(self, output / 'default-settings.png')
                self.android_eink_choice.value = True
                await self.until(lambda: palette.eink_enabled() and self.editor._impl.native.getCurrentTextColor() == palette.argb('#000000'))
                assert self.editor.value == DRAFT
                assert hasattr(self.android_eink_choice._impl, '_eink_switch_style')
                assert Preferences(self.private_root).values['android_eink'] == 'true'
                await asyncio.sleep(.5)
                await capture_window(self, output / 'eink-settings.png')
                self.show_documents()
                await asyncio.sleep(.5)
                await capture_window(self, output / 'eink-editor.png')
                from features.books.mobile.private_view import PrivateWebView, MAX_HTML
                view = PrivateWebView(style=Pack(flex=1))
                content = '<html><head><style>body{color:#fff;background:#123456}</style></head><body>private mode check</body></html>'
                view.set_content('https://logistics.invalid/eink/', content)
                self.show_view(view, destination='documents', route='eink-webview', title='E Ink text preview')
                for _ in range(100):
                    if await view.evaluate_javascript('document.body && document.body.textContent') == 'private mode check':
                        break
                    await asyncio.sleep(.1)
                assert await view.evaluate_javascript('getComputedStyle(document.body).color') == 'rgb(0, 0, 0)'
                assert await view.evaluate_javascript('getComputedStyle(document.body).backgroundColor') == 'rgb(255, 255, 255)'
                self.show_settings()
                self.android_eink_choice.value = False
                await self.until(lambda: not palette.eink_enabled())
                await asyncio.sleep(.3)
                assert not await view.evaluate_javascript('Boolean(document.getElementById("logistics-eink"))')
                self.android_eink_choice.value = True
                await asyncio.sleep(.3)
                assert await view.evaluate_javascript('Boolean(document.getElementById("logistics-eink"))')
                try:
                    view.set_content('https://logistics.invalid/limit/', 'x' * MAX_HTML)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Private HTML styling crossed the memory-only bound')
                assert not view._impl._large_content_dir.exists()
                view.clear_private_content()
                self.show_settings()
                report['cases'] += ['default_unchanged', 'toggle_saves_immediately', 'native_black_text_on_white',
                    'open_draft_preserved', 'private_webview_live_toggle_and_restore', 'private_html_bound_no_disk_fallback']
                report['phase'] = 1
            elif phase == 1:
                assert self.android_eink_choice.value and palette.eink_enabled()
                assert self.editor._impl.native.getCurrentTextColor() == palette.argb('#000000')
                await asyncio.sleep(.5)
                await capture_window(self, output / 'restored-eink-settings.png')
                self.android_eink_choice.value = False
                await self.until(lambda: not palette.eink_enabled() and self.editor._impl.native.getCurrentTextColor() == report['original_ink'])
                assert Preferences(self.private_root).values['android_eink'] == 'false'
                await asyncio.sleep(.5)
                await capture_window(self, output / 'restored-default-settings.png')
                report['cases'] += ['enabled_restores_on_process_restart', 'disable_restores_original_palette']
                report['phase'] = 2
            else:
                assert not self.android_eink_choice.value and not palette.eink_enabled()
                assert self.editor._impl.native.getCurrentTextColor() == report['original_ink']
                report['cases'].append('disabled_restores_on_process_restart')
                report['phase'] = 3
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
            traceback.print_exc()
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        print('EINK_RESULT=' + json.dumps(report), flush=True)
        await asyncio.sleep(.2)
        os._exit(0 if report['success'] else 1)


def main():
    return EInkProbe('Android E Ink validation', BUNDLE)
