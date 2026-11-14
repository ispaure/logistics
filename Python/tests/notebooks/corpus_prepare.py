"""Synthetic-only rehearsal of Brief 01 retrieval and desktop corpus receipts.

Run via build_retention --scratch. There is deliberately no tablet/host option.
"""
import argparse
from contextlib import contextmanager
from io import BufferedReader, BytesIO
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import traceback
from unittest.mock import patch
from zipfile import ZipFile

from features.notebooks import remarkable_ssh
from features.notebooks.notebook import MAX_ARCHIVE, Notebook
from tests.notebooks.corpus_receipts import checkpoint, run_batch


def synthetic_corpus(*, conservative=False):
    from features.pdf.annotation import notebook_from_pdf
    from tests.readers.test_pdf_reader import pdf_bytes

    plain = Notebook.new('Duplicate title', template='Blank')
    for _ in range(6):
        plain.add_page()
    pdf = notebook_from_pdf(pdf_bytes(), 'Duplicate title')
    modern = notebook_from_pdf(pdf_bytes(), 'Modern PDF')
    modern.content.update(formatVersion=2, zoomMode='fitToHeight', cPages={'pages': []})
    modern.content.pop('pages', None)
    books = [plain, pdf, modern]
    for book in books:
        for index in range(len(book.pages)):
            book.page(index).add([[400, 220 + index * 20, .5], [650, 220 + index * 20, .8]], tool=17, width=2)
    if conservative:
        # Unknown-shape controls: blank/multiple/hidden ink, preservation-only
        # page bytes and a backing type the real reader explicitly rejects.
        from features.notebooks.ink import InkPage
        plain.page(0).strokes.clear()
        plain.page(6).add([[500, 500, .5], [650, 500, .5]])
        plain.page(6).layers = [(key, name, False) for key, name, _ in plain.page(6).layers]
        blank = Notebook.new('Blank control', template='Blank')
        preserved = Notebook.new('Preservation control', template='Blank')
        preserved.pages[0].ink = InkPage.read(b'reMarkable .lines file, version=5          ')
        unsupported = Notebook.new('Unsupported backing')
        unsupported.content['fileType'] = 'epub'
        unsupported.members[unsupported.id + '.epub'] = b'synthetic opaque background'
        from features.notebooks.editor import Editor
        from tests.notebooks.image_fixtures import paste_action
        mixed = Notebook.new('Mixed ink and image control', template='Blank')
        editor = Editor(mixed)
        editor.apply(dict(op='stroke', points=[[450, 400, .5], [750, 400, 1]]))
        editor.apply(paste_action())
        editor.apply(dict(op='stroke', points=[[450, 600, 1], [650, 800, .5]]))
        editor.apply(dict(op='arrange-image', id=mixed.page(0).images[0].id, direction='front'))
        books.extend((blank, preserved, unsupported, mixed))
    folder = '10000000-0000-4000-8000-000000000001'
    nested = '10000000-0000-4000-8000-000000000002'
    metadata = {folder: dict(type='CollectionType', visibleName='Duplicate title'),
                nested: dict(type='CollectionType', visibleName='Nested', parent=folder),
                '10000000-0000-4000-8000-000000000003': dict(type='FutureType'),
                '10000000-0000-4000-8000-000000000004': dict(type='DocumentType', deleted=True),
                '10000000-0000-4000-8000-000000000005': b'invalid json',
                'unidentified': dict(type='FutureType')}
    archives = {}
    for index, book in enumerate(books):
        book.metadata['parent'] = nested if index else folder
        metadata[book.id] = dict(book.metadata)
        with ZipFile(BytesIO(book.to_bytes())) as archive:
            archives[book.id] = {name: archive.read(name) for name in archive.namelist()}
    return metadata, archives


def tar_bytes(members):
    result = BytesIO()
    with tarfile.open(fileobj=result, mode='w') as archive:
        for name, value in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            archive.addfile(member, BytesIO(value))
    return result.getvalue()


def conservative_page_receipt(expected, measured):
    """Check editor delivery, never infer visual correctness from unknown ink."""
    assert measured['index'] == expected['index'] and measured['count'] == expected['count']
    assert measured['strokes'] == len(expected['strokes'])
    assert measured['images'] == len(expected['images'])
    assert measured['scene_order'] == expected['scene_order']
    assert measured['decoded_images'] == measured['visible_images']
    assert all(math.isfinite(value) and value > 0 for value in (*measured['canvas'], measured['dpr'], measured['css_scale']))
    assert not expected['background'] or measured['background']
    if expected['password_required']:
        status, reason = 'blocked', 'password_required'
    elif expected['warning']:
        status, reason = 'unsupported', 'preservation_only_page'
    elif expected['template_editable'] and expected['template_settings']['visible'] and not expected['template_available']:
        status, reason = 'unsupported', 'template_artwork_unavailable'
    else:
        status, reason = 'observed', 'visual_reference_unavailable'
    return dict(page=expected['index'], status=status, reason=reason, measured=measured)


