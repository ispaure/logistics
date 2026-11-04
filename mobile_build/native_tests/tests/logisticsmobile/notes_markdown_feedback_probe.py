"""Native acceptance for Markdown reuse, preparation feedback and library moves."""
import asyncio
from io import BytesIO
import json
from pathlib import Path
from threading import Event, Timer
from unittest.mock import patch

import toga
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from features.rclone.localcrypt.mobile.resources import CryptFiles
from mobile.obsidian import open_vault
from .document_workspace_probe import DocumentWorkspaceProbe
from .fixtures import capture_window, png_page

TEST_STAGE = TestStage.EXTENDED


class NotesMarkdownFeedbackProbe(DocumentWorkspaceProbe):
    result_name = 'notes-markdown-feedback-result.json'

    def record_stage(self, stage):
        print('MARKDOWN_NATIVE_STAGE=' + stage, flush=True)
        (Path(self.paths.cache) / 'notes-markdown-progress.json').write_text(json.dumps(dict(stage=stage)))

    def startup(self):
        import faulthandler
        from . import enable_native_fault_log
        self.fault_log = enable_native_fault_log(self.paths.cache)
        faulthandler.dump_traceback_later(25, repeat=True, file=self.fault_log)
        self.record_stage('startup')
        import logging
        self.startup_log = logging.FileHandler(Path(self.paths.cache) / 'notes-markdown-startup.log')
        self.startup_logger = logging.getLogger('mobile.startup')
        self.startup_logger.addHandler(self.startup_log)
        self.startup_logger.setLevel(logging.DEBUG)
        super().startup()
        self.record_stage('startup_returned')
        cache, loop = Path(self.paths.cache), self.loop
        self.diagnostics_stop = Event()
        def observe():
            if self.diagnostics_stop.is_set():
                return
            import traceback
            snapshots = []
            for task in asyncio.all_tasks(loop):
                snapshots.append(dict(task=repr(task), stack=[traceback.format_stack(frame)
                    for frame in task.get_stack()]))
            (cache / 'notes-markdown-tasks.json').write_text(json.dumps(snapshots, indent=2))
            timer = Timer(10, observe)
            timer.daemon = True
            timer.start()
        timer = Timer(10, observe)
        timer.daemon = True
        timer.start()
        # Check startup explicitly too: deferred on_running itself can be the
        # stalled boundary. start_once keeps the eventual hook from duplicating it.
        from . import start_native_check
        self.loop.call_later(.1, lambda: start_native_check(self, self.check))

    def on_running(self):
        self.record_stage('on_running')
        super().on_running()

    async def check(self, app):
        self.record_stage('check_entered')
        try:
            await super().check(app)
        finally:
            import faulthandler
            faulthandler.cancel_dump_traceback_later()
            self.diagnostics_stop.set()
            self.startup_logger.removeHandler(self.startup_log)
            self.startup_log.close()

    async def until(self, predicate, message):
        for _ in range(200):
            if predicate():
                return
            await asyncio.sleep(.05)
        raise AssertionError(message)

    async def web_ready(self, web, expression):
        for _ in range(200):
            if await web.evaluate_javascript(expression):
                return
            await asyncio.sleep(.05)
        raise AssertionError('WebView did not publish: ' + expression)

    def click(self, button):
        native = button._impl.native
        if type(button._impl).__module__.startswith('toga_iOS.'):
            native.sendActionsForControlEvents(1 << 6)
        else:
            assert native.performClick(), button.text

    def button(self, view, text):
        if isinstance(view, toga.Button) and view.text == text:
            return view
        for child in getattr(view, 'children', ()):
            found = self.button(child, text)
            if found is not None:
                return found
        content = getattr(view, 'content', None)
        return self.button(content, text) if content is not None else None

    async def screenshot(self, name):
        await asyncio.sleep(.2)
        await capture_window(self, self.evidence / (name + '.png'))

    async def run_checks(self, app, report):
        self.record_stage('checks_started')
        self.evidence = Path(self.paths.cache) / 'viewer-layout'
        self.evidence.mkdir(exist_ok=True)
        fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
        app.cloud_client.request('import', package=fixture['package'],
            password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
        for private in (False, True):
            root = app.private_root / ('MarkdownCrypt' if private else 'MarkdownLocal')
            root.mkdir(exist_ok=True)
            provider = CryptFiles(root, app.cloud_client, 'Secret') if private else LocalFiles(root)
            await asyncio.to_thread(self.seed, provider)
            owner = await open_vault(app, provider, 'Library', 'documents')
            label = 'localcrypt' if private else 'local'
            try:
                await self.library_checks(owner, report, label)
            finally:
                owner.dispose()
        await self.regular_checks(app, report)

    def seed(self, provider):
        provider.mkdir('Library')
        provider.mkdir('Library/Destination')
        provider.mkdir('Library/Folder')
        provider.mkdir('Library/Folder/Child')
        for name, data in (
                ('Home.md', b'# Cache fixture\n\n![Old](old.png)\n\n[[Target]]'),
                ('Target.md', b'# Target'), ('Folder/Child/Keep.md', b'# Keep'),
                ('old.png', png_page()), ('new.png', png_page())):
            provider.create_file('Library/' + name, BytesIO(data))

    async def library_checks(self, owner, report, label):
        self.record_stage(label + '_library_open')
        opened = []
        original = owner.provider.open
        def read(path, *args, **kwargs):
            if str(path).endswith('.png'):
                opened.append(str(path))
            return original(path, *args, **kwargs)
        with patch.object(owner.provider, 'open', side_effect=read):
            assert await owner.open_note('Library/Home.md'), owner.notice.text
            await self.web_ready(owner.web, '!!document.querySelector("img") && document.querySelector("img").complete')
            assert opened == ['Library/old.png'], opened
            self.record_stage(label + '_library_toggle')
            for _ in range(2):
                self.click(owner.edit)
                await self.until(lambda: owner.editing, 'Pencil did not open library editor')
                await self.web_ready(owner.embedded.formatted.view, '!!window.markdownSnapshot')
                self.click(owner.edit)
                await self.until(lambda: not owner.editing, 'Read toggle did not restore reader')
            assert opened == ['Library/old.png'], opened
            report['cases'].append('3_library_media_reused_' + label)
            from features.notes_library.link_policy import resolve_link
            with patch('features.notes_library.link_policy.resolve_link', wraps=resolve_link) as resolve:
                assert owner.library.link('Library/Home.md', 'Target')[0] == 'Library/Target.md'
                assert owner.library.link('Library/Home.md', 'Target')[0] == 'Library/Target.md'
                report[label + '_link_resolver_calls'] = resolve.call_count
                # Indexed encrypted providers may own their own live resolution.
                if not callable(getattr(owner.provider, 'find_note_paths', None)):
                    assert resolve.call_count <= 1, resolve.call_count
            self.record_stage(label + '_library_edit_references')
            assert await owner.open_editor()
            await owner.embedded.choose_mode(False)
            owner.embedded.source.value = '# Changed\n\n![New](new.png)\n\n[[Missing]]'
            assert await owner.embedded.save()
            assert await owner.open_editor()
            await self.web_ready(owner.web, '!!document.querySelector("img") && document.querySelector("img").alt === "New"')
            assert opened == ['Library/old.png', 'Library/new.png'], opened
            assert await owner.open_editor()
            await owner.embedded.choose_mode(False)
            owner.embedded.source.value = '# References removed'
            assert await owner.embedded.save()
            assert await owner.open_editor()
            await self.web_ready(owner.web, 'document.body.textContent.includes("References removed") && !document.querySelector("img")')
            assert opened == ['Library/old.png', 'Library/new.png'], opened
            report['cases'].append('3_edited_and_deleted_references_' + label)
        self.record_stage(label + '_library_cancel')
        await self.cancel_preparation(owner, label)
        report['cases'].append('4_library_prepare_cancel_' + label)
        self.record_stage(label + '_library_rename_move')
        owner.selected_path = 'Library/Home.md'
        owner.manage_entry(move=True)
        form = owner.file_action_view.content
        name = next(child for child in form.children if isinstance(child, toga.TextInput))
        assert name.value == 'Home.md'
        name.value = 'Renamed.md'
        self.click(self.button(form, 'Rename'))
        await self.until(lambda: owner.path == 'Library/Renamed.md', 'Rename did not publish')
        picker = await owner.move_picker(owner.path)
        browser = picker._folder_browser
        assert all(row.entry.container for row in browser.native_list.data)
        await self.screenshot(label + '-move-root')
        index = next(index for index, row in enumerate(browser.native_list.data) if row.title == 'Destination')
        native = browser.native_list._impl.native
        if type(self.main_window._impl).__module__.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            path = ObjCClass('NSIndexPath').indexPathForRow(index, inSection=0)
            native.selectRowAtIndexPath(path, animated=False, scrollPosition=0)
            browser.native_list._impl.native_controller.tableView_didSelectRowAtIndexPath_(native, path)
        else:
            native.performItemClick(native.getChildAt(index), index, index)
        await self.until(lambda: browser.search_directory == 'Destination', 'Native folder tap did not browse')
        await self.screenshot(label + '-move-destination')
        self.click(self.button(picker, 'Move here'))
        await self.until(lambda: owner.path == 'Library/Destination/Renamed.md', 'Move did not publish')
        assert owner.library.read(owner.path).endswith(b'References removed')
        picker = await owner.move_picker('Library/Folder')
        assert all(row.entry.label != 'Folder' for row in picker._folder_browser.native_list.data)
        self.click(self.button(picker, 'Cancel'))
        await self.until(lambda: owner.file_action_view is None, 'Move Cancel did not return')
        assert owner.library.entry('Library/Folder/Child/Keep.md')
        report['cases'].append('5_native_rename_browse_move_cancel_' + label)

    async def cancel_preparation(self, owner, label):
        from features.notes_library.mobile.library_document import prepare_editor
        entered, release = Event(), Event()
        retained = list(owner.article.children)
        def slow(*args, **kwargs):
            entered.set()
            assert release.wait(15), 'Preparation gate not released'
            return prepare_editor(*args, **kwargs)
        with patch('features.notes_library.mobile.library_document.prepare_editor', side_effect=slow):
            self.click(owner.edit)
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                assert owner.page_loading.status.text == 'Preparing for editing…'
                await self.screenshot(label + '-preparing')
                self.click(self.button(owner.page_loading.panel, 'Cancel'))
                await self.until(lambda: not owner.page_loading.active, 'Preparation Cancel did not respond')
            finally:
                release.set()
            await asyncio.sleep(.4)
        assert not owner.editing and owner.embedded is None
        assert list(owner.article.children) == retained

    async def regular_checks(self, app, report):
        self.record_stage('regular_editor')
        from features.text_editor.resources import LocalTextCopies
        from services.documents.authoring.markdown_editor import prepare_editor
        root = app.private_root / 'RegularMarkdown'
        root.mkdir(exist_ok=True)
        (root / 'Home.md').write_text('# Regular\n\n![Old](old.png)')
        (root / 'old.png').write_bytes(png_page())
        assert await app.open_crypt(copies=LocalTextCopies(LocalFiles(root)), key='Home.md')
        session = app.private_sessions.active
        workflow = session._provider_markdown
        entered, release = Event(), Event()
        def slow(*args, **kwargs):
            entered.set()
            assert release.wait(15), 'Regular preparation gate not released'
            return prepare_editor(*args, **kwargs)
        with patch('services.documents.authoring.provider_markdown.prepare_editor', side_effect=slow):
            self.click(workflow.preview_button)
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                candidate = workflow.preparing_formatted
                await self.screenshot('regular-preparing')
                self.click(self.button(workflow.content, 'Cancel'))
                await self.until(lambda: workflow.preparing_formatted is None, 'Regular Cancel did not respond')
                assert candidate.closed
            finally:
                release.set()
            await asyncio.sleep(.4)
        assert workflow.formatted is None and workflow.preview in workflow.content.children
        assert session.crypt_text.value == '# Regular\n\n![Old](old.png)'
        media = session.crypt_reader._markdown_media
        with patch.object(media.provider, 'open', wraps=media.provider.open) as opened:
            self.click(workflow.preview_button)
            await self.until(lambda: workflow.formatted is not None, 'Regular editor did not open')
            await self.web_ready(workflow.formatted.view, '!!window.markdownSnapshot && !!document.querySelector("img")')
            self.click(workflow.preview_button)
            await self.until(lambda: workflow.preview in workflow.content.children, 'Regular reader did not return')
            await self.web_ready(workflow.preview, '!!document.querySelector("img")')
            assert opened.call_count == 0, opened.call_args_list
        report['cases'].extend(['4_regular_prepare_cancel_and_retry', '3_regular_media_reused'])
        app.private_sessions.close(session.session.id, discard=True)


def main():
    return NotesMarkdownFeedbackProbe('Markdown Feedback QA', 'io.github.ispaure.logisticsnotebookqa')
