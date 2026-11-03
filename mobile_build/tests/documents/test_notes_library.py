"""Location actions, bounded remote access and Notes Library document ownership."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import base64
import json
import os
import unittest
import shutil
from unittest.mock import patch
import mobile_build.tests.documents.test_obsidian as test_obsidian
from commonUtils.runtime.resources.local import LocalFiles
from mobile.notes_actions import RemoteNotes, offer_notes
from features.notes_library.notes import NotesLibrary
import toga
from toga.style import Pack


class Client:
    generation = 1
    def __init__(self, root):
        self.files, self.calls = LocalFiles(root), []
    def cancel(self):pass
    def connection_identity(self, remote):return 'identity'
    def entries(self, remote, path=''):
        self.calls.append(('list', path))
        return self.files.list(path)
    def request(self, action, **kw):
        self.calls.append((action, kw.get('path')))
        row = self.files.entry(kw['path'])
        revision = json.dumps(row['revision'])
        if action == 'remote_stat':return dict(size=row['size'], revision=revision)
        if action == 'remote_range':
            if kw['expected'] != revision:raise ValueError('Changed')
            data = (self.files.root / kw['path']).read_bytes()
            return dict(data=base64.b64encode(data[kw['offset']:kw['offset'] + kw['count']]).decode())
        raise AssertionError(action)


class NotesLibraryTests(unittest.TestCase):
    setUp = test_obsidian.ObsidianTests.setUp
    tearDown = test_obsidian.ObsidianTests.tearDown
    run_async = test_obsidian.ObsidianTests.run_async

    def test_retained_native_title_stays_above_commands_and_breadcrumbs(self):
        from mobile.obsidian import open_vault
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            # Apple promotes this toolbar into native navigation. Its retained
            # side-title row must stay first as an empty library gains a note.
            owner.toolbar.parent.remove(owner.toolbar)
            header = owner.view._document_title_header = toga.Box(style=Pack(height=37))
            owner.view.insert(0, header)
            owner.refresh_chrome()
            self.assertIs(owner.view.children[0], header)
            self.assertTrue(await owner.open_note('Vault/Home.md'))
            owner.refresh_chrome()
            self.assertIs(owner.view.children[0], header)
            self.assertLess(list(owner.view.children).index(header), list(owner.view.children).index(owner.secondary))
            self.assertLess(list(owner.view.children).index(owner.secondary), list(owner.view.children).index(owner.breadcrumbs))
            owner.sidebar.show_sidebar()
            self.assertIs(owner.view.children[0], header)
            owner.sidebar.show_detail()
            self.assertIs(owner.view.children[0], header)
            owner.dispose()
        self.run_async(exercise())

    def test_cancelled_source_preparation_retires_resource_after_worker_finishes(self):
        from threading import Event
        from mobile.obsidian import open_vault
        from features.notes_library.mobile.library_text import LibraryText
        from services.documents.storage import DocumentResource
        entered, finish = Event(), Event()
        resources = []
        original = DocumentResource.read
        (self.vault / 'draft.txt').write_text('draft')
        def read(resource, **kwargs):
            resources.append(resource)
            entered.set()
            if not finish.wait(3):
                raise ValueError('Preparation did not finish')
            return original(resource, **kwargs)
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            with patch.object(DocumentResource, 'read', read):
                task = asyncio.create_task(LibraryText.open(owner, 'Vault/draft.txt'))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    self.assertFalse(resources[0].closed)
                finally:
                    finish.set()
                for _ in range(200):
                    if resources[0].closed:
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(resources[0].closed)
            owner.dispose()
        self.run_async(exercise())

    def test_nested_encoded_image_embeds_and_failure_reasons_reach_preview_and_editor(self):
        from mobile.obsidian import open_vault
        from commonUtils.tests.formats.test_gif_headers import GIF
        from services.documents.authoring.markdown_editor import editor_blocks
        folder = self.vault / 'Archive/Katia Hair VFX Exploration'
        folder.mkdir(parents=True)
        (folder / 'photo.gif').write_bytes(GIF)
        source = r'![Photo]\(Katia%20Hair%20VFX%20Exploration/photo.gif)' + '\n\n![Missing](absent.png)\n'
        (self.vault / 'Home.md').write_text(source)
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            with patch.object(owner.web, 'set_content') as publish:
                self.assertTrue(await owner.open_note('Vault/Home.md'))
            html = publish.call_args.args[1]
            self.assertIn('<img src="data:image/gif;base64,', html)
            self.assertIn('Image unavailable: Note not found', html)
            blocks = editor_blocks(source, image_source=owner.library.image_source('Vault/Home.md'))
            self.assertIn('<img', blocks[0]['html'])
            self.assertEqual(blocks[0]['source'], source.split('\n\n')[0] + '\n')
            self.assertIn('Image unavailable:', ''.join(block['html'] for block in blocks))
            self.assertEqual(''.join(block['source'] for block in blocks), source)
            owner.dispose()
        self.run_async(exercise())

    def test_breadcrumbs_and_underlines_follow_notes_images_and_source_files(self):
        from mobile.obsidian import open_vault
        from mobile_build.tests.support.pdf import PNG
        (self.vault / 'Vault.md').write_text('# Library')
        (self.vault / 'Projects/Projects.md').write_text('# Projects')
        (self.vault / 'Projects/Plain').mkdir()
        for name, data in [('Current.md', b'# Current'), ('Image.png', PNG),
                           ('Data.json', b'{}'), ('Unknown.bin', b'\x00')]:
            (self.vault / 'Projects/Plain' / name).write_bytes(data)
        deep = self.vault.joinpath(*(['Nested'] * 30))
        deep.mkdir(parents=True)
        (deep / 'Current.md').write_text('# Deep note')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            for name in ('Current.md', 'Image.png', 'Data.json', 'Unknown.bin'):
                self.assertTrue(await owner.open_note('Vault/Projects/Plain/' + name))
                links = [child for child in owner.breadcrumbs.children if hasattr(child, 'breadcrumb_path')]
                self.assertEqual([child.breadcrumb_path for child in links],
                                 ['Vault/Vault.md', 'Vault/Projects/Projects.md'])
                self.assertTrue(all(child.notes_folder_link for child in links))
                self.assertEqual(owner.breadcrumbs.children[-1].text, name)
                self.assertTrue(any(getattr(child, 'text', '') == 'Plain' for child in owner.breadcrumbs.children))
            await links[1].on_press()
            self.assertEqual(owner.path, 'Vault/Projects/Projects.md')
            await owner.previous_note()
            self.assertEqual(owner.path, 'Vault/Projects/Plain/Unknown.bin')
            self.assertTrue(await owner.open_note(self.provider.relative(deep / 'Current.md')))
            owner.reflow(220)
            self.assertEqual(owner.breadcrumbs.children[-1].text, 'Current.md')
            owner.dispose()
            self.assertFalse(owner.breadcrumbs.children)
        self.run_async(exercise())

    def test_images_pdf_and_unknown_files_replace_article_without_leaving_library(self):
        from mobile.obsidian import open_vault
        from mobile_build.tests.support.pdf import PDF, PNG, native_pdf
        (self.vault / 'Image.png').write_bytes(PNG)
        (self.vault / 'Document.pdf').write_bytes(PDF)
        (self.vault / 'Unknown.binary').write_bytes(b'\x00binary')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            self.assertTrue(await owner.open_note('Vault/Home.md'))
            sessions = set(self.app.workspace.sessions)
            route = self.app.navigation_generation
            with patch('features.pdf.document.PDFDocument.open', native_pdf):
                for name in ('Image.png', 'Document.pdf', 'Unknown.binary'):
                    target = name if name == 'Image.png' else 'Vault/' + name
                    self.assertTrue(await owner.open_note(target, resolve_link=name == 'Image.png'), owner.notice.text)
                    self.assertEqual(set(self.app.workspace.sessions), sessions)
                    self.assertEqual(self.app.navigation_generation, route)
                    self.assertEqual(owner.path, 'Vault/' + name)
                    self.assertEqual(owner.embedded.kind, 'file')
                    self.assertIn(owner.embedded.view, owner.article.children)
                    if name == 'Document.pdf':
                        self.assertEqual(owner.embedded.preview.count, 3)
                        await owner.embedded.turn(1)
                        self.assertEqual(owner.embedded.index, 1)
                    previous = owner.embedded
                self.assertTrue(await owner.open_note('Vault/Home.md'))
                self.assertTrue(previous.closed)
                self.assertEqual(previous.preview.path, '')
            owner.dispose()
        self.run_async(exercise())

    def test_switching_to_file_preview_retires_previous_markdown_media(self):
        from mobile.obsidian import open_vault
        (self.vault / 'clip.mp4').write_bytes(b'video fixture')
        (self.vault / 'Home.md').write_text('![[clip.mp4]]')
        (self.vault / 'LICENSE').write_text('License')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            self.assertTrue(await owner.open_note('Vault/Home.md'))
            media = owner.library.image_source('Vault/Home.md')
            transports = [transport for _, transport in media.videos.values()]
            self.assertTrue(transports)
            with patch.object(owner.web, 'set_content', wraps=owner.web.set_content) as publish:
                self.assertTrue(await owner.open_note('LICENSE', resolve_link=True), owner.notice.text)
            self.assertTrue(all(transport.closed.is_set() for transport in transports))
            self.assertNotIn('<video', publish.call_args.args[1])
            self.assertEqual(owner.path, 'Vault/LICENSE')
            owner.dispose()
        self.run_async(exercise())

    def test_cancelled_page_worker_keeps_content_until_rendering_finishes(self):
        from threading import Event
        from mobile.obsidian import open_vault
        from mobile_build.tests.support.pdf import PDF, native_pdf
        (self.vault / 'Document.pdf').write_bytes(PDF)
        entered, release = Event(), Event()
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            with patch('features.pdf.document.PDFDocument.open', native_pdf):
                self.assertTrue(await owner.open_note('Vault/Document.pdf'))
                preview = owner.embedded
                original = preview.preview.page
                def render(index):
                    entered.set()
                    release.wait(5)
                    return original(index)
                with patch.object(preview.preview, 'page', side_effect=render):
                    task = asyncio.create_task(preview.turn(1))
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                        self.assertTrue(preview.busy)
                        owner.dispose()
                        self.assertEqual(preview.preview.path, 'Vault/Document.pdf')
                    finally:
                        release.set()
                    for _ in range(100):
                        if not preview.busy:
                            break
                        await asyncio.sleep(.01)
                    self.assertFalse(preview.busy)
                    self.assertEqual(preview.preview.path, '')
        self.run_async(exercise())

    def test_library_markdown_and_source_editing_work_with_text_editor_disabled(self):
        from mobile.obsidian import open_vault
        self.app.set_feature_enabled('text_editor', False, refresh=False)
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            self.assertIsNotNone(owner)
            self.assertTrue(await owner.open_note('Vault/Home.md'))
            self.assertTrue(await owner.open_editor())
            self.assertTrue(await owner.embedded.choose_mode(False))
            owner.embedded.source.value = '# Independent library editor'
            self.assertTrue(await owner.embedded.save())
            self.assertEqual((self.vault / 'Home.md').read_text(), '# Independent library editor')
            owner.dispose()
            self.app.set_feature_enabled('notes_library', False, refresh=False)
            self.assertIsNone(await open_vault(self.app, self.provider, 'Vault', 'documents'))
        self.run_async(exercise())

    def test_video_embeds_stream_in_preview_and_editor_and_close_with_library(self):
        from mobile.obsidian import open_vault
        from services.documents.authoring.markdown_editor import editor_blocks
        (self.vault / 'Media').mkdir()
        (self.vault / 'Media/potato.mp4').write_bytes(b'video fixture')
        source = '![[potato.mp4]]\n'
        (self.vault / 'Home.md').write_text(source)
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            with patch.object(owner.web, 'set_content') as publish:
                self.assertTrue(await owner.open_note('Vault/Home.md'))
            media = owner.library.image_source('Vault/Home.md')
            html = publish.call_args.args[1]
            self.assertIn('<video ', html)
            blocks = editor_blocks(source, image_source=media)
            self.assertIn('<video ', blocks[0]['html'])
            self.assertIn('![[potato.mp4]]', blocks[0]['source'])
            transports = [transport for _, transport in media.videos.values()]
            from unittest.mock import AsyncMock
            self.app.set_feature_enabled('video', True, refresh=False)
            with patch.object(owner.web, 'evaluate_javascript', new_callable=AsyncMock) as pause, patch(
                    'features.video.mobile.player.open_video', new_callable=AsyncMock, return_value=True) as native:
                for video in ('Vault/Media/potato.mp4', 'potato.mp4'):
                    self.assertTrue(await owner.open_note(video, resolve_link=video == 'potato.mp4'), owner.notice.text)
                self.assertEqual(pause.await_count, 2)
            self.assertEqual(native.await_count, 2)
            native.assert_awaited_with(self.app, self.provider, 'Vault/Media/potato.mp4')
            self.assertEqual(owner.path, 'Vault/Home.md')
            self.assertIsNone(owner.embedded)
            # Native mobile HTML embeds are deliberately simple and lazy. No
            # full-player resume preferences or autoplay enter page rendering.
            self.assertIn('controls playsinline preload="none"', html)
            self.assertNotIn('autoplay', html)
            self.assertNotIn('#t=', html)
            self.assertNotIn('autoplay', blocks[0]['html'])
            owner.dispose()
            self.assertTrue(all(transport.closed.is_set() for transport in transports))
            self.assertIsNone(media('potato.mp4'))
        self.run_async(exercise())

    def test_miscellaneous_files_are_visible_and_movable_but_dotfiles_are_hidden(self):
        from mobile.obsidian import open_vault
        for name in ('clip.mp4', 'archive.bin', 'LICENSE', '.secret'):
            (self.vault / name).write_bytes(b'content')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            names = {row['name'] for row in owner.folders['Vault']}
            self.assertTrue({'clip.mp4', 'archive.bin', 'LICENSE'} <= names)
            self.assertNotIn('.secret', names)
            self.assertNotIn('.obsidian', names)
            owner.library.move('Vault/archive.bin', 'Vault/renamed.bin')
            self.assertEqual((self.vault / 'renamed.bin').read_bytes(), b'content')
        self.run_async(exercise())

    def test_drag_moves_files_and_folders_and_library_root_is_an_explicit_target(self):
        from mobile.obsidian import open_vault
        (self.vault / 'Destination').mkdir()
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            self.assertIn(owner.root_drop_button, owner.files_content.children)
            await owner.open_note('Vault/Home.md')
            owner.sidebar.show_sidebar()
            from mobile.favourites import catalog, reference
            source, title, opener, cipher = reference(self.app)
            catalog(self.app).remember(source, title, opener, favourite=True, cipher=cipher)
            drag = owner.file_drag
            self.assertTrue(drag.start('Vault/Home.md'))
            self.assertTrue(drag.drop('Vault/Destination'))
            self.assertTrue(await drag.task)
            self.assertEqual(owner.path, 'Vault/Destination/Home.md')
            self.assertTrue(catalog(self.app).entries()[0]['source']['path'].endswith('/Destination/Home.md'))
            self.assertTrue(owner.sidebar.sidebar_open)
            self.assertFalse((self.vault / 'Home.md').exists())
            self.assertTrue(drag.start('Vault/Destination/Home.md'))
            self.assertTrue(drag.drop(owner.root))
            self.assertTrue(await drag.task)
            self.assertEqual(owner.path, 'Vault/Home.md')
            self.assertTrue(drag.start('Vault/Projects'))
            self.assertIsNone(drag.destination('Vault/Projects/Child'))
            self.assertTrue(drag.drop('Vault/Destination'))
            self.assertTrue(await drag.task)
            self.assertTrue((self.vault / 'Destination/Projects/Plan.MD').is_file())
            (self.vault / 'Destination/Home.md').write_text('Existing destination')
            self.assertTrue(drag.start('Vault/Home.md'))
            self.assertTrue(drag.drop('Vault/Destination'))
            self.assertFalse(await drag.task)
            self.assertTrue((self.vault / 'Home.md').is_file())
            self.assertEqual((self.vault / 'Destination/Home.md').read_text(), 'Existing destination')
            self.assertTrue(owner.article.enabled)
            self.assertFalse(drag.start(owner.root))
            owner.close()
        self.run_async(exercise())

    def test_android_local_drag_callbacks_keep_paths_out_of_native_payload(self):
        from mobile.obsidian import open_vault
        from types import SimpleNamespace
        import sys
        class Native:
            def setOnLongClickListener(self, value): self.long_click = value
            def setOnDragListener(self, value): self.drag = value
            def startDragAndDrop(self, clip, shadow, state, flags):
                self.clip = clip
                return True
        class Widget:
            def __init__(self): self._impl = SimpleNamespace(native=Native())
        class Clip:
            @staticmethod
            def newPlainText(label, text): return (label, text)
        events = SimpleNamespace(ACTION_DRAG_STARTED=1, ACTION_DRAG_ENTERED=2, ACTION_DRAG_LOCATION=3,
                                 ACTION_DROP=4, ACTION_DRAG_EXITED=5, ACTION_DRAG_ENDED=6)
        view = SimpleNamespace(OnLongClickListener=object, OnDragListener=object, DragShadowBuilder=lambda native: native)
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            drag = owner.file_drag
            source, target = Widget(), Widget()
            modules = {'android.view': SimpleNamespace(View=view, DragEvent=events),
                       'android.content': SimpleNamespace(ClipData=Clip),
                       'java': SimpleNamespace(dynamic_proxy=lambda protocol: object)}
            with patch.dict(sys.modules, modules):
                drag.bind_android(source, 'Vault/Projects/Plan.MD', True, False)
                drag.bind_android(target, owner.root, False, True)
                self.assertTrue(source._impl.native.long_click.onLongClick(source._impl.native))
                self.assertEqual(source._impl.native.clip, (drag.token, ''))
                event = SimpleNamespace(getAction=lambda: events.ACTION_DROP,
                    getClipDescription=lambda: SimpleNamespace(getLabel=lambda: drag.token))
                self.assertTrue(target._impl.native.drag.onDrag(target._impl.native, event))
                self.assertTrue(await drag.task)
                self.assertTrue((self.vault / 'Plan.MD').is_file())
                drag.unbind(source)
                drag.unbind(target)
                self.assertIsNone(source._impl.native.long_click)
                self.assertIsNone(target._impl.native.drag)
            owner.close()
        self.run_async(exercise())

    def test_documents_discovers_libraries_two_folders_down_without_reading_notes(self):
        from mobile.notes_discovery import find_libraries
        (self.root / 'One/Two/.obsidian').mkdir(parents=True)
        (self.root / 'One/Two/TooDeep/.obsidian').mkdir(parents=True)
        (self.root / '.hidden/.obsidian').mkdir(parents=True)
        provider = LocalFiles(self.root)
        with patch.object(provider, 'open', side_effect=AssertionError('Discovery must not read documents')), \
                patch.object(provider, 'list', wraps=provider.list) as listing:
            found = find_libraries(provider)
        self.assertIn('Vault', found)
        self.assertIn('One/Two', found)
        self.assertNotIn('One/Two/TooDeep', found)
        self.assertNotIn('.hidden', found)
        self.assertFalse(any('.obsidian' in call.args[0] for call in listing.call_args_list))


    def test_favourite_reopens_note_inside_its_library(self):
        from mobile.obsidian import open_vault
        from mobile.favourites import reference, catalog, reopen
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            await owner.open_note('Vault/Home.md')
            self.assertEqual(owner.session.title, 'Vault')
            self.assertEqual(owner.view._native_reader_title(), 'Home.md')
            source, title, opener, cipher = reference(self.app)
            self.assertIsNone(cipher)
            catalog(self.app).remember(source, title, opener, favourite=True)
            row = catalog(self.app).entries()[0]
            owner.close()
            self.assertTrue(await reopen(self.app, row))
            restored = self.app.vault_browser
            self.assertEqual(restored.path, 'Home.md')
            self.assertEqual(restored.provider.root, self.vault.resolve())
            restored.close()
        self.run_async(exercise())

    def test_system_back_restores_browsing_after_each_document_kind(self):
        from mobile.obsidian import open_vault
        from features.notebooks.notebook import Notebook
        (self.vault / 'Code.json').write_text('{}')
        (self.vault / 'Drawing.rmdoc').write_bytes(Notebook.new('Drawing').to_bytes())
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            for path in ('Vault/Home.md', 'Vault/Code.json', 'Vault/Drawing.rmdoc'):
                owner.sidebar.show_sidebar()
                self.assertTrue(await owner.open_note(path))
                self.assertFalse(owner.sidebar.sidebar_open)
                self.assertEqual(owner.back_action(), owner.return_to_browsing)
                owner.back_action()()
                self.assertEqual(owner.sidebar.side, 'files')
                self.assertIsNone(owner._document_return_side)
                self.assertEqual(owner.back_action(), owner.sidebar.show_detail)
                owner.back_action()()
            owner.close()
        self.run_async(exercise())

    def test_json_and_view_scripts_use_embedded_code_input_and_preserve_source_bytes(self):
        from dataclasses import replace
        from unittest.mock import AsyncMock
        from mobile.obsidian import open_vault
        from commonUtils.ui.native.code_input import CodeInput
        folder = self.vault / '_Resources/dataview'
        folder.mkdir(parents=True)
        path = folder / 'items.json'
        path.write_bytes(b'\xef\xbb\xbf{\r\n  "name": "Original"\r\n}\r\n')
        (folder / 'show.js').write_text('dv.paragraph("Script source");')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.load_folder('Vault/_Resources/dataview')
            self.assertEqual({row['name'] for row in owner.folders['Vault/_Resources/dataview']}, {'items.json', 'show.js'})
            self.assertTrue(await owner.open_note('Vault/_Resources/dataview/items.json'))
            editor = owner.embedded
            self.assertIsInstance(editor.source, CodeInput)
            self.assertIn(editor.view, owner.article.children)
            editor.source.value = '{\n  "name": "Edited in library"\n}\n'
            editor.changed(editor.source.value)
            self.assertTrue(await editor.save())
            self.assertEqual(path.read_bytes(), b'\xef\xbb\xbf{\r\n  "name": "Edited in library"\r\n}\r\n')
            editor.source.value = '{"draft":true}'
            editor.changed(editor.source.value)
            path.write_text('{"external":true}')
            self.assertFalse(await editor.save())
            self.assertTrue(editor.dirty)
            self.assertEqual(editor.text, '{"draft":true}')
            self.assertEqual(path.read_text(), '{"external":true}')
            with patch.object(owner, 'host', replace(owner.host, confirm=AsyncMock(return_value='cancel'))):
                self.assertFalse(await owner.open_note('Vault/Home.md'))
            self.assertIs(owner.embedded, editor)
            with patch.object(owner, 'host', replace(owner.host, confirm=AsyncMock(return_value='discard'))):
                self.assertTrue(await owner.open_note('Vault/Home.md'))
            self.assertTrue(await owner.open_note('_Resources/dataview/show.js', resolve_link=True))
            self.assertEqual(owner.embedded.text, 'dv.paragraph("Script source");')
            self.assertEqual(owner.embedded.kind, 'text')
            owner.dispose()
            self.assertEqual(editor.text, '')
        self.run_async(exercise())

    def test_data_view_heading_jump_waits_for_generated_content(self):
        from unittest.mock import AsyncMock
        from mobile.obsidian import open_vault
        (self.vault / 'Home.md').write_text('```dataviewjs\ndv.header(2, "Generated target");\n```\n')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            with patch.object(owner, 'scroll_fragment') as scroll, \
                    patch('features.notes_library.mobile.dataview.execute_views', new=AsyncMock(return_value='## Generated target\n')):
                self.assertTrue(await owner.open_note('Vault/Home.md', fragment='generated-target'))
                owner.page_loaded()
                scroll.assert_not_called()
                self.assertEqual(owner.pending_fragment, 'generated-target')
                await owner.data_view_task
                owner.page_loaded()
                scroll.assert_called_once_with('generated-target')
                self.assertEqual(owner.pending_fragment, '')
        self.run_async(exercise())

    def test_data_view_output_does_not_change_authored_source_and_stale_output_is_discarded(self):
        from unittest.mock import AsyncMock
        from mobile.obsidian import open_vault
        source = '# Dashboard\n\n```dataviewjs\nawait dv.view("views/inventory");\n```\n'
        (self.vault / 'Home.md').write_text(source)
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            with patch.object(owner.web, 'set_content') as publish:
                await owner.open_note('Vault/Home.md')
                initial = publish.call_args.args[1]
                self.assertIn('Loading data view', initial)
                self.assertIn('worker-src blob:', initial)
                plan = owner.data_view_plan
                owner.data_view_plan = None
                with patch('features.notes_library.mobile.dataview.execute_views',
                           new=AsyncMock(return_value='# Dashboard\n\n| Name |\n| --- |\n| Mobile result |\n')):
                    await owner.render_data_views(plan, owner.base, owner.path)
                self.assertIn('Mobile result', publish.call_args.args[1])
                self.assertNotIn('worker-src blob:', publish.call_args.args[1])
                self.assertEqual((self.vault / 'Home.md').read_text(), source)
                entered, release = asyncio.Event(), asyncio.Event()
                async def slow(*args, **kwargs):
                    entered.set()
                    await release.wait()
                    return 'Stale result'
                with patch('features.notes_library.mobile.dataview.execute_views', side_effect=slow):
                    pending = asyncio.create_task(owner.render_data_views(plan, owner.base, owner.path))
                    await entered.wait()
                    await owner.open_note('Vault/Projects/Plan.MD')
                    calls = publish.call_count
                    release.set()
                    await pending
                    self.assertEqual(publish.call_count, calls)
                    self.assertNotIn('Stale result', publish.call_args.args[1])
        self.run_async(exercise())

    def test_percent_encoded_links_and_connections_prefer_decoded_then_literal(self):
        from features.notes_library.notes_links import connections
        library = NotesLibrary(self.provider, 'Vault')
        raw = self.vault / 'Two%20Words.md'
        decoded = self.vault / 'Projects/Two Words.md'
        raw.write_text('# Literal')
        home = self.vault / 'Home.md'
        home.write_text('[Target](Two%20Words.md#heading)')
        for target in ('Two%20Words.md#heading', 'Two%20Words#heading'):
            self.assertEqual(library.link('Vault/Home.md', target), ('Vault/Two%20Words.md', 'heading'))
        self.assertEqual(connections(library, 'Vault/Two%20Words.md')['incoming'], ['Vault/Home.md'])
        decoded.write_text('# Decoded')
        for target in ('Two%20Words.md#heading', 'Two%20Words#heading'):
            self.assertEqual(library.link('Vault/Home.md', target), ('Vault/Projects/Two Words.md', 'heading'))
        self.assertEqual(connections(library, 'Vault/Projects/Two Words.md')['incoming'], ['Vault/Home.md'])
        self.assertEqual(connections(library, 'Vault/Two%20Words.md')['incoming'], [])
        self.assertEqual(connections(library, 'Vault/Home.md')['outgoing'], ['Vault/Projects/Two Words.md'])
        self.assertEqual(library.link('Vault/Home.md', 'Two%2520Words.md'), ('Vault/Two%20Words.md', ''))
        (self.vault / 'Other').mkdir()
        (self.vault / 'Other/Two Words.md').write_text('# Ambiguous decoded')
        with self.assertRaisesRegex(ValueError, 'Several notes'):
            library.link('Vault/Home.md', 'Two%20Words.md')
        self.assertIn('Two%20Words.md#heading', connections(library, 'Vault/Home.md')['unresolved'])

    def test_connections_apply_navigation_normalization_and_containment_before_fallback(self):
        from features.notes_library.notes_links import connections
        library = NotesLibrary(self.provider, 'Vault')
        (self.vault / 'Projects/Two Words.md').write_text('# Target')
        source = self.vault / 'Other/Source.md'
        source.parent.mkdir()
        target = 'Projects//Two%20Words.md'
        source.write_text('[Target](' + target + ')')
        self.assertEqual(library.link('Vault/Other/Source.md', target)[0], 'Vault/Projects/Two Words.md')
        self.assertEqual(connections(library, 'Vault/Projects/Two Words.md')['incoming'], ['Vault/Other/Source.md'])
        # Both literal names exist inside the vault, but their decoded targets
        # are forbidden; a connection must not suggest they can be followed.
        (self.vault / '%2e%2e').mkdir()
        (self.vault / '%2e%2e/Outside.md').write_text('# Literal')
        (self.vault / 'Bad%00Name.md').write_text('# Literal')
        for target in ('%2e%2e/Outside.md', 'Bad%00Name.md'):
            (self.vault / 'Home.md').write_text('[Target](' + target + ')')
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    library.link('Vault/Home.md', target)
                links = connections(library, 'Vault/Home.md')
                self.assertIn(target, links['unresolved'])
                self.assertEqual(links['outgoing'], [])

    def test_explicit_percent_encoded_note_paths_fall_back_without_escaping(self):
        library = NotesLibrary(self.provider, 'Vault')
        (self.vault / 'Projects/Two%20Words.md').write_text('# Literal')
        self.assertEqual(library.link('Vault/Home.md', './Projects/Two%20Words.md'),
                         ('Vault/Projects/Two%20Words.md', ''))
        for target in ('%2e%2e/outside.md', '%2foutside.md', 'bad%5cname.md'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                library.link('Vault/Home.md', target)

    def test_direct_links_probe_only_the_target_without_listing_siblings(self):
        library = NotesLibrary(self.provider, 'Vault')
        with patch.object(self.provider, 'list', side_effect=AssertionError('Listed unrelated notes')):
            self.assertEqual(library.link('Vault/Home.md', 'Projects/Plan.MD#heading'),
                             ('Vault/Projects/Plan.MD', 'heading'))
            self.assertEqual(library.link('Vault/Projects/Plan.MD', 'Home'), ('Vault/Home.md', ''))
            self.assertEqual(library.link('Vault/Projects/Plan.MD', '../Home.md'), ('Vault/Home.md', ''))
            with self.assertRaisesRegex(ValueError, 'not found'):
                library.link('Vault/Home.md', './missing.md')
            (self.vault / 'Linked.md').symlink_to(self.vault / 'Home.md')
            with self.assertRaisesRegex(ValueError, 'Linked storage'):
                library.link('Vault/Home.md', 'Linked.md')

    def test_global_link_lookup_reuses_names_and_detects_external_changes(self):
        (self.vault / 'Projects/Tech.md').write_text('# Tech')
        library = NotesLibrary(self.provider, 'Vault')
        with patch.object(self.provider, 'list', wraps=self.provider.list) as listing:
            self.assertEqual(library.link('Vault/Home.md', 'Tech'), ('Vault/Projects/Tech.md', ''))
            self.assertEqual(listing.call_count, 2)
            listing.reset_mock()
            self.assertEqual(library.link('Vault/Home.md', 'Tech'), ('Vault/Projects/Tech.md', ''))
            listing.assert_not_called()
            (self.vault / 'New').mkdir()
            (self.vault / 'New/Tech.md').write_text('# Another Tech')
            with self.assertRaisesRegex(ValueError, 'Several notes'):
                library.link('Vault/Home.md', 'Tech')
            self.assertEqual({call.args[0] for call in listing.call_args_list}, {'Vault', 'Vault/New'})
            (self.vault / 'Projects/Tech.md').unlink()
            self.assertEqual(library.link('Vault/Home.md', 'Tech'), ('Vault/New/Tech.md', ''))
            (self.vault / 'New/Tech.md').rename(self.vault / 'New/Renamed.md')
            with self.assertRaisesRegex(ValueError, 'not found'):
                library.link('Vault/Home.md', 'Tech')

    def test_close_retires_cached_names_and_a_late_scan_cannot_repopulate_them(self):
        from commonUtils.runtime.operations import OperationCancelled
        library = NotesLibrary(self.provider, 'Vault')
        library._link_listing('Vault', lambda: False)
        self.assertTrue(library._link_folders)
        library.close()
        self.assertEqual(library._link_folders, {})
        with self.assertRaises(OperationCancelled):
            library._link_listing('Vault', lambda: False)
        library = NotesLibrary(self.provider, 'Vault')
        original = self.provider.list
        def retire_during_listing(*args, **kwargs):
            rows = original(*args, **kwargs)
            library.close()
            return rows
        with patch.object(self.provider, 'list', side_effect=retire_during_listing):
            with self.assertRaises(OperationCancelled):
                library._link_listing('Vault', lambda: False)
        self.assertEqual(library._link_folders, {})


    def test_close_and_page_history_are_separate_controls(self):
        from mobile.obsidian import open_vault
        from commonUtils.runtime.resources.local import LocalFiles

        async def exercise():
            for width in (390, 900):
                with self.subTest(width=width):
                    self.app.show_documents_hub()
                    owner = await open_vault(self.app, LocalFiles(self.root), 'Vault', 'documents')
                    owner.reflow(width)
                    panel = self.app.body
                    key = owner.session.id
                    self.assertIs(owner.view._reader_close_button, owner.close_button)
                    self.assertEqual(owner.close_button.control_icon, 'close')
                    self.assertEqual(owner.view._native_reader_buttons(), [owner.links_button])
                    self.assertEqual(owner.secondary.children[:2], [owner.back_button, owner.forward_button])
                    self.assertEqual(owner.menu.control_icon, 'notes_files')
                    self.assertFalse(owner.back_button.enabled)
                    self.assertFalse(owner.forward_button.enabled)
                    await owner.open_note('Vault/Home.md')
                    owner.follow_link(owner.web, owner.base + '?target=Projects%2FPlan.MD')
                    for _ in range(100):
                        if owner.path == 'Vault/Projects/Plan.MD':
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(owner.back_button.enabled)
                    self.assertFalse(owner.forward_button.enabled)
                    owner.back_button.on_press()  # Native taps do not await returned coroutines.
                    for _ in range(100):
                        if owner.path == 'Vault/Home.md' and owner.history_index == 0:
                            break
                        await asyncio.sleep(.01)
                    self.assertEqual(owner.path, 'Vault/Home.md')
                    self.assertEqual(owner.view._document_path(), str(self.root / owner.path))
                    self.assertFalse(owner.back_button.enabled)
                    self.assertTrue(owner.forward_button.enabled)
                    self.assertIs(self.app.body, panel)
                    owner.forward_button.on_press()
                    for _ in range(100):
                        if owner.path == 'Vault/Projects/Plan.MD':
                            break
                        await asyncio.sleep(.01)
                    self.assertEqual(owner.path, 'Vault/Projects/Plan.MD')
                    self.assertEqual(owner.view._document_path(), str(self.root / owner.path))
                    owner.sidebar.show_sidebar()
                    owner.close_button.on_press()
                    self.assertNotIn(key, self.app.workspace.sessions)
                    self.assertTrue(owner.cancelled.is_set())
                    self.assertIsNone(owner.path)
                    self.assertIsNot(self.app.body, panel)

        self.run_async(exercise())

    @unittest.skipUnless(os.environ.get('LOGISTICS_MOBILE_BRIDGE'), 'Host native bridge required')
    def test_native_localcrypt_and_crypt_remote_actions_read_and_lock(self):
        from io import BytesIO
        from pathlib import Path
        from uuid import uuid4
        from features.rclone.mobile.cloud import CloudClient
        from features.rclone.localcrypt.mobile.resources import encrypted_storage
        fixture = json.loads(Path('mobile_build/native_tests/tests/logisticsmobile/localcrypt_fixture.json').read_text())
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            client = self.app.cloud_client = CloudClient(library=os.environ['LOGISTICS_MOBILE_BRIDGE'])
            client.request('import', package=fixture['package'], password='synthetic-resume-password',
                           package_name='Synthetic.zip', session_only=True)
            try:
                provider = encrypted_storage(self.app.private_root, client, 'Secret')
                provider.mkdir('.obsidian')
                provider.create_file('.obsidian/config.ini', BytesIO(b'[Fixture]'))
                provider.mkdir('Nested')
                provider.create_file('Home.md', BytesIO(b'# Private home'))
                provider.create_file('Nested/Next.md', BytesIO(b'# Private nested note'))
                self.app.cloud_crypt_remotes = {'Secret'}
                self.app.set_loaded_remote_names(['Secret'])
                self.app.remember_credential_association('Synthetic.zip', ['Secret'], session_only=True)
                self.assertEqual(self.app.existing_crypt_locations(), {'LocalCrypt: Secret': 'Secret'})
                self.app.show_documents_hub()
                while True:
                    discovery = self.app._notes_discovery_task
                    await discovery
                    if discovery is self.app._notes_discovery_task:
                        break
                buttons = self.app.document_notes_list.children[1].children
                self.assertIn('LocalCrypt: Secret', [button.text for button in buttons],
                              self.app.document_notes_list.children[2].text)
                detected = next(button for button in buttons if button.text == 'LocalCrypt: Secret')
                await detected.on_press()
                self.assertIsNotNone(getattr(self.app, 'vault_browser', None),
                                     self.app.document_notes_list.children[2].text)
                discovered = self.app.vault_browser
                self.assertEqual(self.app.native_host.state.destination, 'documents')
                self.assertTrue(discovered.provider.private)
                self.assertTrue(await discovered.open_note('Home.md'), discovered.notice.text)
                self.assertTrue(await discovered.open_note('Nested/Next.md'), discovered.notice.text)
                await discovered.navigate_history(-1)
                self.assertEqual(discovered.path, 'Home.md')
                self.assertNotIn('Synthetic.zip', self.app.preferences.values.get('remote_packages', ''))
                discovered.close()
                # Real cipher names must match across different parent paths.
                with patch.object(provider, 'list', side_effect=AssertionError('Decoded unrelated filenames')):
                    self.assertEqual(NotesLibrary(provider).link('Home.md', 'Next'), ('Nested/Next.md', ''))
                client.request('mirror_sync', remote='Secret', path='', identity=client.connection_identity('Secret'),
                               local_path=str(provider.root.resolve()), run=uuid4().hex, push=True)
                for kind, source, value in [('crypt', 'Local', 'Secret'), ('remote', 'Cloud', ('Secret', ''))]:
                    with self.subTest(kind=kind):
                        status = toga.Label('')
                        button = toga.Button('Open as Notes Library')
                        box = toga.Box(children=[status])
                        self.app.show_view(box, destination='files', route='encrypted-notes-action')
                        entry = dict(source=source, kind=kind, value=value, name='Secret')
                        await offer_notes(self.app, entry, box, button, status)
                        if kind == 'remote':
                            self.assertNotIn(button, box.children)
                            continue
                        self.assertIn(button, box.children, status.text)
                        await button.on_press()
                        owner = self.app.vault_browser
                        self.assertIsNotNone(owner)
                        self.assertTrue(await owner.open_note('Home.md'), owner.notice.text)
                        await owner.toggle_folder('Nested')
                        self.assertTrue(await owner.open_note('Nested/Next.md'), owner.notice.text)
                        owner.back_button.on_press()
                        for _ in range(100):
                            if owner.path == 'Home.md':
                                break
                            await asyncio.sleep(.01)
                        self.assertEqual(owner.path, 'Home.md')
                remote_update = self.root / 'remote-update'
                (remote_update / '.obsidian').mkdir(parents=True)
                (remote_update / 'Home.md').write_text('# Pulled while open')
                client.request('mirror_sync', remote='Secret', path='', identity=client.connection_identity('Secret'),
                               local_path=str(remote_update.resolve()), run=uuid4().hex, push=True, decrypted=True)
                client.request('mirror_sync', remote='Secret', path='', identity=client.connection_identity('Secret'),
                               local_path=str(provider.root.resolve()), run=uuid4().hex, push=False)
                self.assertEqual(owner.path, 'Home.md')
                self.assertEqual(owner.library.read('Home.md'), b'# Pulled while open')
                client.clear()
                self.assertFalse(await owner.open_note('Home.md'))
                self.app.clear_private_catalog()
                self.assertIsNone(owner.path)
                self.app.show_documents_hub()
                await self.app._notes_discovery_task
                self.assertFalse(self.app.document_notes_list.children[1].children)
            finally:
                client.clear()
        self.run_async(exercise())

    def test_documents_discovers_local_library_without_workspace_prompt(self):
        from services.documents.locations import collection_path
        folder = collection_path(self.app.private_root) / 'Notes'
        shutil.copytree(self.vault, folder)
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:await restore
            entry = dict(source='Local', kind='local', value='Notes', name='Notes', copies=[])
            self.app.show_picker_folder(entry)
            self.assertFalse(any(getattr(child, 'text', '') == 'Open as Notes Library'
                                 for child, _ in self.app.folder_action_controls))
            self.app.show_documents_hub()
            await self.app._notes_discovery_task
            button = next(child for child in self.app.document_notes_list.children[1].children
                          if getattr(child, 'text', '') == 'Notes · Local')
            self.assertIsNotNone(button.parent)
            await button.on_press()
            owner = self.app.vault_browser
            self.assertEqual(self.app.native_host.state.destination, 'documents')
            self.assertEqual(owner.session.provider, 'notes-library')
            self.assertIn(owner.session.id, self.app.workspace.sessions)
            self.assertIsNotNone(owner.search)
            await owner.open_note('Notes/Home.md')
            await owner.open_note('Notes/Projects/Plan.MD')
            await owner.navigate_history(-1)
            self.assertEqual(owner.path, 'Notes/Home.md')
            owner.show_page_search()
            owner.page_search.query.value = 'Home'
            self.assertTrue(owner.page_search.visible)
            key = owner.session.id
            self.app.show_documents_hub()
            self.app.session_opener(key)()
            self.assertEqual(self.app.native_host.state.destination, 'documents')
            self.app.close_session(key)
            self.assertNotIn(key, self.app.workspace.sessions)
            self.assertTrue(owner.page_search.closed)
            self.assertEqual(owner.page_search.query.value, '')
        self.run_async(exercise())

    def test_remote_action_has_no_search_and_never_lists_unopened_children(self):
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:await restore
            client = self.app.cloud_client = Client(self.vault)
            status = toga.Label('');button = toga.Button('Open as Notes Library');box = toga.Box(children=[status], style=Pack())
            self.app.show_view(box, destination='files', route='notes-action')
            entry = dict(source='Remote', kind='remote', value=('remote', ''), name='Remote')
            await offer_notes(self.app, entry, box, button, status)
            self.assertNotIn(button, box.children)
            self.assertEqual(client.calls, [])
        self.run_async(exercise())

    def test_missing_or_file_marker_does_not_offer_and_stale_probe_cannot_present(self):
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:await restore
            client = self.app.cloud_client = Client(self.vault)
            status = toga.Label('');button = toga.Button('Open as Notes Library');box = toga.Box(children=[status])
            self.app.show_view(box, destination='files', route='notes-action')
            entry = dict(source='Remote', kind='remote', value=('remote', ''), name='Remote')
            with patch.object(client, 'entries', return_value=[dict(path='.obsidian', directory=False)]):
                await offer_notes(self.app, entry, box, button, status)
            self.assertNotIn(button, box.children)
            original = client.entries
            def stale(remote, path):
                client.generation += 1
                return original(remote, path)
            with patch.object(client, 'entries', side_effect=stale):
                await offer_notes(self.app, entry, box, button, status)
            self.assertNotIn(button, box.children)
        self.run_async(exercise())

    def test_shared_bounds_and_links_are_enforced_for_remote(self):
        client = Client(self.vault)
        with self.assertRaisesRegex(ValueError, 'local copy'):
            NotesLibrary(RemoteNotes(client, 'remote'))
        self.assertEqual(client.calls, [])

    def test_expanded_private_html_is_refused_without_replacing_note(self):
        from types import SimpleNamespace
        from mobile.obsidian import VaultBrowser
        class PrivateFiles(LocalFiles):
            private = True
        self.app.cloud_client = SimpleNamespace(generation=1, cancel=lambda: None)
        owner = VaultBrowser(self.app, PrivateFiles(self.root), 'Vault', 'documents')
        self.app.vault_browser = owner
        async def exercise():
            self.assertTrue(await owner.open_note('Vault/Home.md'))
            history = list(owner.history)
            with patch('mobile.obsidian.markdown_preview', return_value='x' * (2 * 1024 * 1024 + 1)):
                self.assertFalse(await owner.open_note('Vault/Projects/Plan.MD'))
            self.assertEqual(owner.path, 'Vault/Home.md')
            self.assertEqual(owner.history, history)
        self.run_async(exercise())
