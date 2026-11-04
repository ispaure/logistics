"""Actual Android WebView/iOS WKWebView image and password acceptance."""
import asyncio
import base64
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from mobile.app import LogisticsMobile
from . import start_native_check
from .fixtures import capture_window
from .notebook_image_checks import exercise_notebook_images

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
        report=dict(success=False,providers=[],error='')
        try:
            if getattr(self,'startup_task',None) is not None:
                await asyncio.shield(self.startup_task)
            for _ in range(400):
                if not getattr(self,'_startup_in_progress',False):break
                await asyncio.sleep(.1)
            assert not getattr(self,'_startup_in_progress',False)
            # Only this isolated standalone app imports credentials. The shared
            # required normal-suite runner reuses its existing Secret session.
            fixtures=json.loads(Path(__file__).with_name('notebook-image-fixture.json').read_text())
            self.show_cloud()
            if getattr(self,'cloud_restore_task',None):await self.cloud_restore_task
            self.cloud_client.request('import',package=fixtures['credentials'],password='image-qa-session',
                                      package_name='ImageQA.zip',session_only=True)
            report=await exercise_notebook_images(self,output=output)
        except Exception:
            report=getattr(self,'_notebook_image_report',report)
            report['success']=False
            report['error']=traceback.format_exc()
            print(report['error'],flush=True)
            try:await capture_window(self,output/'image-failure.png')
            except Exception:pass
        finally:
            report['artifacts']={p.name:base64.b64encode(p.read_bytes()).decode()
                for p in output.iterdir() if p.suffix in ('.png','.rmdoc')}
            (Path(self.paths.cache)/'notebook-image-result.json').write_text(json.dumps(report))


def main():
    return Probe('Notebook image QA',BUNDLE)
