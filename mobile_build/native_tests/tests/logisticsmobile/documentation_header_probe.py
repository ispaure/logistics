"""Settings Help title and tree allocation on phone, tablet and folding hosts."""
import asyncio
import json
from pathlib import Path
import sys
import traceback

from .notes_drawers_probe import NotesDrawersProbe
from .fixtures import capture_window
from .rotation_checks import rotate
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


class DocumentationHeaderProbe(NotesDrawersProbe):
    async def probe(self):
        output = Path(self.paths.cache)
        evidence = output / 'viewer-layout'
        evidence.mkdir(exist_ok=True)
        report = dict(success=False, samples=[])
        try:
            self.show_settings()
            self.settings_navigation.choose('Help')
            def descendants(widget):
                yield widget
                for child in widget.children:
                    yield from descendants(child)
            button = next(child for child in descendants(self.settings_navigation.sections['Help'])
                          if getattr(child, 'text', '') == 'Mobile documentation')
            button.on_press()
            owner = self.documentation
            for orientation in ('portrait', 'landscape-left', 'portrait'):
                # The tablet driver acknowledges this request before native rotation.
                (output / 'creation-orientation').write_text(orientation)
                await rotate(self, orientation, settle=.7)
                self.adaptive.render()
                await asyncio.sleep(.5)
                assert owner.commands.parent is (owner.article if owner.wide else owner.view)
                assert owner.back_button.parent is owner.commands
                assert owner.forward_button.parent is owner.commands
                assert owner.view._native_reader_buttons() == []
                if sys.platform == 'ios':
                    title_width = float(owner.view._document_title_view.bounds.size.width)
                else:
                    label = self.native_host.adapter._reader_action_bar_title
                    title_width = float(label.getWidth()) / label.getResources().getDisplayMetrics().density
                assert title_width >= 140, ('Title squeezed by controls', title_width)
                await capture_window(self, evidence / ('help-article-' + orientation + '.png'))
                owner.show_browse()
                await asyncio.sleep(.4)
                title = owner.rows.children[0].children[-1]._impl.native
                if sys.platform == 'ios':
                    row_width = float(title.bounds.size.width)
                else:
                    row_width = float(title.getWidth()) / title.getResources().getDisplayMetrics().density
                assert row_width >= 140, ('Tree title squeezed', row_width)
                await capture_window(self, evidence / ('help-tree-' + orientation + '.png'))
                owner.sidebar.show_detail()
                owner.reading = True
                report['samples'].append(dict(orientation=orientation, title_width=title_width,
                                              tree_title_width=row_width, expanded=owner.wide))
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (output / 'documentation-header-result.json').write_text(json.dumps(report, indent=2))


def main():
    return DocumentationHeaderProbe('Help header QA', 'io.github.ispaure.logisticsnotebookqa')