def desktop_inspector(workspace, *, synthetic=False):
    """Open arbitrary documents conservatively; strict fixture assertions opt in."""
    from commonUtils.ui import pyside as qt
    from features.notebooks.ui.workspace import NotebookWorkspace, NotebookWindow
    from features.notebooks.ui.menus import NotebookMenus
    from features.notebooks.storage import NotebookDocument
    from services.documents.storage import local_document_resource
    from tests.notebooks.notebook_desktop_stress_probe import Probe

    def inspect(source, pages, receipt):
        target = workspace / (source.stem + '-editable.rmdoc')
        shutil.copyfile(source, target)
        probe = None
        phase = 'editor_open'

        def open_copy():
            instance = Probe.__new__(Probe)
            instance.window_states = []
            instance.window = NotebookWindow()
            instance.panel = NotebookWorkspace(instance.window, root=workspace / 'recovery', library=False)
            instance.window.setCentralWidget(instance.panel)
            instance.window.notebook_menus = NotebookMenus(instance.window)
            instance.window.resize(1100, 900)
            instance.window.show()
            resource = None
            try:
                resource = local_document_resource(target, max_bytes=MAX_ARCHIVE)
                book = Notebook.read(resource.read())
                instance.panel.open_resource(NotebookDocument(book, resource=resource, recovery=instance.panel.repository))
                instance.ready()
                return instance
            except BaseException:
                if resource is not None:
                    resource.close()
                instance.window.close()
                instance.window.deleteLater()
                raise

        try:
            probe = open_copy()
            original = Notebook.read(source.read_bytes())
            assert [page.id for page in probe.panel.editor.notebook.pages] == [page.id for page in original.pages]
            if synthetic:
                assert len(original.pages) == (7 if original.content['fileType'] == 'notebook' else 3)
            receipt[phase] = dict(status='passed', path='NotebookWorkspace.open_resource', backend=qt.QApplication.instance().platformName())
            phase = 'page_render'
            rendered = []
            for page in pages:
                probe.action('page', index=page)
                expected = probe.panel.editor.state()
                if synthetic:
                    assert len(expected['strokes']) == 1
                if synthetic and original.content['fileType'] == 'pdf':
                    assert expected['background'] and expected['background'].startswith('data:image/png;base64,')
                if expected['background']:
                    probe.wait(lambda: probe.js("$('pdfBackground').complete&&$('pdfBackground').naturalWidth>0"), 'background decoded')
                    assert probe.js("$('pdfBackground').src") == expected['background']
                if not synthetic:
                    probe.wait(lambda: probe.js("state.password_required||(state.images||[]).filter(imageVisible).every(p=>imageCache.get(p.src)?.complete&&imageCache.get(p.src)?.naturalWidth>0)"), 'visible images decoded')
                    value = probe.js("({index:state.index,count:state.count,strokes:state.strokes.length,images:state.images.length,scene_order:state.scene_order,visible_images:state.password_required?0:state.images.filter(imageVisible).length,decoded_images:state.password_required?0:state.images.filter(p=>imageVisible(p)&&imageCache.get(p.src)?.complete&&imageCache.get(p.src)?.naturalWidth>0).length,canvas:[canvas.width,canvas.height],dpr:devicePixelRatio,css_scale:canvas.getBoundingClientRect().width/state.width,background:!$('pdfBackground').hidden&&$('pdfBackground').naturalWidth>0})")
                    rendered.append(conservative_page_receipt(expected, value))
                    continue
                value = probe.js("(()=>{const keep=state.strokes;draw();const p=ctx.getImageData(0,0,canvas.width,canvas.height).data;let ink=0;try{state.strokes=[];draw();const b=ctx.getImageData(0,0,canvas.width,canvas.height).data;for(let i=0;i<p.length;i+=4)if(p[i]!==b[i]||p[i+1]!==b[i+1]||p[i+2]!==b[i+2]||p[i+3]!==b[i+3])ink++;}finally{state.strokes=keep;draw()}return {index:state.index,strokes:state.strokes.length,ink_pixels:ink,canvas:[canvas.width,canvas.height],dpr:devicePixelRatio,css_scale:canvas.getBoundingClientRect().width/state.width,background:!$('pdfBackground').hidden&&$('pdfBackground').naturalWidth>0}})()")
                assert value['index'] == page
                assert value['strokes'] == len(expected['strokes'])
                assert not expected['strokes'] or value['ink_pixels'] > 0
                assert not expected['background'] or value['background']
                if expected['background']:
                    assert probe.js("$('pdfBackground').src") == expected['background']
                rendered.append(dict(page=page, measured=value, preservation_warning=bool(expected['warning'])))
            if not synthetic:
                statuses = {page['status'] for page in rendered}
                receipt[phase] = dict(status=next((status for status in ('blocked', 'unsupported') if status in statuses), 'observed'),
                                      pages=rendered, scope='Actual editor delivery and background decode only; visual correctness unverified')
                receipt['save_reopen'] = dict(status='untested', reason='conservative_inspection_does_not_edit')
                return
            receipt[phase] = dict(status='passed', pages=rendered, scope='Pixel difference with ink removed and background decode; no native visual reference')
            phase = 'save_reopen'
            probe.action('page', index=0)
            before = probe.count()
            probe.action('stroke', points=[[450, 300, .5], [600, 300, .8]], tool=17, width=2, color=0)
            probe.action('save')
            assert not probe.panel.document.dirty
            saved = Notebook.read(target.read_bytes())
            assert len(saved.page(0).strokes) == before + 1
            for index in range(len(original.pages)):
                assert [stroke.payload() for stroke in saved.page(index).strokes[:1]] == [stroke.payload() for stroke in original.page(index).strokes]
            if original.content['fileType'] == 'pdf':
                assert saved.members[saved.id + '.pdf'] == original.members[original.id + '.pdf']
            probe.close()
            probe.window.deleteLater()
            probe = None
            qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            probe = open_copy()
            probe.action('page', index=0)
            assert probe.count() == before + 1
            receipt[phase] = dict(status='passed', added_strokes=1, scope='Desktop command, Save, close and real editor reopen on disposable copy')
        except Exception as error:
            receipt[phase] = dict(status='failed', error_type=type(error).__name__)
            if synthetic:
                traceback.print_exc()
            raise
        finally:
            if probe is not None:
                with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Ok):
                    probe.close()
                probe.window.deleteLater()
            qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
    return inspect


