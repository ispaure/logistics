"""Native workspace Move and Notes folder checks with startup diagnostics."""
import asyncio
import json
from pathlib import Path
from time import monotonic
import sys
import traceback

from commonUtils.testing.stages import TestStage
from .document_workspace_probe import DocumentWorkspaceProbe
from .workspace_move_probe import WorkspaceMoveProbe
from .notes_folders_probe import NotesFoldersProbe

TEST_STAGE = TestStage.EXTENDED


class FolderFeedbackProbe(DocumentWorkspaceProbe):
    result_name = 'folder-feedback-result.json'

    def startup(self):
        self._probe_complete = False
        self._feedback_report = {}
        self._feedback_phase = 'startup'
        self._startup_samples = []
        self._startup_started = monotonic()
        super().startup()
        self.loop.call_later(2, self.sample_startup)

    def sample_startup(self, *, schedule=True):
        sample = dict(elapsed=monotonic() - self._startup_started,
                      starting=getattr(self, '_startup_in_progress', True),
                      phase=self._feedback_phase, cases=list(self._feedback_report.get('cases', [])))
        navigation = getattr(self, 'navigation', None)
        if navigation is not None and type(self._impl).__module__.startswith('toga_android.'):
            def geometry(view):
                return dict(width=view.getWidth(), height=view.getHeight(),
                            layout_requested=view.isLayoutRequested(),
                            attached=view.isAttachedToWindow(), visibility=view.getVisibility())
            sample['root'] = geometry(navigation._impl.native)
            sample['content'] = geometry(navigation._impl.native_content)
            cover = getattr(getattr(self, 'startup_screen', None), 'cover', None)
            if cover is not None:
                sample['cover_parent'] = geometry(cover.parent)
                sample['cover_geometry'] = cover.geometry
                sample['cover_finished'] = cover.future.done()
        self._startup_samples = [*self._startup_samples[-59:], sample]
        cache = Path(self.paths.cache)
        pending = cache / 'folder-feedback-startup.json.tmp'
        pending.write_text(json.dumps(self._startup_samples, indent=2))
        pending.replace(cache / 'folder-feedback-startup.json')
        if not self._probe_complete:
            stacks = []
            for task in asyncio.all_tasks(self.loop):
                stacks.append(repr(task))
                pending = task.get_coro()
                while pending is not None:
                    frame = getattr(pending, 'cr_frame', None) or getattr(pending, 'gi_frame', None)
                    if frame is not None:
                        stacks.extend(traceback.format_stack(frame))
                    pending = getattr(pending, 'cr_await', None) or getattr(pending, 'gi_yieldfrom', None)
            for identity, frame in sys._current_frames().items():
                stacks.append('Thread ' + str(identity))
                stacks.extend(traceback.format_stack(frame))
            (cache / 'folder-feedback-tasks.txt').write_text('\n'.join(stacks))
            if schedule:
                self.loop.call_later(2, self.sample_startup)

    async def check(self, app):
        try:
            await super().check(app)
        finally:
            self._probe_complete = True
            self.sample_startup(schedule=False)

    async def run_checks(self, app, report):
        self._feedback_report = report
        self._feedback_phase = 'workspace_moves'
        self.sample_startup(schedule=False)
        report['startup_seconds'] = monotonic() - self._startup_started
        report['backend'] = type(app._impl).__module__
        if report['backend'].startswith('toga_android.'):
            from android.os import Build
            report['device'] = dict(model=str(Build.MODEL), api=int(Build.VERSION.SDK_INT))
        await WorkspaceMoveProbe.run_checks(self, app, report)
        self._feedback_phase = 'folder_expansion'
        await NotesFoldersProbe.run_checks(self, app, report)
        self._feedback_phase = 'complete'

    settle = NotesFoldersProbe.settle


def main():
    return FolderFeedbackProbe('Folder Feedback QA', 'io.github.ispaure.logisticsnotebookqa')
