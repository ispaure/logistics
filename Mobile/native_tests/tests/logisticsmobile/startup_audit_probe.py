"""Independent section checks using real iOS paths and upgrade restoration."""
import asyncio
import inspect
import json
from pathlib import Path
import traceback
import logisticsmobile

from logisticsmobile.app import LogisticsMobile
from .fixtures import capture_window, make_books


class Probe(LogisticsMobile):
    def startup(self):
        # Deliberately keep storage_root=None: exercise the normal iOS migration.
        try:
            super().startup()
        except BaseException:
            (Path(self.paths.cache) / 'startup-audit-error.txt').write_text(traceback.format_exc())
            raise

    def on_running(self):
        self.loop.create_task(self.audit())

    async def audit(self):
        output = Path(self.paths.cache) / 'startup-audit'
        output.mkdir(exist_ok=True)
        report = dict(success=False, sections=[], asynchronous_errors=[],
            source=json.loads(Path(logisticsmobile.__file__).with_name('source.json').read_text()))
        previous_handler = self.loop.get_exception_handler()

        def failed_task(loop, context):
            report['asynchronous_errors'].append(str(context.get('exception') or context.get('message')))
            if previous_handler is not None:
                previous_handler(loop, context)

        self.loop.set_exception_handler(failed_task)

        async def check(name, action):
            item = dict(name=name, success=False)
            try:
                result = action()
                if inspect.isawaitable(result):
                    result = await asyncio.wait_for(result, 45)
                if result is False:
                    raise AssertionError('Section returned failure')
                pending = getattr(self, 'cloud_restore_task', None)
                if pending is not None and not pending.done():
                    await asyncio.wait_for(asyncio.shield(pending), 20)
                await asyncio.sleep(.5)
                await capture_window(self, output / (name + '.png'))
                item['success'] = True
            except Exception:
                item['error'] = traceback.format_exc()
                item['status'] = {name: str(getattr(getattr(self, name, None), 'value',
                    getattr(getattr(self, name, None), 'text', ''))) for name in ('cloud_status', 'file_status', 'status')}
            report['sections'].append(item)
            (output / 'result.json').write_text(json.dumps(report, indent=2))

        def restored_draft():
            expected_path = self.private_root / 'audit-expectations.json'
            if expected_path.exists():
                expected = json.loads(expected_path.read_text())
                document = self.store.open(expected['document'])
                assert document.text == expected['draft']
                assert self.current is not None and self.current.id == expected['document']
                assert self.current.text == expected['draft']

        try:
            await check('restored-draft', restored_draft)
            for name, action in (
                ('home', self.show_home), ('workspaces', self.show_locations),
                ('documents', self.show_documents_hub), ('settings', self.show_settings),
                ('rclone-connections', self.show_cloud_connections),
                ('credential-import', self.show_cloud_import), ('smb-shares', self.show_smb_connection),
                ('local-files', lambda: self.show_files(local_root=True)),
                ('chat', self.show_chat), ('chat-settings', self.show_chat_configuration),
            ):
                await check(name, action)
            from logisticsmobile.documentation_ui import show_documentation
            await check('documentation', lambda: show_documentation(self))
            from features.rclone.mobile.storage_location import collection_path
            local = collection_path(self.private_root)
            local.mkdir(exist_ok=True)
            epub, comic = make_books(local)
            from pypdf import PdfWriter
            pdf = local / 'Fixture.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=400)
            writer.write(pdf)
            for name, path in (('epub', epub), ('comic', comic), ('pdf', pdf)):
                await check(name, lambda path=path: self.open_download(path=path))
            await check('home-after-readers', self.show_home)
            report['success'] = all(item['success'] for item in report['sections']) and not report['asynchronous_errors']
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            self.loop.set_exception_handler(previous_handler)
            (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    return Probe('Startup Audit', 'io.github.ispaure.logisticsupgradeaudit')
