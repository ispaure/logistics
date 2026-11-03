"""Reader titles across natural rotation, fullscreen and retained fold changes.

The optional external fold driver acknowledges requests in the synthetic cache;
it must change the real simulator posture, not inject application geometry.
"""
from commonUtils.testing.stages import TestStage
import asyncio
import json
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace

from .viewer_layout_probe import ViewerLayoutProbe, BUNDLE, geometry
from .fixtures import make_books
from .rotation_checks import rotate

TEST_STAGE = TestStage.EXTENDED


class ReaderTitleProbe(ViewerLayoutProbe):
    async def check(self):
        output = Path(self.paths.cache) / 'viewer-layout'
        output.mkdir(exist_ok=True)
        report = dict(success=False, samples=[], errors=[])
        try:
            if getattr(self, 'startup_task', None) is not None:
                await asyncio.shield(self.startup_task)
            await self.show_files()
            self.storage_root.mkdir(parents=True, exist_ok=True)
            epub, comic = make_books(self.storage_root, chapter_text="<p>A passage for repagination. </p>" * 240)
            comic = comic.replace(comic.with_name('2026 — ملاحظات اجتماع المشروع الأسبوعي والملفات المرفقة.cbz'))
            from commonUtils.runtime.resources.documents import LocalDocuments
            from commonUtils.runtime.resources.local import LocalFiles
            from services.documents.provider_documents import ProviderDocuments
            for imported in (True, False):
                for path in (comic, epub):
                    name = ('imported-' if imported else 'provider-') + path.suffix[1:]
                    await rotate(self, 'landscape-left', settle=.5)
                    if imported:
                        record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), path)
                        assert await self.open_book(record['id'])
                        owner = self.readers.active
                        owner.set_reading_mode(False)
                    else:
                        assert await self.open_crypt(copies=ProviderDocuments(LocalFiles(self.storage_root)), key=path.name)
                        owner = self.private_sessions.active
                        if getattr(owner, 'crypt_immersive', False):
                            owner.toggle_private_reading_mode()
                    async def record_sample(label, orientation, *, opening=False):
                        row = await self.sample(owner, label, orientation, output, opening=opening)
                        # The ordinary viewer probe also checks unrelated
                        # pagination/footer policy. This scenario owns titles.
                        row['errors'] = [error for error in row['errors'] if 'title' in error.lower()]
                        if sys.platform == 'ios':
                            from mobile.document_location import side_title_reader
                            controller = self.native_host.adapter.content_controller(self.native_host.state.destination)
                            reader = side_title_reader(self.body.children[0])
                            title = reader._document_title_view if reader is not None else controller.navigationItem.titleView
                        else:
                            reader = None
                            title = self.native_host.adapter._reader_action_bar_title
                        assert title is not None, 'Missing native document title'
                        if sys.platform == 'ios' and path == comic:
                            from commonUtils.ui.native.panning_title import apple_title_class
                            caption = next(child for child in title.subviews
                                           if child.isKindOfClass(apple_title_class()))
                            moving = caption.movingText
                            if moving is not None:
                                right = float(moving.frame.origin.x + moving.frame.size.width)
                                if abs(right - float(caption.bounds.size.width)) > 1:
                                    row['errors'].append('Right-to-left title starts at the wrong edge')
                        frame = geometry(self, SimpleNamespace(_impl=SimpleNamespace(native=title)))
                        row['native_title'] = frame
                        content = geometry(self, reader._reading_frame_owner.content) if reader is not None else row['view']
                        if frame[1] + frame[3] > content[1] + 1:
                            row['errors'].append('Native title overlaps the document')
                        if sys.platform == 'ios' and 'epub' in row:
                            dom = row['epub']
                            if frame[1] + frame[3] > dom['native_frame'][1] + 1:
                                row['errors'].append('Native title overlaps the EPUB WebView')
                            if reader is not None and frame[3] < 37:
                                row['errors'].append('Title frame clips its storage subtitle')
                            pages = owner.page_footer.epub_pagination.pages
                            for _ in range(100):
                                if pages.complete:
                                    break
                                await asyncio.sleep(.1)
                            row['chapter_counts'] = pages.counts.copy()
                            if not pages.complete or pages.counts[owner.page_footer.epub_pagination.chapter] != dom['count']:
                                row['errors'].append('Footer page count differs from the EPUB layout')
                        report['samples'].append(row)
                        (output / 'progress.json').write_text(json.dumps(report, indent=2))
                        return row
                    await record_sample(name + '-opening', 'landscape-left', opening=True)
                    for orientation in ('portrait', 'landscape-left', 'landscape-right'):
                        await record_sample(name, orientation)
                    for hidden in (True, False):
                        if imported:
                            owner.set_reading_mode(hidden)
                        else:
                            owner.toggle_private_reading_mode()
                        await asyncio.sleep(.6)
                    await record_sample(name + '-restored', 'landscape-right', opening=True)
                    if (Path(self.paths.cache) / 'drive-folds').exists():
                        orientation = 'portrait' if path == epub else 'landscape-right'
                        await rotate(self, orientation, settle=.5)
                        first_fold = None
                        for angle in (0, 180, 0):
                            request = dict(viewer=name, angle=angle)
                            acknowledgement = output / 'fold-done.json'
                            pending = output / 'fold-request.tmp'
                            pending.write_text(json.dumps(request))
                            pending.replace(output / 'fold-request.json')
                            acknowledgement.unlink(missing_ok=True)
                            for _ in range(300):
                                if acknowledgement.exists() and json.loads(acknowledgement.read_text()) == request:
                                    break
                                await asyncio.sleep(.1)
                            else:
                                raise AssertionError('External fold driver did not acknowledge the real pose')
                            await asyncio.sleep(1)
                            row = await record_sample(name + '-fold-' + str(angle), orientation, opening=True)
                            if path == epub and angle == 0:
                                if first_fold is None:
                                    first_fold = row['chapter_counts']
                                elif row['chapter_counts'] != first_fold:
                                    row['errors'].append('Returning to folded portrait changed the page count')
                    self.request_reader_close(owner.session.id)
                    for _ in range(100):
                        if owner.session.id not in self.workspace.sessions:
                            break
                        await asyncio.sleep(.1)
                    assert owner.session.id not in self.workspace.sessions
            report['success'] = bool(report['samples']) and not any(row['errors'] for row in report['samples'])
        except Exception:
            report['errors'].append(traceback.format_exc())
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        (Path(self.paths.cache) / 'viewer-layout-result.json').write_text(json.dumps(report, indent=2))


def main():
    return ReaderTitleProbe('Reader Title QA', BUNDLE)
