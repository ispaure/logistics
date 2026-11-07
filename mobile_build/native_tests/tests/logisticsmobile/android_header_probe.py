"""Android Notes/Help header acceptance with native taps, swipes and bounds."""
import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from mobile.obsidian import open_vault
from .documentation_header_probe import DocumentationHeaderProbe
from .rotation_checks import rotate

TEST_STAGE = TestStage.REGRESSION


class AndroidHeaderProbe(DocumentationHeaderProbe):
    def startup(self):
        super().startup()
        self.loop.create_task(self.observe_startup())

    async def observe_startup(self):
        samples = []
        for _ in range(120):
            await asyncio.sleep(.5)
            cover = getattr(getattr(self, 'startup_screen', None), 'cover', None)
            sample = dict(startup=bool(getattr(self, '_startup_in_progress', True)),
                          layout_ready=bool(getattr(self, '_startup_layout_ready', False)))
            if cover is not None:
                root, content = self.navigation._impl.native, self.navigation._impl.native_content
                sample.update(geometry=[int(root.getWidth()), int(root.getHeight()),
                    int(content.getWidth()), int(content.getHeight())],
                    requested=[bool(root.isLayoutRequested()), bool(content.isLayoutRequested())],
                    previous=cover.geometry, future_done=cover.future.done())
            samples.append(sample)
            (Path(self.paths.cache) / 'android-header-startup.json').write_text(
                json.dumps(samples[-20:], indent=2))
            if not sample['startup']:
                break

    async def probe(self):
        output = Path(self.paths.cache)
        evidence = output / 'viewer-layout'
        evidence.mkdir(exist_ok=True)
        report = dict(success=False, samples=[])
        owner = None
        try:
            await super().probe()
            report['help'] = json.loads((output / 'documentation-header-result.json').read_text())
            assert report['help']['success'], report['help'].get('error')
            self.routes.back()
            await self.show_files()
            root = output / 'Art'
            (root / '.obsidian').mkdir(parents=True, exist_ok=True)
            (root / 'Home.md').write_text('# Home\n\n[[Other]]')
            (root / 'Other.md').write_text('# Other\n\n[[Home]]')
            long_name = 'Weekly environment art and lighting production references.md'
            (root / long_name).write_text('# Weekly review')
            (root / 'World').mkdir(exist_ok=True)
            (root / 'World/World.md').write_text('# World')
            folder = root / 'World/Projects/Character art production planning'
            folder.mkdir(parents=True, exist_ok=True)
            name = 'Review the complete delivery schedule and documentation notes.md'
            target = (folder / name).relative_to(root).as_posix()
            (folder / name).write_text('# Production planning\n\nA native header fixture.')
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            assert await owner.open_note('Home.md')
            assert await owner.open_note('Other.md')
            await self.touch_native(owner.back_button._impl.native)
            await self.wait_for(lambda: owner.path == 'Home.md' and owner.history_index == 0
                and owner.forward_button.enabled, 'Back tap did not retrace note history')
            await self.touch_native(owner.forward_button._impl.native)
            await self.wait_for(lambda: owner.path == 'Other.md' and owner.history_index == 1
                and not owner.page_loading.active, 'Forward tap did not restore the note')
            await self.touch_native(owner.edit._impl.native)
            await self.wait_for(lambda: owner.editing, 'Pencil tap did not enter editing')
            formatted = owner.embedded.formatted
            for _ in range(400):
                if await formatted.view.evaluate_javascript(
                        'document.documentElement.dataset.editorBridge===' + json.dumps(formatted.bridge)
                        + ' && typeof window.markdownSnapshot==="function"'):
                    break
                await asyncio.sleep(.05)
            else:
                raise AssertionError('Formatted editor did not finish loading')
            await self.touch_native(owner.edit._impl.native)
            await self.wait_for(lambda: not owner.editing, 'View tap did not leave editing')
            for orientation in ('portrait', 'landscape-left', 'portrait'):
                (output / 'creation-orientation').write_text(orientation)
                await rotate(self, orientation, settle=.6, timeout=45)
                assert await owner.open_note(target)
                await asyncio.sleep(.7)
                self.adaptive.render()
                await asyncio.sleep(.3)
                scroll = owner.breadcrumb_scroll
                for button in owner.breadcrumbs.children:
                    if not hasattr(button, 'breadcrumb_folder'):
                        continue
                    native = button._impl.native
                    layout = native.getLayout()
                    assert layout is not None and layout.getEllipsisCount(0) == 0, (
                        'Breadcrumb label ellipsized inside scroll content', button.text,
                        native.getWidth(), native.getPaint().measureText(button.text),
                        native.getPaddingLeft(), native.getPaddingRight())
                assert abs(scroll.horizontal_position - scroll.max_horizontal_position) <= 1, (
                    'Initial breadcrumb end', scroll.horizontal_position, scroll.max_horizontal_position)
                controls = [owner.back_button, owner.forward_button, scroll, owner.edit, owner.reader_actions_button]
                assert list(owner.secondary.children) == controls
                row_x, _, row_width, _ = self.native_rect(owner.secondary._impl.native)
                rects = [self.native_rect(control._impl.native) for control in controls]
                assert rects[0][0] >= row_x - 1
                assert rects[-1][0] + rects[-1][2] <= row_x + row_width + 1, ('Clipped actions', rects)
                for left, right in zip(rects, rects[1:]):
                    assert left[0] + left[2] <= right[0] + 1, ('Overlapping controls', rects)
                scroll_width = self.native_rect(scroll._impl.native)[2]
                assert scroll_width >= 96 * (
                    scroll._impl.native.getResources().getDisplayMetrics().density) - 1, (
                    'Breadcrumb viewport too narrow', rects)
                label = self.native_host.adapter._reader_action_bar_title
                assert label.getTypeface().isBold(), 'Notes title is not bold'
                assert owner.reader_actions_button._impl._surface_roles[0] == 'transparent'
                titles = label.getParent()
                density = label.getResources().getDisplayMetrics().density
                margins = titles.getLayoutParams()
                unit = round(owner.menu.style.width * density)
                assert margins.getMarginStart() == 2 * unit
                assert margins.getMarginEnd() == unit
                close_rect = self.native_rect(owner.close_button._impl.native)
                close = owner.close_button._impl.native
                icon = owner.close_button._impl._control_drawable.getBounds()
                bubble = close.getBackground().getDrawable(0).getBounds()
                assert abs(close.getPaddingStart() + icon.width() / 2 - bubble.exactCenterX()) <= 1
                assert abs(bubble.exactCenterY() - close_rect[3] / 2) <= 1
                assert bubble.height() < close_rect[3] and bubble.width() < close_rect[2]
                links_rect = self.native_rect(owner.links_button._impl.native)
                assert abs(close_rect[0] - rects[0][0]) <= 2, (close_rect, rects[0])
                assert abs(sum((links_rect[0], links_rect[2])) - sum((rects[-1][0], rects[-1][2]))) <= 2, (
                    links_rect, rects[-1])
                assert abs(close_rect[2] - unit) <= 1 and abs(links_rect[2] - unit) <= 1
                available = titles.getParent().getWidth() - 3 * unit
                assert abs(titles.getWidth() - available) <= 1, ('Unused title width', titles.getWidth(), available)
                assert str(label.getText()) == name
                await self.capture_header(evidence / ('notes-title-' + orientation + '.png'))
                await self.touch_native(owner.reader_actions_button._impl.native)
                popup = owner.reader_actions.menu.popup
                assert popup is not None and popup.getMenu().size() > 0, 'Actions menu did not open'
                await self.capture_header(evidence / ('notes-menu-' + orientation + '.png'))
                popup.dismiss()
                if owner._breadcrumbs_shortened:
                    crumb_x, _, crumb_width, _ = self.native_rect(owner.breadcrumbs.children[0]._impl.native)
                    fraction = (crumb_x + crumb_width / 2 + 65 * density - rects[2][0]) / scroll_width
                    await self.touch_native(scroll._impl.native, fraction=fraction, swipe=1)
                    await self.wait_for(lambda: not owner._breadcrumbs_shortened
                        and scroll.max_horizontal_position > 0,
                        'Horizontal drag did not expand breadcrumb labels')
                    assert not owner.sidebar.sidebar_open
                    await asyncio.sleep(.3)
                before = scroll.horizontal_position
                for _ in range(20):
                    if scroll.horizontal_position <= 1:
                        break
                    await self.touch_native(scroll._impl.hScrollView, swipe=1)
                assert scroll.horizontal_position <= 1, ('Cannot swipe to library root', before, scroll.horizontal_position)
                assert not owner.sidebar.sidebar_open, 'Breadcrumb swipe opened a drawer'
                await self.capture_header(evidence / ('notes-root-' + orientation + '.png'))
                owner.select_panel_tab('Search')
                await self.touch_native(owner.breadcrumbs.children[0]._impl.native)
                await self.wait_for(lambda: owner.panel_tab == 'Files'
                    and (owner.sidebar.expanded or owner.sidebar.sidebar_open),
                    'Root breadcrumb tap did not reveal Files')
                if orientation == 'portrait':
                    await asyncio.sleep(.45)
                    listing = owner.rows.native_list
                    entry = next(row for row in listing.data if row.path == long_name)
                    label = listing._impl.native.getRowTitleView(entry.index, listing._impl.generation)
                    assert label is not None and label.getMaxLines() == 2
                    assert label.getLayout().getLineCount() == 2, 'Long note title did not wrap'
                    from android.util import TypedValue
                    expected = TypedValue.applyDimension(
                        TypedValue.COMPLEX_UNIT_SP, 15, label.getResources().getDisplayMetrics())
                    assert abs(label.getTextSize() - expected) < .1
                    await self.capture_header(evidence / 'notes-files-portrait.png')
                    drawer = owner.sidebar.overlay
                    pending = asyncio.create_task(owner.file_actions('World'))
                    await self.wait_for(lambda: owner.sidebar.action_overlay is not None,
                        'File actions did not open above Files')
                    await self.capture_header(evidence / 'notes-file-actions-portrait.png')
                    cancel = owner.sidebar.action_overlay.panel.content.children[-1]
                    await self.touch_native(cancel._impl.native)
                    await asyncio.wait_for(pending, timeout=5)
                    assert owner.sidebar.overlay is drawer and owner.sidebar.side == 'files'
                owner.sidebar.show_detail()
                owner.sidebar.finish_dismissals()
                await asyncio.sleep(.4)
                scroll.horizontal_position = 0
                await self.touch_native(owner.breadcrumbs.children[2]._impl.native)
                await self.wait_for(lambda: owner.path == 'World/World.md', 'Ancestor breadcrumb tap did not open its landing page')
                report['samples'].append(dict(orientation=orientation, expanded=owner.sidebar.expanded,
                    title_width=titles.getWidth() / density, breadcrumb_width=scroll_width / density,
                    initial_scroll=before, root_swipe=True, root_tap=True, ancestor_tap=True))
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
            print(report['error'], flush=True)
            try:
                await self.capture_header(evidence / 'notes-header-failure.png')
            except Exception:
                report['screenshot_error'] = traceback.format_exc()
        finally:
            if owner is not None:
                owner.dispose()
        (output / 'android-header-result.json').write_text(json.dumps(report, indent=2))


def main():
    return AndroidHeaderProbe('Android header QA', 'io.github.ispaure.logisticsnotebookqa')
