"""Native PDF-to-notebook menus, backgrounds, collisions and timed pen input."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from io import BytesIO
import json
from pathlib import Path
import traceback

from .notebook_probe import NotebookProbe


class PDFAnnotationProbe(NotebookProbe):
    async def check(self, app):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, NameObject
        from features.pdf.annotation import LABEL
        from features.notebooks.notebook import Notebook
        from .fixtures import capture_window
        from .web_checks import wait_for_text
        output = Path(self.paths.cache)
        report = dict(success=False, synthetic=True, physical_pencil_tested=False)
        try:
            for _ in range(400):
                if not getattr(app, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            task = getattr(app, 'cloud_startup_task', None)
            if task is not None:
                await task
            app.show_home()
            app.set_feature_enabled('notebooks', True, refresh=False)
            data = BytesIO()
            with PdfWriter() as writer:
                for color in ('1 0 0', '0 0.6 0'):
                    page = writer.add_blank_page(width=300, height=450)
                    stream = DecodedStreamObject()
                    stream.set_data((color + ' rg 20 20 80 400 re f').encode())
                    page[NameObject('/Contents')] = writer._add_object(stream)
                writer.write(data)
            source = Path(app.private_root) / 'LocalFiles/annotation.pdf'
            source.parent.mkdir(parents=True, exist_ok=True)
            original = data.getvalue()
            source.write_bytes(original)
            assert await app.open_download(path=source)
            owner = app.private_sessions.active
            callback = next(callback for label, callback in owner.crypt_action_items if label == LABEL)
            assert await callback(), 'PDF reader annotation action did not open a notebook'
            panel = app.notebook_panel
            await wait_for_text(panel.web, 'annotation')
            async def js(script):
                return await panel.web.evaluate_javascript(script)
            async def value(expression):
                return json.loads(await js('JSON.stringify(' + expression + ')'))
            async def idle():
                for _ in range(1000):
                    if not panel.busy and await value('!busy && !queue.length'):
                        return
                    await asyncio.sleep(.02)
                raise AssertionError('Notebook queue did not drain')
            for _ in range(100):
                if await value("$('pdfBackground').complete && $('pdfBackground').naturalWidth > 0"):
                    break
                await asyncio.sleep(.05)
            assert await value("!$('pdfBackground').hidden && $('pdfBackground').naturalWidth > 0")
            background = await value("$('pdfBackground').src")
            await js('send({op:"page",index:1})')
            await idle()
            assert await value("$('pdfBackground').src") != background
            report['distinct_pdf_backgrounds'] = True
            await js(BENCHMARK + ';void 0')
            report['latency'] = []
            for batched in (False, True):
                await js('window.annotationBench(' + str(batched).lower() + ');void 0')
                for _ in range(1000):
                    if await value('window.annotationBenchResult !== null'):
                        break
                    await asyncio.sleep(.02)
                result = await value('window.annotationBenchResult')
                assert result and not result.get('error'), result
                await idle()
                assert len(panel.editor.notebook.page(1).strokes) == len(report['latency']) + 1
                report['latency'].append(result)
            assert report['latency'][1]['paint_batches'] < report['latency'][0]['paint_batches'], report
            assert all(len(s.points) == 241 for s in panel.editor.notebook.page(1).strokes)
            await js('send({op:"save"})')
            await idle()
            destination = source.with_suffix('.rmdoc')
            saved = destination.read_bytes()
            reopened = Notebook.read(saved)
            assert reopened.members[reopened.id + '.pdf'] == original
            assert len(reopened.page(1).strokes) == 2
            assert source.read_bytes() == original
            report['sibling_save_and_readback'] = True
            # Exercise the user-facing error path without leaving a modal dialog
            # awaiting manual dismissal in a disposable automated test.
            from features.pdf.mobile.annotation import annotate_pdf
            dialogs = []
            import toga
            real_error = toga.ErrorDialog
            def error_dialog(title, message):
                dialogs.append(message)
                return real_error(title, message)
            real_dialog = app.main_window.dialog
            async def capture(dialog):
                return None
            toga.ErrorDialog = error_dialog
            app.main_window.dialog = capture
            try:
                assert not await annotate_pdf(owner, owner.crypt_reader)
            finally:
                toga.ErrorDialog = real_error
                app.main_window.dialog = real_dialog
            assert dialogs and 'already exists' in dialogs[0], dialogs
            assert destination.read_bytes() == saved
            report['collision_error_preserves_destination'] = True
            await capture_window(app, output / 'pdf-annotation.png')
            report['backend'] = type(panel.web._impl).__module__
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'pdf-annotation-result.json').write_text(json.dumps(report, indent=2))
        print('PDF_ANNOTATION=' + json.dumps(report), flush=True)


BENCHMARK = r"""
window.annotationBenchResult=null;
window.annotationBench=async function(batched){
  window.annotationBenchResult=null;
  const oldPreview=preview;let batches=0,frames=[],lastTime=performance.now();
  preview=function(...args){batches++;return oldPreview(...args)};
  frameBatchedInk=batched;
  $('tool').value='15';brushOptions();$('color').value='0';$('width').value='2';
  const rect=canvas.getBoundingClientRect();
  function event(x){return {pointerId:987,pointerType:'pen',pressure:.5,
    clientX:rect.left+rect.width*(.2+x*.002),clientY:rect.top+rect.height*.35,
    nativePen:true,preventDefault(){}}}
  const capture=canvas.setPointerCapture;canvas.setPointerCapture=()=>{};
  const started=performance.now();
  try{
    canvas.onpointerdown(event(0));
    for(let frame=0;frame<30;frame++){
      await new Promise(requestAnimationFrame);
      const now=performance.now();frames.push(now-lastTime);lastTime=now;
      for(let i=1;i<=8;i++)canvas.onpointermove(event(frame*8+i));
    }
    canvas.onpointerup(event(240));
    window.annotationBenchResult={batched,paint_batches:batches,
      duration_ms:performance.now()-started,max_frame_gap_ms:Math.max(...frames),samples:241};
  }catch(e){window.annotationBenchResult={error:String(e)}}
  finally{preview=oldPreview;canvas.setPointerCapture=capture}
};
"""


def main():
    return PDFAnnotationProbe('PDF Annotation QA', 'io.github.ispaure.logisticsnotebookqa')