def main(output, *, conservative=False):
    if not os.environ.get('COMMONUTILS_STORAGE_ROOT'):
        raise RuntimeError('Run through logistics_build.build_retention --scratch.')
    from commonUtils.ui import pyside as qt
    from tests.notebooks.corpus_calibration import calibrate
    app = qt.QApplication.instance() or qt.QApplication([])
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    metadata, archives = synthetic_corpus(conservative=conservative)
    requests = []

    @contextmanager
    def synthetic_stream(host, command, cancelled, *, port=22):
        assert host == 'synthetic.invalid'
        if command.startswith('set -- ./*.metadata'):
            members = {key + '.metadata': value if isinstance(value, bytes) else json.dumps(value).encode() for key, value in metadata.items()}
        else:
            identity = command.split("identity='", 1)[1].split("'", 1)[0]
            members = archives[identity]
            requests.append(identity)
        with BufferedReader(BytesIO(tar_bytes(members))) as stream:
            yield stream

    with patch.object(remarkable_ssh, 'ssh_stream', synthetic_stream):
        snapshot = remarkable_ssh.list_snapshot('synthetic.invalid')
        retrieve = lambda identity, target: remarkable_ssh.export_document('synthetic.invalid', identity, target)
        inspect = desktop_inspector(Path.cwd(), synthetic=not conservative)
        report = run_batch(snapshot, output, retrieve, inspect, document_ids=archives)
        first_exports = len(requests)
        report = run_batch(snapshot, output, retrieve, inspect, document_ids=archives)
        assert len(requests) == first_exports == len(archives)
    calibration = calibrate()
    checkpoint(output / 'calibration.json', calibration)
    source = Path(__file__).resolve().parents[3]
    def revision(path):
        return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    from tests.notebooks.corpus_receipts import digest
    summary = dict(synthetic_only=True, totals=report['totals'], resume_export_calls=len(requests),
                   calibration=calibration, backend=app.platformName(), physical_hardware=False,
                   editor_expectation='conservative' if conservative else 'synthetic', live_acquisition_enabled=False)
    summary['source'] = dict(logistics=revision(source), commonUtils=revision(source / 'Python/commonUtils'),
                            modules_sha256={name: digest(Path(__file__).with_name(name)) for name in
                                ('corpus_prepare.py', 'corpus_receipts.py', 'corpus_calibration.py')}, python=sys.version)
    checkpoint(output / 'summary.json', summary)
    print(json.dumps(dict(synthetic_only=True, totals=report['totals'], resume_export_calls=len(requests))))
    outcomes = ({'page_render_observed': 5, 'page_render_unsupported': 1, 'editor_open_unsupported': 1}
                if conservative else {'passed': 3})
    return int(report['totals']['outcomes'] != outcomes or not calibration['passed'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--conservative', action='store_true', help='Rehearse arbitrary-shape expectations using only generated fixtures')
    args = parser.parse_args()
    raise SystemExit(main(args.output, conservative=args.conservative))
