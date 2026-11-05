"""Native Qt notebook cutout/password acceptance through both real providers."""
import argparse
import asyncio
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import struct
import traceback
import zlib

from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from features.notebooks.editor import Editor
from features.notebooks.storage import NotebookDocument
from features.notebooks.recovery import Repository
from features.notebooks.ui.workspace import NotebookWorkspace
from features.rclone import executable
from logistics_build.build_retention import scratch
from services.documents.storage import DocumentResource
from tests.local_crypt_fixture import crypt_fixture
from tests.notebooks.image_fixtures import fixture_bytes
from tests.notebooks.webengine_driver import javascript
from mobile_build.native_tests.tests.logisticsmobile.notebook_image_checks import ImageWorkflow, signature


def main(output, rclone=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    app=qt.QApplication.instance() or qt.QApplication([])
    report=dict(success=False,scope='Native macOS Qt WebEngine; actual Local/LocalCrypt resources',providers=[])
    workspace=None;workflow=None
    try:
        with scratch() as work, crypt_fixture(work,rclone or executable.get_rclone_path(),pull=False) as fixture:
            # The probe owns this provider across closing and reopening documents.
            # A document's last release must still lock an otherwise unowned session.
            release_provider = fixture.provider.acquire()
            try:
                for label,provider in [('Local',LocalFiles(fixture.plain)),('LocalCrypt',fixture.provider)]:
                    original=fixture_bytes();name='image-qa.rmdoc'
                    DocumentResource.publish(provider,name,original,max_bytes=MAX_ARCHIVE,validate=Notebook.read)
                    original_pdf=Notebook.read(original).members[Notebook.read(original).id+'.pdf']
                    repository=Repository(work/('recovery-'+label)) if not provider.private else None
                    resource=DocumentResource(provider,name,max_bytes=MAX_ARCHIVE)
                    document=NotebookDocument(Notebook.read(resource.read()),resource=resource,recovery=repository)
                    workspace=NotebookWorkspace(root=work/'unused',library=False)
                    workspace.resize(1250,950);workspace.show();workspace.open_resource(document)
                    async def evaluate(code):
                        return javascript(workspace.web,code)
                    async def capture(phase):
                        workspace.web.grab().save(str(output/(label+'-'+phase+'.png')))
                        encoded=await evaluate("canvas.toDataURL('image/png')")
                        (output/(label+'-'+phase+'-canvas.png')).write_bytes(base64.b64decode(encoded.split(',',1)[1]))
                    workflow=ImageWorkflow(evaluate,lambda:workspace.editor,capture)
                    asyncio.run(workflow.run())
                    expected=signature(workspace.editor.notebook)
                    assert workspace.document.resource.read()==original,'Source changed before explicit Save'
                    if repository:
                        assert signature(repository.open(document.key))==expected,'Recovery lost image geometry/order'
                    else:
                        assert workspace.document.recovery is None
                    asyncio.run(workflow.send(dict(op='save')))
                    saved=workspace.document.resource.read();loaded=Notebook.read(saved)
                    assert signature(loaded)==expected
                    assert loaded.members[loaded.id+'.pdf']==original_pdf
                    (output/(label+'-saved.rmdoc')).write_bytes(saved)
                    if provider.private:
                        ciphertext=provider.encrypted_path(name).read_bytes()
                        assert b'%PDF' not in ciphertext and b'PNG' not in ciphertext
                    workspace.dispose();workspace.close();workspace.deleteLater();workspace=None
                    resource=DocumentResource(provider,name,max_bytes=MAX_ARCHIVE)
                    workspace=NotebookWorkspace(root=work/'unused',library=False)
                    workspace.resize(1250,950);workspace.show()
                    workspace.open_resource(NotebookDocument(Notebook.read(resource.read()),resource=resource,recovery=repository))
                    reopened=ImageWorkflow(evaluate,lambda:workspace.editor,capture)
                    asyncio.run(reopened.idle());asyncio.run(evaluate(__import__('mobile_build.native_tests.tests.logisticsmobile.notebook_image_checks',fromlist=['HELPERS']).HELPERS))
                    asyncio.run(reopened.unlock())
                    assert signature(workspace.editor.notebook)==expected
                    asyncio.run(capture('reopened'))
                    report['providers'].append(dict(provider=label,cases=workflow.cases,
                        saved_sha256=sha256(saved).hexdigest(),password_reprompt=True,pdf_ciphertext_preserved=True,
                        recovery_checked=repository is not None,reopened=True))
                    workspace.dispose();workspace.close();workspace.deleteLater();workspace=None
                    app.sendPostedEvents(None,qt.QEvent.Type.DeferredDelete);app.processEvents()
                report['success']=True
            except Exception:
                report['error']=traceback.format_exc()
                report['partial_cases']=workflow.cases if workflow else []
                if workspace is not None and workspace.web is not None:
                    try:
                        report['canvas_state']=json.loads(javascript(workspace.web,"JSON.stringify({locked:state.password_required,count:state.images.length,status:$('status').textContent,pasteDisabled:$('pasteImage').disabled})"))
                        workspace.web.grab().save(str(output/'failure.png'))
                    except Exception:pass
                raise
            finally:
                try:
                    if workspace is not None:
                        workspace.dispose();workspace.close();workspace.deleteLater();workspace=None
                finally:
                    try:
                        app.sendPostedEvents(None,qt.QEvent.Type.DeferredDelete)
                        app.processEvents()
                    finally:
                        release_provider()
    finally:
        (output/'desktop-images-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(success=True,providers=[p['provider'] for p in report['providers']])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rclone',type=Path)
    args=parser.parse_args()
    main(args.output,args.rclone)
