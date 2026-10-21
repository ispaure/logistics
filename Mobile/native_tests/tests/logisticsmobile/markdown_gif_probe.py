"""Isolated native WebView GIF/sizing proof; never opens existing user documents.

The driver captures native screenshots while each phase is active. Those pixels,
not canvas drawImage (which may use a GIF's first frame), prove visible animation.
"""
import asyncio
import base64
import json
from pathlib import Path
import traceback

import toga
from toga.style import Pack

if toga.platform.current_platform == 'iOS':
    from toga_iOS.app import PythonAppDelegate

    class LogisticsSceneAppDelegate(PythonAppDelegate):
        pass


GIF = base64.b64decode(
    'R0lGODlhBAAEAIEAAP8AAAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQABgAAACwAAAAABAAE'
    'AAAICQABCBxIsCCAgAAh+QQBBgABACwAAAAABAAEAIEAAP8AAAAAAAAAAAAICQABCBxIsCCAgAA7')


class MarkdownGifProbe(toga.App):
    def startup(self):
        self.main_window = toga.MainWindow(title='Markdown GIF verification')
        self.web = toga.WebView(style=Pack(flex=1))
        self.main_window.content = self.web
        self.main_window.show()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def evaluate(self, web, script):
        return await asyncio.wait_for(web.evaluate_javascript(script), timeout=10)

    async def inspect(self, web):
        for _ in range(100):
            raw = await self.evaluate(web, '''JSON.stringify({viewport:innerWidth,
                images:Array.from(document.images, img=>({loaded:img.complete&&img.naturalWidth===4,
                width:img.getBoundingClientRect().width,height:img.getBoundingClientRect().height,
                left:img.getBoundingClientRect().left,right:img.getBoundingClientRect().right,
                source:img.src.startsWith('data:image/gif;base64,')}))})''')
            result = json.loads(raw)
            if len(result['images']) == 2 and all(row['loaded'] for row in result['images']):
                for image in result['images']:
                    assert image['source'] and 0 < image['width'] <= 400
                    assert image['left'] >= 0 and image['right'] <= result['viewport'] + 1
                assert abs(result['images'][1]['width'] - 70) < 1
                assert abs(result['images'][0]['width'] / result['images'][0]['height'] - 2) < .02
                return result
            await asyncio.sleep(.05)
        raise AssertionError('GIF images did not load in native WebView')

    async def phase(self, name, web, report):
        sample = await self.inspect(web)
        report['samples'].append(dict(mode=name, **sample))
        (self.paths.cache / 'gif-phase.json').write_text(json.dumps(dict(mode=name)))
        await asyncio.sleep(5)  # Driver saves multiple native frames during this window.

    async def probe(self):
        from commonUtils.runtime.local_files import LocalFiles
        from commonUtils.ui.native.markdown_images import folder_image_source
        from logisticsmobile.preview import markdown_preview
        from features.text_editor.mobile.markdown_editor import FormattedMarkdownInput
        result = dict(success=False, backend=type(self.web._impl).__module__, samples=[])
        try:
            root = self.paths.cache / 'gif-fixtures'
            root.mkdir(exist_ok=True)
            (root / 'colors #1.GIF').write_bytes(GIF)
            path = root / 'note.md'
            source = 'Before ![Colors|400x200](colors%20%231.GIF) after.\n\n![[colors #1.GIF|70]]\n'
            path.write_text(source)
            factory = lambda: folder_image_source(LocalFiles(root), 'note.md')
            self.web.set_content('https://logistics.invalid/gif/read/',
                markdown_preview(source, image_source=factory()))
            await self.phase('preview', self.web, result)
            changes = []
            editor = FormattedMarkdownInput(changes.append, image_source=factory)
            self.main_window.content = editor.view
            editor.load(source)
            await self.phase('formatted', editor.view, result)
            await self.evaluate(editor.view, '''(()=>{const p=document.querySelector('section p');
                p.append(document.createTextNode(' edited'));
                p.dispatchEvent(new InputEvent('input',{bubbles:true}));return true})()''')
            for _ in range(100):
                if changes:
                    break
                await asyncio.sleep(.05)
            assert changes and ' edited' in changes[-1]
            assert '![Colors|400x200](colors%20%231.GIF)' in changes[-1]
            assert '![[colors #1.GIF|70]]' in changes[-1]
            assert 'data:image' not in changes[-1]
            path.write_text(changes[-1])
            source_input = toga.MultilineTextInput(value=path.read_text())
            assert source_input.value == changes[-1]
            result['source_round_trip'] = True
            editor.dispose()
            self.main_window.content = self.web
            self.web.set_content('https://logistics.invalid/gif/reopened/',
                markdown_preview(path.read_text(), image_source=factory()))
            await self.phase('saved-reopened', self.web, result)
            from commonUtils.ui.native.markdown import MarkdownWikiView
            wiki = MarkdownWikiView(root, path, width=390)
            self.main_window.content = wiki.view
            await self.phase('wiki', wiki.web, result)
            assert (root / 'colors #1.GIF').read_bytes() == GIF
            result['image_bytes_unchanged'] = True
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (self.paths.cache / 'gif-phase.json').write_text(json.dumps(dict(mode='complete')))
        (self.paths.cache / 'gif-result.json').write_text(json.dumps(result, indent=2))
        print('MARKDOWN_GIF_RESULT=' + json.dumps(result), flush=True)


def main():
    return MarkdownGifProbe('Markdown GIF QA', 'io.github.ispaure.logisticsgifqa')
