"""Retain one synthetic draft while real keyboard/window/fold controls change.

The operator or UI test drives UIKit. No hinge or keyboard geometry is injected.
Write ``finish`` in the evidence directory to end the bounded observation.
"""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import time
import traceback

from .fixtures import capture_window
from .markdown_rework_probe import MarkdownReworkProbe
from .rotation_checks import pose_snapshot
from .web_checks import wait_for_text


class MarkdownAdaptiveProbe(MarkdownReworkProbe):
    async def probe(self):
        output = Path(self.paths.cache) / 'markdown-adaptive-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, samples=[], observed_hinge_statuses=[])
        try:
            document = self.store.create('Adaptive writing.md',
                ('# Adaptive writing\n\nA **bold** idea and an [example](https://example.com).\n\n'
                 + 'A paragraph for keyboard and window testing.\n\n' * 30).encode())
            self.refresh_documents()
            self.open_document(document.id)
            self.show_documents(edit=True)
            owner = self.editor_view
            web = owner.formatted.view
            await wait_for_text(web, 'Adaptive writing')
            # Unnotified native DOM input must survive window/fold transitions.
            await web.evaluate_javascript("document.querySelector('h1').append(' — retained 😀')")
            await owner.formatted.flush()
            seen, previous = set(), None
            report['ready'] = True
            deadline = time.monotonic() + 850
            while time.monotonic() < deadline:
                await asyncio.sleep(.35)
                pose = pose_snapshot(self)
                adapter = self.native_host.adapter
                mode = owner.session.view.get('markdown_editor', 'formatted')
                sample = dict(pose=pose, keyboard_inset=float(adapter.keyboard_inset), mode=mode)
                signature = json.dumps(sample, sort_keys=True)
                if signature != previous:
                    # Ignore UIKit's intermediate morph frames, then measure
                    # the actual native WebView rather than a CSS approximation.
                    await asyncio.sleep(.5)
                    if pose_snapshot(self) != pose:
                        continue
                    if mode == 'formatted':
                        sample['web'] = json.loads(await web.evaluate_javascript('''JSON.stringify((() => {
                            const r=document.getElementById('document').getBoundingClientRect();
                            return {top:r.top,bottom:r.bottom,width:innerWidth,height:innerHeight,outerScroll:scrollY,
                                names:Array.from(document.querySelectorAll('nav button,nav summary')).map(b=>b.getAttribute('aria-label'))};
                        })())'''))
                        bounds = sample['web']
                        assert bounds['top'] >= -1 and bounds['bottom'] <= bounds['height'] + 1, bounds
                        assert abs(bounds['outerScroll']) < 1, bounds
                    assert self.editor_view is owner and owner.formatted.view is web
                    assert owner.document.text.startswith('# Adaptive writing — retained 😀'), owner.document.text[:100]
                    seen.add(pose.get('hinge_status', 0))
                    report['observed_hinge_statuses'] = sorted(seen)
                    report['samples'].append(sample)
                    report['draft_retained'] = owner.document.text.startswith('# Adaptive writing — retained 😀')
                    previous = signature
                    await capture_window(self, output / ('state-%02d.png' % len(report['samples'])))
                    (output / 'progress.json').write_text(json.dumps(report, indent=2))
                if (output / 'finish').exists():
                    await owner.save()
                    assert not owner.document.modified, owner.status.text
                    report['saved_final_input'] = True
                    report['real_fold_round_trip'] = {1, 2, 3} <= seen
                    report['success'] = True
                    break
            else:
                raise TimeoutError('Adaptive observation ended without a finish signal; only recorded poses were tested.')
        except BaseException:
            report['error'] = traceback.format_exc()
            await capture_window(self, output / 'failure.png')
        (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    return MarkdownAdaptiveProbe('Markdown QA', 'io.github.ispaure.logisticsmarkdownqa')
