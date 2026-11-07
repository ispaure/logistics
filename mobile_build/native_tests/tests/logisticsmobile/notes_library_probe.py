"""Native in-place Notes Library, Markdown and notebook acceptance."""
import asyncio
import json
from pathlib import Path
import traceback
import toga
from threading import Event
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile
from mobile.obsidian import open_vault
from features.notes_library.notes import NotesLibrary
from . import start_native_check
from .fixtures import capture_window
from .rotation_checks import rotate

TEST_STAGE = TestStage.REGRESSION


class NotesLibraryProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('notes-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def wait_js(self, web, expression):
        for _ in range(150):
            try:
                if await web.evaluate_javascript(expression):
                    return
            except Exception:
                pass
            await asyncio.sleep(.1)
        raise AssertionError('Editor did not become ready: ' + expression)

    async def check_library_tools(self, owner, root, evidence):
        editor = owner.embedded
        with patch.object(editor, 'flush', new=AsyncMock(side_effect=ValueError('Input not ready'))):
            await editor.show_find()
            assert not hasattr(editor, 'finder')
            assert owner.notice.text == 'Input not ready'
        await editor.show_find()
        editor.source.value += '\n🐢 Native parity check.\n'
        editor.changed(editor.source.value)
        editor.finder.query.value = 'Native parity'
        editor.finder.changed()
        editor.finder.next()
        start, end = editor.finder.span
        expected = tuple(len(editor.text[:offset].encode('utf-16-le')) // 2 for offset in (start, end))
        native = editor.source._impl.native
        if self._is_apple():
            assert (int(native.selectedRange.location), int(native.selectedRange.location + native.selectedRange.length)) == expected
        else:
            assert (native.getSelectionStart(), native.getSelectionEnd()) == expected
        await asyncio.sleep(.3)
        await capture_window(self, evidence / 'notes-find-replace.png')
        editor.finder.replacement.value = 'Native tools verified'
        editor.finder.replace_all()
        assert 'Native tools verified' in editor.text
        editor.finder.toggle()
        with patch.object(owner.view.window, 'dialog', new=AsyncMock(return_value='0')):
            await editor.show_contents()
        await editor.edit_yaml()
        await asyncio.sleep(.3)
        await capture_window(self, evidence / 'notes-yaml.png')
        rows = editor.tool_views[-1]
        rows.children[0].value = 'parity: true\n'
        await rows.children[2].on_press()
        assert editor.text.startswith('---\nparity: true\n---\n')
        assert await editor.save()
        assert 'Native tools verified' in (root / 'Home.md').read_text()
        await editor.show_properties()
        rows = editor.tool_views[-1]
        await rows.children[0].on_press()
        rows = editor.tool_views[-1]
        assert rows.children[0].readonly
        assert rows.children[1].value == 'Checkbox'
        rows.children[2].value = 'false'
        await capture_window(self, evidence / 'notes-property.png')
        await rows.children[4].on_press()
        assert 'parity: false' in editor.text
        original = editor.text
        editor.property_form(original)
        rows = editor.tool_views[-1]
        rows.children[0].value = 'parity'
        rows.children[2].value = 'Keep original'
        await rows.children[4].on_press()
        assert 'already exists' in rows.children[3].text
        assert editor.text == original
        owner.present()
        assert await editor.save()
        await editor.choose_mode(True)
        await self.wait_js(editor.formatted.view, '!!window.markdownSnapshot && '
            'document.documentElement.dataset.editorBridge===' + json.dumps(editor.formatted.bridge))
        web = editor.formatted.view
        async def pending_text(text):
            # Leave the DOM ahead of Python, as with a coalesced input bridge.
            return await web.evaluate_javascript('(()=>{const s=Array.from(document.querySelectorAll("section"))'
                '.filter(s=>s.isContentEditable).at(-1);s.innerHTML="<p>"+' + json.dumps(text) + '+"</p>";return true})()')
        await pending_text('Before native save')
        entered, release = Event(), Event()
        original_save = editor.resource.save
        def slow_save(data, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError('Native save probe did not release the writer')
            return original_save(data, **kwargs)
        with patch.object(editor.resource, 'save', side_effect=slow_save):
            pending = asyncio.create_task(editor.save())
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                await pending_text('Typed during native save')
            finally:
                release.set()
            assert not await pending
        assert editor.dirty
        assert 'Typed during native save' in editor.text
        assert 'Before native save' in (root / 'Home.md').read_text()
        assert 'Typed during native save' not in (root / 'Home.md').read_text()
        assert await editor.save()
        assert 'Typed during native save' in (root / 'Home.md').read_text()

    def _is_apple(self):
        return type(self.main_window._impl).__module__.startswith('toga_iOS.')

    async def check_file_previews(self, owner, root, evidence):
        from io import BytesIO
        from pypdf import PdfWriter
        from .fixtures import png_page
        (root / 'Image.png').write_bytes(png_page())
        (root / 'Unknown.binary').write_bytes(b'\x00binary')
        output = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.add_blank_page(width=300, height=200)
        writer.write(output)
        (root / 'Document.pdf').write_bytes(output.getvalue())
        (root / 'clip.mp4').write_bytes(b'non-playing stream fixture')
        (root / 'Media.md').write_text('![[clip.mp4]]')
        assert await owner.open_note('Media.md')
        await self.wait_js(owner.web, '!!document.querySelector("video")')
        media = owner.library.image_source('Media.md')
        assert not media.videos
        assert await asyncio.to_thread(owner.library.open_embedded_video, 'Media.md', 'clip.mp4')
        transports = [transport for _, transport in media.videos.values()]
        assert transports
        sessions = set(self.workspace.sessions)
        for name in ('Image.png', 'Document.pdf', 'Unknown.binary'):
            assert await owner.open_note(name), owner.notice.text
            assert set(self.workspace.sessions) == sessions
            assert owner.path == name and owner.embedded.kind == 'file'
            assert all(transport.closed.is_set() for transport in transports)
            preview = owner.embedded
            if name != 'Unknown.binary':
                await self.wait_js(preview.web, '!!document.querySelector("img") && document.querySelector("img").complete && document.querySelector("img").naturalWidth > 0')
            if name == 'Document.pdf':
                assert preview.preview.count == 2
                await preview.turn(1)
                assert preview.index == 1
                await self.wait_js(preview.web, 'document.querySelector("img").complete && document.querySelector("img").naturalWidth > 0')
            await capture_window(self, evidence / ('notes-file-' + name + '.png'))
        assert await owner.open_note('Home.md')
        assert preview.closed and not preview.preview.path

    async def check_breadcrumbs(self, owner, root, evidence):
        from .fixtures import png_page
        folder = root / 'Technology/Accessories/Devices'
        folder.mkdir(parents=True)
        (root / 'Technology/Technology.md').write_text('# Technology')
        (root / 'Technology/Accessories/Accessories.md').write_text('# Accessories')
        (folder / 'Current Page.md').write_text('# Current Page')
        (folder / 'Image.png').write_bytes(png_page())
        (folder / 'Data.json').write_text('{}')
        (folder / 'Unknown.binary').write_bytes(b'\x00')
        for name in ('Current Page.md', 'Image.png', 'Data.json', 'Unknown.binary'):
            assert await owner.open_note('Technology/Accessories/Devices/' + name), owner.notice.text
            await asyncio.sleep(.3)
            links = [child.children[1] for child in owner.breadcrumbs.children if isinstance(child, toga.Box)]
            assert links, [getattr(child, 'text', '') for child in owner.breadcrumbs.children]
            separators = [child for child in owner.breadcrumbs.children
                          if isinstance(child, toga.ImageView) and not hasattr(child, 'browser_entry_kind')]
            assert len(separators) == len(links)
            for button in links:
                native = button._impl.native
                if self._impl.__class__.__module__.startswith('toga_iOS.'):
                    title = native.attributedTitleForState(0)
                    if button.breadcrumb_path:
                        assert title is not None and str(title.string) == button.text
                    else:
                        assert title is None
                else:
                    assert bool(native.getPaintFlags() & 8) == bool(button.breadcrumb_path)
            assert links[-1].text == 'Devices'
            await capture_window(self, evidence / ('notes-breadcrumb-' + name + '.png'))
        landing = next((button for button in links if button.breadcrumb_path), None)
        await (landing or links[-1]).on_press()
        if landing is not None:
            assert owner.path.endswith('/Technology.md') or owner.path.endswith('/Accessories.md')
        else:
            assert owner.sidebar.side == 'files' or owner.sidebar.expanded
            owner.sidebar.show_detail()
        assert await owner.open_note('Home.md')

    async def probe(self):
        report = dict(success=False, samples=[])
        evidence = Path(self.paths.cache) / 'viewer-layout'
        evidence.mkdir(exist_ok=True)
        owner = None
        try:
            root = Path(self.paths.cache) / ('library-' + uuid4().hex)
            (root / '.obsidian').mkdir(parents=True)
            (root / 'Projects').mkdir()
            (root / 'Home.md').write_text('# [[Tech]]\n\nA note in the library.\n')
            (root / 'Projects/Tech.md').write_text('# Technology\n')
            provider = LocalFiles(root)
            NotesLibrary(provider).create('Sketch', extension='rmdoc')
            owner = await open_vault(self, provider, '', 'files')
            await asyncio.sleep(.5)
            assert owner.path is None and owner.welcome in owner.article.children
            assert not owner.sidebar.sidebar_open
            assert owner.secondary.parent is None
            await capture_window(self, evidence / 'notes-welcome.png')
            owner.sidebar.show_sidebar()
            await asyncio.sleep(.3)
            assert owner.secondary.parent is None
            await capture_window(self, evidence / 'notes-files.png')
            assert await owner.open_note('Home.md')
            await asyncio.sleep(.4)
            expected_parent = owner.article if owner.host.apple or owner.sidebar.expanded else owner.view
            assert owner.secondary.parent is expected_parent
            await capture_window(self, evidence / 'notes-reading.png')
            session_ids = set(self.workspace.sessions)
            await self.check_file_previews(owner, root, evidence)
            report['embedded_file_previews'] = True
            await self.check_breadcrumbs(owner, root, evidence)
            report['breadcrumbs_all_files'] = True
            assert await owner.open_editor()
            editor = owner.embedded
            web = editor.formatted.view
            await self.wait_js(web, '!!window.markdownSnapshot')
            assert set(self.workspace.sessions) == session_ids
            data = json.loads(await web.evaluate_javascript("JSON.stringify({editable:document.querySelector('section').contentEditable,sourceOnly:!!document.querySelector('section').dataset.sourceOnly})"))
            assert data == dict(editable='true', sourceOnly=False), data
            await capture_window(self, evidence / 'notes-editing.png')
            # Use the actual formatted input protocol and preserve the wiki heading.
            await web.evaluate_javascript("(()=>{const s=document.querySelector('section');s.innerHTML='<p><span data-live-source>\u0023 [[Tech Updated]]</span></p>';s.dispatchEvent(new InputEvent('input',{bubbles:true}));return true})()")
            await editor.flush()
            assert '# [[Tech Updated]]' in editor.text, editor.text
            assert await editor.save()
            assert '# [[Tech Updated]]' in (root / 'Home.md').read_text()
            owner.sidebar.show_sidebar()
            await asyncio.sleep(.3)
            assert owner.embedded is editor
            await capture_window(self, evidence / 'notes-editing-files.png')
            owner.sidebar.show_detail()
            await owner.show_links()
            await asyncio.sleep(.3)
            assert owner.embedded is editor
            await capture_window(self, evidence / 'notes-editing-links.png')
            owner.sidebar.show_detail()
            # Focus the actual WebKit contenteditable, then measure toolbar order.
            if type(web._impl).__module__.startswith('toga_android.'):
                web._impl.native.requestFocus()
            await web.evaluate_javascript("(()=>{const s=document.querySelector('section');s.blur();s.focus();const r=document.createRange();r.selectNodeContents(s);r.collapse(false);getSelection().removeAllRanges();getSelection().addRange(r);return true})()")
            await asyncio.sleep(.5)
            metrics = json.loads(await web.evaluate_javascript("JSON.stringify((()=>{const r=s=>{const b=document.querySelector(s).getBoundingClientRect();return {top:b.top,bottom:b.bottom,height:b.height}};return {document:r('#document'),toolbar:r('nav'),width:innerWidth,body:document.body.scrollWidth}})())"))
            assert metrics['toolbar']['top'] >= metrics['document']['bottom'] - 1, metrics
            assert metrics['toolbar']['height'] >= 44, metrics
            assert metrics['body'] <= metrics['width'] + 1, metrics
            report['samples'].append(metrics)
            await capture_window(self, evidence / 'notes-keyboard-tools.png')
            await web.evaluate_javascript('document.activeElement.blur();true')
            await rotate(self, 'landscape-left')
            await asyncio.sleep(.4)
            await capture_window(self, evidence / 'notes-landscape.png')
            if (Path(self.paths.cache) / 'notes-keyboard').exists():
                laptop = (Path(self.paths.cache) / 'notes-laptop-keyboard').exists()
                from commonUtils.ui.native.keyboard import native_value
                if not laptop:
                    await rotate(self, 'portrait')
                before_keyboard = owner.host.presentation.fold_division(web)
                if laptop and (before_keyboard is None or before_keyboard.vertical):
                    await rotate(self, 'portrait')
                    before_keyboard = owner.host.presentation.fold_division(web)
                from .rotation_checks import pose_snapshot
                from mobile.fold_layout import reserved_divisions
                from dataclasses import asdict
                diagnostic = dict(pose=pose_snapshot(self), backend=type(web._impl).__module__,
                    web_regions=[asdict(r) for r in reserved_divisions(web, include_inactive=True)],
                    web_bounds=dict(width=float(web._impl.native.bounds.size.width), height=float(web._impl.native.bounds.size.height)))
                report['laptop_geometry'] = diagnostic
                if laptop:
                    assert before_keyboard is not None and not before_keyboard.vertical, diagnostic
                await web.evaluate_javascript("document.querySelector('section').focus();true")
                for child in native_value(native_value(web._impl.native.scrollView).subviews):
                    if 'WKContentView' in str(child.objc_class):
                        child.becomeFirstResponder()
                await asyncio.sleep(1)
                (evidence / 'keyboard-capture-request').touch()
                for _ in range(100):
                    if (evidence / 'keyboard-capture-done').exists():
                        break
                    await asyncio.sleep(.1)
                assert (evidence / 'keyboard-capture-done').exists(), 'OS keyboard screenshot not captured'
                await asyncio.sleep(.5)
                assert self.native_host.adapter.keyboard_inset > 100, 'Duo software keyboard did not open'
                keyboard_metrics = json.loads(await web.evaluate_javascript("JSON.stringify((()=>{const r=s=>{const b=document.querySelector(s).getBoundingClientRect();return {top:b.top,bottom:b.bottom,height:b.height}};return {document:r('#document'),toolbar:r('nav'),height:innerHeight,viewport_height:visualViewport?.height,viewport_top:visualViewport?.offsetTop,editing:document.body.classList.contains('editing')}})())"))
                keyboard_metrics['fold_y'] = before_keyboard.y if before_keyboard is not None else None
                keyboard_metrics['keyboard_inset'] = self.native_host.adapter.keyboard_inset
                native = web._impl.native
                window = self.main_window._impl.native
                keyboard = window.convertRect(self.native_host.adapter.keyboard_frame, fromCoordinateSpace=window.screen.coordinateSpace)
                local_keyboard = native.convertRect(keyboard, fromView=window)
                keyboard_metrics['keyboard_top'] = float(local_keyboard.origin.y)
                report['laptop_keyboard'] = keyboard_metrics
                assert keyboard_metrics['toolbar']['bottom'] <= keyboard_metrics['keyboard_top'] + 1, keyboard_metrics
                assert keyboard_metrics['editing'], keyboard_metrics
                await capture_window(self, evidence / 'notes-laptop-keyboard.png')
                if before_keyboard is not None and not before_keyboard.vertical:
                    lower_room = keyboard_metrics['keyboard_top'] - before_keyboard.y - before_keyboard.height
                    if lower_room >= keyboard_metrics['toolbar']['height']:
                        assert keyboard_metrics['toolbar']['top'] >= before_keyboard.y + before_keyboard.height - 1, keyboard_metrics
                    else:
                        assert keyboard_metrics['document']['height'] >= 44, keyboard_metrics
                        keyboard_metrics['lower_half_occupied_by_keyboard'] = True
                    assert keyboard_metrics['document']['bottom'] <= before_keyboard.y + 1, keyboard_metrics
                assert keyboard_metrics['toolbar']['bottom'] <= keyboard_metrics['height'] + 1, keyboard_metrics
                report['laptop_keyboard'] = keyboard_metrics
                await capture_window(self, evidence / 'notes-laptop-keyboard.png')
                await web.evaluate_javascript('document.activeElement.blur();true')
                web._impl.native.endEditing(True)
            await rotate(self, 'portrait')
            await self.check_library_tools(owner, root, evidence)
            # Slow content search cannot monopolize the event loop or selector.
            for index in range(120):
                (root / 'Projects' / f'Match {index:03}.md').write_text('search needle')
            owner.search_mode.value = 'Search within Documents'
            owner.search.value = 'needle'
            first = owner.search_task
            await asyncio.sleep(.21)
            owner.search_mode.value = 'Search in File Names'
            await owner.search_task
            assert not owner.search_rows
            if first is not None:
                await asyncio.gather(first, return_exceptions=True)
            owner.search.value = ''
            assert await owner.open_note('Sketch.rmdoc')
            canvas = owner.embedded
            await self.wait_js(canvas.panel.web, '!!window.notebookIdle && window.notebookIdle()')
            assert set(self.workspace.sessions) == session_ids
            await capture_window(self, evidence / 'notes-remarkable.png')
            from features.notebooks.notebook import Notebook
            sketch = root / 'Sketch.rmdoc'
            await canvas.panel.perform({'op': 'add-page'})
            assert canvas.dirty
            with patch.object(canvas.panel.document.resource, 'save', side_effect=OSError('Test write failure')):
                assert not await owner.open_note('Home.md')
            assert owner.embedded is canvas and canvas.dirty
            assert len(Notebook.read(sketch.read_bytes()).pages) == 1
            assert await owner.open_note('Home.md')
            assert len(Notebook.read(sketch.read_bytes()).pages) == 2
            with patch.object(self.main_window, 'dialog', new=AsyncMock(return_value='rmdoc')):
                await owner.new_note()
            await capture_window(self, evidence / 'notes-new-name.png')
            await owner.choose_location('Created.rmdoc', 'rmdoc', 'Projects')
            await capture_window(self, evidence / 'notes-new-location.png')
            report.update(success=True, in_place=True, wiki_editing=True, drawings_saved=True,
                          search_cancellable=True, native_save_race=True)
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            if owner is not None:
                owner.dispose()
            (Path(self.paths.cache) / 'notes-library-result.json').write_text(json.dumps(report, indent=2))


def main():
    return NotesLibraryProbe('Notes Library QA', 'io.github.ispaure.logisticsnotebookqa')
