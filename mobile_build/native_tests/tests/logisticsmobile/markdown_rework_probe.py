"""Native Markdown appearance, final-input persistence and library route checks."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
import time
from uuid import uuid4

from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies
from mobile.app import LogisticsMobile
from .fixtures import capture_window
from .web_checks import wait_for_text

TEXT = '# A calmer place to write\n\nA **bold idea**, some *emphasis* and a [link](Next.md).\n\n' \
       '## Today\n\n- Plan the next step\n- Keep the details together\n\n' \
       '  ~~~~c++ title="nested"\n  int value = 1;\n  ~~~~\n\n' \
       '> Good tools leave room for your thoughts.\n\n' \
       '| Task | Status |\n| :--- | ---: |\n| Markdown | Ready |\n\n' \
       '```python\nprint("Hello, world")\n```\n'


class MarkdownReworkProbe(LogisticsMobile):
    def startup(self):
        import logging
        logging.getLogger().addHandler(logging.FileHandler(Path(self.paths.cache) / 'markdown-qa-python.log', mode='w'))
        self.storage_root = Path(self.paths.cache) / ('markdown-rework-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_markdown_rework_started', False):
            self._markdown_rework_started = True
            self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'markdown-rework-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, backend=type(self._impl).__module__)
        try:
            started = time.monotonic()
            document = self.store.create('Writing.md', TEXT.encode())
            self.open_document(document.id)
            self.show_documents(edit=True)
            owner = self.editor_view
            document = owner.document
            assert "not a current item" not in owner.status.text, owner.status.text
            web = owner.formatted.view
            await wait_for_text(web, 'A calmer place to write')
            report['formatted_ready_seconds'] = time.monotonic() - started
            await asyncio.sleep(.5)
            metrics = json.loads(await web.evaluate_javascript('''JSON.stringify((() => {
                const root = document.getElementById('document');
                const h1 = root.querySelector('h1');
                const p = root.querySelector('p');
                const bounds = root.getBoundingClientRect();
                return {ready: document.documentElement.dataset.editorReady,
                    heading: parseFloat(getComputedStyle(h1).fontSize),
                    paragraph: parseFloat(getComputedStyle(p).fontSize),
                    bold: getComputedStyle(root.querySelector('strong')).fontWeight,
                    documentTop: bounds.top, documentBottom: bounds.bottom,
                    width: innerWidth, height: innerHeight, outerScroll: scrollY};
            })())'''))
            assert metrics['ready'] == 'true', metrics
            assert metrics['heading'] >= metrics['paragraph'] * 1.8, metrics
            assert int(metrics['bold']) >= 600, metrics
            assert metrics['documentBottom'] <= metrics['height'] + 1, metrics
            await capture_window(self, output / 'formatted.png')
            await web.evaluate_javascript("document.querySelector('nav details').open = true")
            panel = json.loads(await web.evaluate_javascript('''JSON.stringify((() => {
                const box = document.querySelector('.format-menu').getBoundingClientRect();
                return {top:box.top, bottom:box.bottom, height:innerHeight,
                    documentTop:document.getElementById('document').getBoundingClientRect().top};
            })())'''))
            assert panel['documentTop'] == metrics['documentTop'], panel
            assert panel['top'] >= 0 and panel['bottom'] <= panel['height'] + 1, panel
            await capture_window(self, output / 'formatting.png')
            # Deliberately omit input: Save must fetch the final native DOM draft.
            await web.evaluate_javascript("document.querySelector('nav details').open = false; document.querySelector('h1').append(' — saved 😀')")
            await web.evaluate_javascript("document.querySelector('ul li p').append(' — edited'); document.querySelector('td:last-child').append(' now')")
            assert 'saved 😀' not in document.text
            started = time.monotonic()
            await owner.save()
            report['final_input_save_seconds'] = time.monotonic() - started
            assert document.text.startswith('# A calmer place to write — saved 😀'), document.text
            assert not document.modified
            assert document.text.endswith('```python\nprint("Hello, world")\n```\n'), document.text
            assert '~~~~c++ title="nested"' in document.text, document.text
            assert '| :--- | ---: |' in document.text, document.text
            report['nested_fence_and_table_alignment'] = True
            report['managed'] = dict(metrics=metrics, formatting=panel, final_input_saved=True)
            from .rotation_checks import rotate, pose_snapshot
            report['rotation'] = []
            for orientation in ('landscape-left', 'landscape-right', 'portrait'):
                await rotate(self, orientation)
                geometry = json.loads(await web.evaluate_javascript('''JSON.stringify((() => {
                    const root=document.getElementById('document').getBoundingClientRect();
                    const nav=document.querySelector('nav').getBoundingClientRect();
                    return {top:root.top,bottom:root.bottom,height:innerHeight,
                        toolbarTop:nav.top,toolbarBottom:nav.bottom,outerScroll:scrollY};
                })())'''))
                assert geometry['top'] >= geometry['toolbarBottom'] - 1, geometry
                assert geometry['bottom'] <= geometry['height'] + 1, geometry
                assert geometry['bottom'] > geometry['top'] + 40, geometry
                assert abs(geometry['outerScroll']) < 1, geometry
                assert owner.formatted.view is web
                assert 'saved 😀' in owner.document.text
                report['rotation'].append(dict(orientation=orientation,geometry=geometry,pose=pose_snapshot(self)))
            await owner.choose_mode('Source')
            assert owner.editor_area.children == [owner.editor]
            await owner.choose_mode('Formatted')
            await wait_for_text(web, 'saved 😀')
            long_note = self.store.create('Position.md', ('A paragraph for continued writing.\n\n' * 200).encode())
            self.open_document(long_note.id)
            self.show_documents(edit=True)
            long_owner = self.editor_view
            long_web = long_owner.formatted.view
            await wait_for_text(long_web, 'A paragraph for continued writing.')
            await long_web.evaluate_javascript("document.getElementById('document').scrollTop=240")
            await long_owner.choose_mode('Source')
            long_owner.editor.value += '\nChanged in Source\n'
            await long_owner.choose_mode('Formatted')
            await wait_for_text(long_web, 'Changed in Source')
            await asyncio.sleep(.3)
            scroll = float(await long_web.evaluate_javascript("document.getElementById('document').scrollTop"))
            assert scroll >= 200, scroll
            report['mode_scroll_retained'] = True
            self.close_session(long_owner.session.id, choice='discard')

            from mobile.obsidian import open_vault
            root = self.storage_root / 'library'
            (root / '.obsidian').mkdir(parents=True)
            (root / 'Writing.md').write_text(TEXT)
            (root / 'Next.md').write_text('# Another note\n')
            library = await open_vault(self, LocalFiles(root), '', 'files', title='My notes')
            await library.open_note('Writing.md')
            await wait_for_text(library.web, 'A calmer place to write')
            await asyncio.sleep(.5)
            await capture_window(self, output / 'library.png')
            assert await library.open_editor()
            editor = self.private_sessions.active
            workflow = editor._provider_markdown
            assert editor.crypt_content.children == [workflow.formatted.view]
            await wait_for_text(workflow.formatted.view, 'A calmer place to write')
            await workflow.formatted.view.evaluate_javascript("document.querySelector('h1').append(' — local')")
            await editor.save_crypt()
            assert (root / 'Writing.md').read_text().startswith('# A calmer place to write — local')
            await dict(workflow.actions_menu.actions)['Return to Notes Library']()
            await wait_for_text(library.web, 'A calmer place to write — local')
            assert library.path == 'Writing.md'
            report['library'] = dict(formatted_entry=True, saved_return=True)

            # Exercise remote policy through an adapter exposing physical files:
            # remote status must win over any locally available write methods.
            remote = LocalFiles(root)
            remote.remote_storage = True
            remote_library = await open_vault(self, remote, '', 'files', title='Cloud notes')
            await remote_library.open_note('Writing.md')
            assert not remote_library.edit.enabled
            assert not await remote_library.open_editor()
            assert not remote_library.new_note()
            assert 'New note…' not in dict(remote_library.reader_actions.actions)
            reader = LocalTextCopies(remote).open('Writing.md')
            assert reader.read_only
            assert await self.open_crypt(copies=LocalTextCopies(remote), key='Writing.md', edit=True)
            remote_owner = self.private_sessions.active
            assert remote_owner.crypt_content.children == [remote_owner._provider_markdown.preview]
            assert remote_owner.crypt_edit_mode is None
            report['remote'] = dict(read_only=True)

            from io import BytesIO
            from features.rclone.localcrypt.mobile.resources import encrypted_storage
            self.show_cloud(present=False)
            restore = getattr(self, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
            client = self.cloud_client
            client.request('import', package=fixture['package'], password='synthetic-resume-password',
                           package_name='Synthetic.zip', session_only=True)
            await asyncio.sleep(.2)  # Credential observers retire the old connection's views.
            crypt = encrypted_storage(self.private_root, client, 'Secret')
            crypt.mkdir('.obsidian')
            crypt.create_file('Private.md', BytesIO(TEXT.encode()))
            private_library = await open_vault(self, crypt, '', 'files', title='Private notes')
            assert await private_library.open_note('Private.md'), private_library.notice.text
            assert await private_library.open_editor()
            private_editor = self.private_sessions.active
            private_workflow = private_editor._provider_markdown
            assert private_workflow.private
            await wait_for_text(private_workflow.formatted.view, 'A calmer place to write')
            await private_workflow.formatted.view.evaluate_javascript("document.querySelector('h1').append(' — encrypted')")
            await private_editor.save_crypt()
            with crypt.open('Private.md') as stream:
                assert stream.read().decode().startswith('# A calmer place to write — encrypted')
            await dict(private_workflow.actions_menu.actions)['Return to Notes Library']()
            await wait_for_text(private_library.web, 'A calmer place to write — encrypted')
            client.lock()
            self.private_sessions.revoke_stale()
            await asyncio.sleep(.2)
            assert not private_library.valid()
            assert private_library.cancelled.is_set()
            report['localcrypt'] = dict(formatted_entry=True, saved_return=True, lock_revoked=True)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
            await capture_window(self, output / 'failure.png')
        (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    return MarkdownReworkProbe('Markdown QA', 'io.github.ispaure.logisticsmarkdownqa')
