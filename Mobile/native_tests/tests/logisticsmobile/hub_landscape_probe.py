"""Disposable Duo hub rotation/seam check; partial hinge status is injected."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4
from logisticsmobile.app import LogisticsMobile
from .fixtures import capture_window
from .rotation_checks import rotate


class HubLandscapeProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('hub-landscape-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'hub-landscape-probe'
        output.mkdir(exist_ok=True)
        report = dict(success=False, samples=[], injected_hinge_status=True)
        try:
            await asyncio.sleep(1)
            for index in range(18):
                document = self.store.create(f'Landscape document {index + 1:02d}.md')
                session = self.workspace.open('managed-text', document.id, 'markdown', document.name)
                self.recent_documents.remember(session)
            for orientation in ('landscape-left', 'landscape-right', 'portrait'):
                await rotate(self, orientation)
                for status in ((3, 2) if orientation != 'portrait' else (0,)):
                    self._hinge_status = status
                    for destination, show in (('home', self.show_home), ('documents', self.show_documents_hub)):
                        show()
                        await asyncio.sleep(.4)
                        self.resize_workspace()
                        await asyncio.sleep(.4)
                        hub = self.home_sections if destination == 'home' else self.documents_sections
                        window = self.main_window._impl.native
                        def rect(widget):
                            native = widget._impl.native
                            frame = native.convertRect(native.bounds, toView=window)
                            return [float(frame.origin.x), float(frame.origin.y),
                                    float(frame.size.width), float(frame.size.height)]
                        name = f'{destination}-{orientation}-{status}'
                        sample = dict(name=name, paired=hub.paired, left=rect(hub.leading_scroll),
                                      right=rect(hub.trailing_scroll) if hub.paired else None)
                        report['samples'].append(sample)
                        await capture_window(self, output / (name + '.png'))
                        assert hub.paired == (orientation != 'portrait'), sample
                        if hub.paired:
                            left, right = sample['left'], sample['right']
                            center = float(window.bounds.size.width) / 2
                            assert abs(left[0] + left[2] - center) <= 1, sample
                            assert abs(right[0] - center) <= 1, sample
                            assert abs(left[3] - right[3]) <= 1 and left[3] > 250, sample
                            import toga
                            def check_controls(widget, bounds):
                                if isinstance(widget, toga.Button):
                                    x, _, width, _ = rect(widget)
                                    assert x >= bounds[0] - 1 and x + width <= bounds[0] + bounds[2] + 1, (widget.text, rect(widget), bounds)
                                for child in widget.children:
                                    check_controls(child, bounds)
                            check_controls(hub.content, left)
                            check_controls(hub.trailing_content, right)
                            assert hub.trailing.parent is hub.trailing_content
                            # Each side scrolls independently and all rows stay reachable.
                            hub.trailing_scroll.vertical_position = hub.trailing_scroll.max_vertical_position
                            await asyncio.sleep(.1)
                            assert hub.leading_scroll.vertical_position == 0
                            hub.trailing_scroll.vertical_position = 0
                        else:
                            assert hub.trailing.parent is hub.content
            report['retained_rotation'] = []
            for destination, show in (('home', self.show_home), ('documents', self.show_documents_hub)):
                show()
                hub = self.home_sections if destination == 'home' else self.documents_sections
                leading, trailing = hub.content, hub.trailing
                for orientation, status in (('landscape-right', 2), ('portrait', 0)):
                    self._hinge_status = status
                    await rotate(self, orientation)
                    self.resize_workspace()
                    await asyncio.sleep(.3)
                    assert hub is (self.home_sections if destination == 'home' else self.documents_sections)
                    assert hub.content is leading and hub.trailing is trailing
                    assert hub.paired == (status == 2)
                    assert not self.routes.screens[destination]
                report['retained_rotation'].append(destination)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('HUB_LANDSCAPE_RESULT=' + json.dumps(report), flush=True)


def main():
    return HubLandscapeProbe('Hub Landscape Preview', 'io.github.ispaure.logisticshublandscape')
