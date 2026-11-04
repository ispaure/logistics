"""Actual Android WebView/iOS WKWebView image and password acceptance."""
import asyncio
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from services.documents.storage import DocumentResource
from mobile.app import LogisticsMobile
from . import start_native_check
from .fixtures import capture_window
from .notebook_image_checks import ImageWorkflow, HELPERS, signature

TEST_STAGE = TestStage.REGRESSION
BUNDLE = 'io.github.ispaure.logisticsnotebookqa'


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root=Path(self.paths.cache)/'image-qa-storage'
        super().startup()

    def on_running(self):
        start_native_check(self,self.check)

    async def check(self,app):
        output=Path(self.paths.cache)/'notebook-ui';output.mkdir(exist_ok=True)
        report=dict(success=False,scope='Real native WebView, command bridge, PDF renderer and LocalCrypt bridge; synthetic pointer delivery',providers=[])
        provider=None;panel=None
        try:
            if getattr(self,'startup_task',None) is not None:
                await asyncio.shield(self.startup_task)
            for _ in range(400):
                if not getattr(self,'_startup_in_progress',False):break
                await asyncio.sleep(.1)
            assert not getattr(self,'_startup_in_progress',False)
            self.set_feature_enabled('notebooks',True,refresh=False)
            self.show_home()
            fixtures=json.loads(Path(__file__).with_name('notebook-image-fixture.json').read_text())
            original=base64.b64decode(fixtures['rmdoc']);original_book=Notebook.read(original)
            original_pdf=original_book.members[original_book.id+'.pdf']
            from features.notebooks.mobile.documents import open_notebook,close_notebook
            from features.rclone.localcrypt.mobile.resources import CryptFiles
            for label in ('Local','LocalCrypt'):
                if label=='Local':
                    root=Path(self.private_root)/'image-local';root.mkdir()
                    provider=LocalFiles(root)
                else:
                    self.show_cloud()
                    if getattr(self,'cloud_restore_task',None):await self.cloud_restore_task
                    self.cloud_client.request('import',package=fixtures['credentials'],password='image-qa-session',package_name='ImageQA.zip',session_only=True)
                    provider=CryptFiles(Path(self.private_root)/'image-crypt',self.cloud_client,'Secret')
                provider.create_file('images.rmdoc',BytesIO(original))
                resource=DocumentResource(provider,'images.rmdoc',max_bytes=MAX_ARCHIVE)
                assert await open_notebook(self,resource=resource)
                panel=self.notebook_panel
                backend=type(panel.web._impl).__module__
                assert backend.startswith(('toga_iOS.','toga_android.')),backend
                async def evaluate(code):return await panel.web.evaluate_javascript(code)
                async def capture(phase):
                    await capture_window(self,output/(label+'-'+phase+'.png'))
                    encoded=await evaluate("canvas.toDataURL('image/png')")
                    (output/(label+'-'+phase+'-canvas.png')).write_bytes(base64.b64decode(encoded.split(',',1)[1]))
                workflow=ImageWorkflow(evaluate,lambda:panel.editor,capture)
                await workflow.run()
                expected=signature(panel.editor.notebook)
                assert panel.document.resource.read()==original,'Source changed before Save'
                if label=='Local':
                    recovered=panel.document.recovery.open(panel.document.key)
                    assert signature(recovered)==expected
                else:assert panel.document.recovery is None
                await workflow.send(dict(op='save'))
                saved=panel.document.resource.read();book=Notebook.read(saved)
                assert signature(book)==expected
                assert book.members[book.id+'.pdf']==original_pdf
                (output/(label+'-saved.rmdoc')).write_bytes(saved)
                if label=='LocalCrypt':
                    ciphertext=provider._physical('images.rmdoc').read_bytes()
                    assert b'%PDF' not in ciphertext and b'PNG' not in ciphertext
                assert close_notebook(self,panel.session.id,'discard')
                assert await open_notebook(self,resource=DocumentResource(provider,'images.rmdoc',max_bytes=MAX_ARCHIVE))
                panel=self.notebook_panel
                reopened=ImageWorkflow(evaluate,lambda:panel.editor,capture)
                await reopened.idle();await evaluate(HELPERS);await reopened.unlock()
                assert signature(panel.editor.notebook)==expected
                await capture('reopened')
                report['providers'].append(dict(provider=label,backend=backend,cases=workflow.cases,
                    saved_sha256=sha256(saved).hexdigest(),password_reprompt=True,pdf_ciphertext_preserved=True,
                    recovery_checked=label=='Local',reopened=True))
                assert close_notebook(self,panel.session.id,'discard');panel=None
                getattr(provider,'close',lambda:None)();provider=None
            report['success']=True
        except Exception:
            report['error']=traceback.format_exc()
            print(report['error'],flush=True)
            try:await capture_window(self,output/'image-failure.png')
            except Exception:pass
        finally:
            if panel is not None:
                try:close_notebook(self,panel.session.id,'discard')
                except Exception:pass
            if provider is not None:getattr(provider,'close',lambda:None)()
            report['artifacts']={p.name:base64.b64encode(p.read_bytes()).decode() for p in output.iterdir() if p.suffix in ('.png','.rmdoc')}
            (Path(self.paths.cache)/'notebook-image-result.json').write_text(json.dumps(report))


def main():
    return Probe('Notebook image QA',BUNDLE)
