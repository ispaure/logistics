"""Measure production Markdown surfaces in an isolated iOS app."""
import asyncio
import json
import logging
from pathlib import Path
import traceback
from uuid import uuid4

from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile
from mobile.font_scaling import refresh
from . import start_native_check
from .web_checks import wait_for_text
from .fixtures import capture_window

TEST_STAGE = TestStage.REGRESSION
TEXT = ('# Typography sample\n\nBody sample with `inline code`.\n\n'
        '## Second\n\n### Third\n\n#### Fourth\n\n##### Fifth\n\n###### Sixth\n\n'
        '- List sample\n\n> Quote sample\n\n```\nCode sample\n```\n\n'
        '| Column |\n| --- |\n| Cell |\n')
METRICS = """JSON.stringify(Object.fromEntries(
 ['body','p','h1','h2','h3','h4','h5','h6','li','blockquote','pre code','p code','td'].map(s=>{
 const selector=/^h[1-6]$/.test(s)?s+',[data-live-heading="'+s[1]+'"]'
   :s==='p'?'p:not([data-live-heading])':s==='p code'?'p code,p .live-code':s;
 const e=s==='body'?document.body:(document.querySelector('#document')||document.body).querySelector(selector),c=getComputedStyle(e);
 return [s,{size:parseFloat(c.fontSize),family:c.fontFamily,line:c.lineHeight}];})))"""


class MarkdownTypographyProbe(LogisticsMobile):
    def startup(self):
        logging.getLogger().addHandler(logging.FileHandler(
            Path(self.paths.cache) / 'logistics-native-ui-error.txt', mode='w'))
        self.storage_root = Path(self.paths.cache) / ('typography-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        report = dict(success=False, samples=[])
        try:
            from mobile.obsidian import open_vault
            from mobile.documentation_ui import show_documentation
            root = self.storage_root / 'sample'
            (root / '.obsidian').mkdir(parents=True)
            (root / 'Sample.md').write_text(TEXT)
            expected = None

            async def measure(name, web, size):
                nonlocal expected
                await wait_for_text(web, 'Typography sample')
                await asyncio.sleep(.3)
                metrics = json.loads(await web.evaluate_javascript(METRICS))
                report['samples'].append(dict(name=name, size=size, metrics=metrics))
                assert metrics['p']['size'] == size, (name, metrics)
                ratios = {key: round(value['size'] / size, 3) for key, value in metrics.items()}
                if expected is None:
                    expected = ratios
                assert ratios == expected, (name, ratios, expected)
                await capture_window(self, Path(self.paths.cache) / 'viewer-layout' / (name + '.png'))

            (Path(self.paths.cache) / 'viewer-layout').mkdir(exist_ok=True)
            for size in (16, 24):
                self.preferences.values['markdown_font_size'] = str(size)
                refresh(self)
                self.create_chosen_document('md')
                owner = self.editor_view
                owner.editor.value = TEXT
                owner.apply_split(0)
                await measure(f'file-edit-{size}', owner.formatted.view, size)
                native_size = float(owner.editor._impl.native.font.pointSize)
                assert abs(native_size - size) < .7, native_size
                report['samples'].append(dict(name='file-source', size=size, native_size=native_size))
                self.show_preview()
                await measure(f'file-read-{size}', owner.preview, size)
                library = await open_vault(self, LocalFiles(root), '', 'files')
                await library.open_note('Sample.md')
                await measure(f'notes-read-{size}', library.web, size)
                assert await library.open_editor()
                editor = self.private_sessions.active
                await measure(f'notes-edit-{size}', editor._provider_markdown.formatted.view, size)
                native_size = float(editor.crypt_text._impl.native.font.pointSize)
                assert abs(native_size - size) < .7, native_size
                report['samples'].append(dict(name='notes-source', size=size, native_size=native_size))
                docs = show_documentation(self, root, root / 'Sample.md')
                if docs.load_task is not None:
                    await docs.load_task
                await measure(f'documentation-{size}', docs.web, size)
                # Keep the legacy/general preference deliberately different.
                self.preferences.values['font_size'] = '12'
                self.show_chat()
                for _ in range(100):
                    if self.chat_current is not None:
                        break
                    await asyncio.sleep(.05)
                from features.lm.domain import message
                self.chat_current['messages'] = [message('assistant', TEXT)]
                self.update_chat_transcript()
                await measure(f'chat-{size}', self.chat_transcript, size)
                native_size = float(self.chat_prompt._impl.native.font.pointSize)
                assert abs(native_size - size) < .7, native_size
                report['samples'].append(dict(name='chat-composer', size=size, native_size=native_size))
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'markdown-typography-result.json').write_text(json.dumps(report, indent=2))


def main():
    return MarkdownTypographyProbe('Markdown typography QA', 'io.github.ispaure.logisticsstorageqa')
