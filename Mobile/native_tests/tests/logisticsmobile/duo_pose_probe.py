"""Isolated native rotation audit plus optional observed Device Hub fold poses.

The automatic sweep records only poses actually observed. --observe-folds keeps
one comic session open for Device Hub open/close/fold/rotate interaction, saving
state and screenshots after each settled geometry change. No fake hinge input.
"""
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import traceback

from .ios_toolbar_probe import ToolbarProbe
from .rotation_checks import panel_state, pose_snapshot, rotate, safe_geometry, assert_visible_controls

BUNDLE = 'io.github.ispaure.logisticsduofoldqa'


class DuoPoseProbe(ToolbarProbe):
    def on_running(self):
        from rubicon.objc import ObjCClass
        arguments = [str(arg) for arg in ObjCClass('NSProcessInfo').processInfo.arguments]
        self.pose_sweep = '--pose-sweep' in arguments
        self.page_turns = '--page-turns' in arguments
        super().on_running()

    async def record(self, name):
        from .page_motion_checks import exercise
        await exercise(self, name)
        if self.page_turns and name.endswith('-cbz'):
            owner = self.private_sessions.active
            if owner.crypt_immersive:
                owner.toggle_private_reading_mode()
                await asyncio.sleep(.3)
        expected = panel_state(self)
        first = None
        for orientation in ((None,) if self.pose_sweep else ('portrait', 'landscape-left', 'landscape-right', 'portrait')):
            if orientation is not None:
                await rotate(self, orientation)
            self.resize_workspace()
            await asyncio.sleep(.3)
            assert panel_state(self) == expected, (name, orientation, 'content or route changed')
            sample = await super().record(name + '-' + (orientation or 'observed-pose'))
            sample.update(pose=pose_snapshot(self), safe_area=safe_geometry(self),
                          fixed_controls=assert_visible_controls(self))
            from .artwork_checks import snapshot
            sample['artwork'] = await snapshot(self)
            self.check_panes(sample)
            if first is None:
                first = sample
        return first

    def check_panes(self, sample):
        from logisticsmobile.fold_layout import division
        body = self.body.children[0] if self.body.children else None
        frame = getattr(body, '_workspace_frame', None)
        if frame is None or len(frame.row.children) != 2 or frame.compact_open:
            return
        fold = division(self, frame.row)
        children = frame.row.children
        if fold is not None:
            assert_fold_panes(frame.row, fold)
        sample['panes'] = dict(widths=[float(child._impl.native.bounds.size.width) for child in children],
                               fold=asdict(fold) if fold else None)

    async def check(self):
        await super().check()
        source = Path(__file__).resolve().parents[2] / 'fold-source.json'
        if source.exists():
            self.report['source'] = json.loads(source.read_text())
        self.report['observed_poses'] = sorted({pose_key(row['pose']) for row in self.report['screens'] if 'pose' in row})
        self.report['artwork_accessibility_policy_round_trips'] = sorted(getattr(self, '_artwork_accessibility_checks', set()))
        self.report['all_fold_poses_tested'] = False
        self.report['comic_fold_round_trip_tested'] = False
        (self.output / 'result.json').write_text(json.dumps(self.report, indent=2))
        from rubicon.objc import ObjCClass
        arguments = [str(arg) for arg in ObjCClass('NSProcessInfo').processInfo.arguments]
        if '--observe-folds' not in arguments or not self.report['success']:
            return
        try:
            owner = next(owner for owner in self.readers.controllers.values()
                         if (getattr(owner, 'book_record', None) or {}).get('kind') == 'comic')
            await self.open_book(owner.book_record['id'])
            owner = self.readers.active
            owner.set_reading_mode(False)
            await owner.move_book_page(1)
            expected = panel_state(self)
            previous = None
            # Bounded interactive audit. Each sample is evidence of a real pose.
            for _ in range(1800):
                await asyncio.sleep(.5)
                pose = pose_snapshot(self)
                signature = json.dumps(pose, sort_keys=True)
                if signature == previous:
                    continue
                await asyncio.sleep(.5)
                if json.dumps(pose_snapshot(self), sort_keys=True) != signature:
                    continue
                previous = signature
                self.resize_workspace()
                await asyncio.sleep(.5)
                assert panel_state(self) == expected, 'Fold changed the active document/page'
                sample = await super().record('live-fold-' + str(len(self.report['screens'])))
                sample.update(pose=pose_snapshot(self), safe_area=safe_geometry(self))
                nav = owner.comic_navigation
                if nav.right_anchored:
                    assert (nav.visible[0] if nav.right_to_left else nav.visible[-1]) == owner.book_record['position']
                sample['comic'] = dict(anchor=nav.page, visible=nav.visible, right_anchored=nav.right_anchored)
                self.report['observed_poses'] = sorted({pose_key(row['pose']) for row in self.report['screens'] if 'pose' in row})
                required = {f'{pose}-{axis}' for pose in ('outer', 'inner-flat', 'inner-folded') for axis in ('tall', 'wide')}
                self.report['comic_fold_round_trip_tested'] = required <= set(self.report['observed_poses'])
                (self.output / 'result.json').write_text(json.dumps(self.report, indent=2))
        except BaseException:
            self.report.update(success=False, error=traceback.format_exc())
            (self.output / 'result.json').write_text(json.dumps(self.report, indent=2))


def pose_key(pose):
    state = {1: 'outer', 2: 'inner-folded', 3: 'inner-flat'}.get(pose.get('hinge_status'), 'non-duo')
    return state + ('-wide' if pose['width'] > pose['height'] else '-tall')


def assert_fold_panes(row, fold):
    """Actual native pane allocations must leave the whole reserved band clear."""
    native = row._impl.native
    rects = [child._impl.native.convertRect(child._impl.native.bounds, toView=native) for child in row.children]
    first, second = rects
    if fold.vertical:
        assert first.origin.x + first.size.width <= fold.x + 1, (first, fold)
        assert second.origin.x >= fold.x + fold.width - 1, (second, fold)
    else:
        assert first.origin.y + first.size.height <= fold.y + 1, (first, fold)
        assert second.origin.y >= fold.y + fold.height - 1, (second, fold)


def main():
    return DuoPoseProbe('Fold QA', BUNDLE)
