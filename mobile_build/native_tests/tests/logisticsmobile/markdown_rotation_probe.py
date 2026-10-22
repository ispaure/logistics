"""Android Markdown route identity and viewport reflow on disposable local files."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies
from mobile.app import LogisticsMobile


class MarkdownRotationProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('markdown-rotation-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_rotation_probe_started', False):
            self._rotation_probe_started = True
            self.loop.create_task(self.probe())

    async def probe(self):
        report = dict(success=False, platform='android', samples=[])
        activity = self._impl.native
        original_orientation = activity.getRequestedOrientation()
        try:
            activity.setRequestedOrientation(1)
            root = self.storage_root / 'notes'
            root.mkdir()
            text = '# Mobile reading guide\n\n' + ('A paragraph that wraps within the portrait viewport. ' * 16)
            text += '\n\n## Wide table\n\n|' + '|'.join('Column ' + str(i) for i in range(10))
            text += '|\n|' + '|'.join('---' for i in range(10))
            text += '|\n|' + '|'.join('A long cell value' for i in range(10)) + '|\n'
            text += '\n```\n' + 'Long code sample ' * 80 + '\n```\n'
            name = 'A long Markdown filename for portrait layout and rotation.md'
            (root / name).write_text(text)
            assert await self.open_crypt(copies=LocalTextCopies(LocalFiles(root)), key=name, destination='files')
            owner = self.private_sessions.active
            web, body = owner.crypt_preview, self.routes.body('files')
            for label, orientation, configuration in (('portrait', 1, 1), ('landscape', 0, 2), ('portrait-return', 1, 1)):
                activity.setRequestedOrientation(orientation)
                for _ in range(80):
                    if activity.getResources().getConfiguration().orientation == configuration:
                        break
                    await asyncio.sleep(.1)
                await asyncio.sleep(3)
                if label == 'landscape':
                    self.adaptive.menu_open['files'] = True
                    self.adaptive.render()
                    await asyncio.sleep(.5)
                from android.graphics import Rect
                visible = Rect()
                web._impl.native.getGlobalVisibleRect(visible)
                metrics = json.loads(await web.evaluate_javascript(
                    'JSON.stringify({viewport:innerWidth,body:document.body.clientWidth,'
                    'scroll:document.documentElement.scrollWidth,font:getComputedStyle(document.body).fontSize})'))
                metrics.update(label=label, orientation=int(activity.getResources().getConfiguration().orientation),
                    window_width=self.main_window.size.width, web_pixels=web._impl.native.getWidth(),
                    visible_pixels=visible.width(), drawer_open=self.adaptive.menu_open['files'])
                report['samples'].append(metrics)
                assert metrics['orientation'] == configuration, metrics
                assert self.routes.body('files') is body and owner.crypt_view in body.children
                assert self.native_host.state.destination == 'files'
                assert owner.crypt_preview is web and owner.crypt_text.value == text
                assert owner.crypt_edit_mode not in owner.crypt_markdown_footer.children
                assert metrics['scroll'] <= metrics['viewport'] + 1, metrics
                if configuration == 1:
                    assert not metrics['drawer_open'] and metrics['visible_pixels'] >= metrics['web_pixels'] * .95, metrics
                from .fixtures import capture_window
                await capture_window(self, Path(self.paths.cache) / ('markdown-rotation-' + label + '.png'))
            samples = report['samples']
            assert samples[1]['window_width'] > samples[0]['window_width'], samples
            assert abs(samples[0]['viewport'] - samples[2]['viewport']) <= 1, samples
            assert len({sample['font'] for sample in samples}) == 1, samples
            # Selection callbacks can arrive after native layout settles.
            await asyncio.sleep(8)
            assert self.routes.body('files') is body and owner.crypt_view in body.children
            assert (root / name).read_text() == text
            report.update(success=True, route_retained=True, content_retained=True,
                portrait_no_overflow=True, native_rotation=True)
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            activity.setRequestedOrientation(original_orientation)
        (Path(self.paths.cache) / 'markdown-rotation-result.json').write_text(json.dumps(report, indent=2))
