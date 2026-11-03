"""Execute authored JSON/custom views and preserve the Markdown/provider boundary."""
import json
from pathlib import Path

from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.ui.native.markdown_preview import markdown_preview
from features.notes_library.notes import NotesLibrary
from features.notes_library.dataview import ViewFiles, view_plan, runtime_script, javascript
from features.notes_library.dataview_script import POLL, worker_policy
from features.notes_library.ui.notes_library import NotesLibraryWindow

TEST_STAGE = TestStage.REGRESSION

FILE_SIZES = r'''
const files = app.vault.getMarkdownFiles();
const rows = files.map(file => ({name: file.basename, path: file.path, size: file.stat.size}))
    .sort((a, b) => b.size - a.size);
function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 ** 2).toFixed(2)} MB`;
}
dv.table(["File", "Size"], rows.map(file => [dv.fileLink(file.path), formatSize(file.size)]));
'''

FOLDER_INDEX = r'''
const currentFolder = dv.current().file.folder;
const currentFolderName = currentFolder.split("/").pop();
const pages = dv.pages(`"${currentFolder}"`).array();
function compareNames(a, b) {
    return a.file.name.localeCompare(b.file.name, undefined, { sensitivity: "base" });
}
function addInternalLink(container, page) {
    const link = container.createEl("a", {
        text: page.file.name, cls: "internal-link", href: page.file.path
    });
    link.dataset.href = page.file.path;
}
function getDirectChildFolders(folderPath) {
    return [...new Set(pages.map(page => page.file.folder).filter(pageFolder => {
        if (!pageFolder.startsWith(`${folderPath}/`)) return false;
        const relativePath = pageFolder.slice(folderPath.length + 1);
        return relativePath.length > 0 && !relativePath.includes("/");
    }))].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
}
function renderFolder(folderPath, container, skipIndex = false) {
    const folderName = folderPath.split("/").pop();
    const folderIndex = pages.find(page => page.file.folder === folderPath && page.file.name === folderName);
    const directFiles = pages.filter(page => page.file.folder === folderPath &&
        (!folderIndex || page.file.path !== folderIndex.file.path)).sort(compareNames);
    for (const page of directFiles) addInternalLink(container.createEl("li"), page);
    const childFolders = getDirectChildFolders(folderPath);
    for (const childFolderPath of childFolders) {
        const childFolderName = childFolderPath.split("/").pop();
        const childFolderIndex = pages.find(page =>
            page.file.folder === childFolderPath && page.file.name === childFolderName);
        if (!childFolderIndex) continue;
        const folderItem = container.createEl("li");
        addInternalLink(folderItem, childFolderIndex);
        const childList = folderItem.createEl("ul");
        renderFolder(childFolderPath, childList);
        if (childList.children.length === 0) childList.remove();
    }
}
const rootList = dv.container.createEl("ul");
renderFolder(currentFolder, rootList);
'''


class DataViewTests(QtTestCase):
    def test_vault_file_sizes_render_inline_and_nested_views_without_content_reads(self):
        from unittest.mock import patch
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Vault/Sub').mkdir(parents=True)
            (root / 'Vault/views').mkdir()
            (root / 'Vault/.hidden').mkdir()
            for name, content in (('Vault/Tiny.md', 'é'), ('Vault/Sub/Large # [x].markdown', 'x' * 2048),
                                  ('Vault/.hidden/Secret.md', 'secret'), ('Outside.md', 'outside')):
                (root / name).write_text(content, encoding='utf-8')
            (root / 'Vault/views/sizes.js').write_text(FILE_SIZES)
            window = NotesLibraryWindow(lambda: LocalFiles(root), 'File sizes', root='Vault')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            for code in (FILE_SIZES, 'await dv.view("views/sizes");'):
                source = '```dataviewjs\n' + code + '\n```\n'
                (root / 'Vault/Sub/Home.md').write_text(source)
                files = ViewFiles(window.library, 'Vault/Sub/Home.md')
                with patch.object(window.library.provider, 'open', side_effect=AssertionError('No content reads')):
                    index = files.request(dict(id=1, kind='index', metadata=True))['value']
                sizes = {page['file']['path']: page['file']['size'] for page in index['pages']}
                self.assertEqual(sizes['Tiny.md'], 2)
                self.assertEqual(sizes['Sub/Large # [x].markdown'], 2048)
                self.assertNotIn('.hidden/Secret.md', sizes)
                self.assertNotIn('Outside.md', sizes)
                window.open_note('Vault/Sub/Home.md', remember=False)
                self.wait_until(lambda: window.viewer.view_output is not None and
                                'Loading data view' not in window.viewer.view_output, timeout=20)
                result = window.viewer.view_output
                self.assertNotIn('Data view error', result)
                self.assertIn('Large%20%23%20%5Bx%5D.markdown', result)
                self.assertIn('[Tiny](<../Tiny.md>) | 2 B', result)
                self.assertIn('2\\.0 KB', result)
                self.assertLess(result.index('Large%20'), result.index('[Tiny]'))
                self.assertEqual((root / 'Vault/Sub/Home.md').read_text(), source)
            window.close()

    def test_recursive_folder_index_renders_inline_and_custom_view(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            for name in ('Guide/Child/Deep', 'Guide/Empty', 'Guide/NoIndex', 'Guide2', 'views'):
                (root / name).mkdir(parents=True)
            for name in ('Guide/alpha.md', 'Guide/Beta.md', 'Guide/Child/Child.md',
                         'Guide/Child/Deep/Deep.md', 'Guide/Child/Deep/Leaf # [x].md',
                         'Guide/Empty/Empty.md', 'Guide/NoIndex/Invisible.md', 'Guide2/Other.md'):
                (root / name).write_text('# ' + Path(name).stem)
            (root / 'views/folders.js').write_text(FOLDER_INDEX)
            window = NotesLibraryWindow(lambda: LocalFiles(root), 'Folder index')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            for code in (FOLDER_INDEX, 'await dv.view("views/folders");'):
                source = '# Guide\n\n```dataviewjs\n' + code + '\n```\n'
                (root / 'Guide/Guide.md').write_text(source)
                window.open_note('Guide/Guide.md', remember=False)
                self.wait_until(lambda: not window.progress.busy and window.viewer.markdown_text() == source and
                                window.viewer.view_output is not None and
                                'Loading data view' not in window.viewer.view_output, timeout=20)
                rendered = window.viewer.view_output
                self.assertNotIn('Data view error', rendered)
                self.assertIn('- [alpha](<alpha.md>)\n- [Beta](<Beta.md>)', rendered)
                self.assertIn('- [Child](<Child/Child.md>)\n    - [Deep](<Child/Deep/Deep.md>)', rendered)
                self.assertIn('        - [Leaf', rendered)
                self.assertIn('Leaf%20%23%20%5Bx%5D.md', rendered)
                self.assertIn('- [Empty](<Empty/Empty.md>)', rendered)
                for excluded in ('Invisible', 'Other', '[Guide]'):
                    self.assertNotIn(excluded, rendered)
                self.assertIn('Leaf # [x]', window.viewer.browser.toPlainText())
                self.assertEqual(window.viewer.markdown_text(), source)
                self.assertEqual((root / 'Guide/Guide.md').read_text(), source)
            target, _ = window.library.link('Guide/Guide.md', 'Child/Deep/Leaf%20%23%20%5Bx%5D.md')
            self.assertEqual(target, 'Guide/Child/Deep/Leaf # [x].md')
            window.close()

    def test_page_index_is_library_relative_hidden_filtered_and_bounded(self):
        from unittest.mock import patch
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Vault/Sub').mkdir(parents=True)
            (root / 'Vault/.hidden').mkdir()
            for name in ('Vault/Home.md', 'Vault/Sub/Sub.md', 'Vault/Sub/Extra.markdown', 'Vault/Sub/data.json',
                         'Vault/.hidden/Secret.md', 'Outside.md'):
                (root / name).write_text('content')
            files = ViewFiles(NotesLibrary(LocalFiles(root), 'Vault'), 'Vault/Sub/Sub.md')
            value = files.request(dict(id=1, kind='index'))['value']
            self.assertEqual(value['current']['file'], dict(path='Sub/Sub.md', folder='Sub', name='Sub'))
            self.assertEqual([page['file']['path'] for page in value['pages']],
                             ['Home.md', 'Sub/Extra.markdown', 'Sub/Sub.md'])
            with patch('features.notes_library.dataview.MAX_TOTAL', 1):
                self.assertIn('8 MiB', files.request(dict(id=2, kind='index'))['error'])
            with patch.object(files.library.provider, 'list_names', return_value=[{}] * 10001):
                self.assertIn('10,000', files.request(dict(id=3, kind='index'))['error'])

    def test_custom_view_matches_case_on_case_sensitive_encrypted_storage(self):
        from unittest.mock import patch
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '_Resources/dataview').mkdir(parents=True)
            (root / '_Resources/dataview/folder-index-recursive.js').write_text('dv.paragraph("found");')
            library = NotesLibrary(LocalFiles(root))
            files = ViewFiles(library, 'Home.md')
            requested = '_Resources/Dataview/folder-index-recursive'
            # macOS can mask the issue; model exact, case-sensitive provider reads.
            original = files.read
            def read(path, cancelled):
                return None if '/Dataview/' in path else original(path, cancelled)
            with patch.object(files, 'read', side_effect=read):
                reply = files.request(dict(id=1, kind='view', path=requested))
            self.assertEqual(reply['value']['code'], 'dv.paragraph("found");')
            self.assertNotIn('error', reply)

    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_localcrypt_source_editor_reads_and_saves_through_provider(self):
        from io import BytesIO
        from features.rclone import executable
        from features.rclone.localcrypt.backend import CryptResources
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone executable not installed')
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as fixture:
            fixture.provider.mkdir('.obsidian')
            fixture.provider.create_file('data.json', BytesIO(b'{"private":true}'))
            fixture.provider.mkdir('_Resources')
            fixture.provider.mkdir('_Resources/dataview')
            fixture.provider.create_file('_Resources/dataview/folder-index-recursive.js', BytesIO(b'dv.paragraph("found");'))
            files = ViewFiles(NotesLibrary(fixture.provider), 'Home.md')
            reply = files.request(dict(id=1, kind='view', path='_Resources/Dataview/folder-index-recursive'))
            self.assertEqual(reply['value']['code'], 'dv.paragraph("found");')
            window = NotesLibraryWindow(lambda: CryptResources(fixture.item, binary=binary), 'Encrypted source')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(window.windowTitle(), fixture.item.remote)
            fixture.provider.create_file('clip.mp4', BytesIO(b'encrypted video fixture'))
            media = window.library.image_source('Home.md')
            _, url = media('clip.mp4')
            from urllib.request import Request, urlopen
            with urlopen(Request(url, headers={'Range': 'bytes=0-8'}), timeout=5) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), b'encrypted')
            window.open_note('data.json')
            self.wait_until(lambda: not window.progress.busy)
            editor = window.text_document
            self.assertIsNotNone(editor, window.viewer.status.text())
            self.assertEqual(editor.editor.toPlainText(), '{"private":true}')
            editor.editor.selectAll()
            editor.editor.insertPlainText('{"private":"updated"}')
            self.assertTrue(editor.save())
            self.wait_until(lambda: not editor.busy)
            self.assertFalse(editor.dirty, editor.status.text())
            with fixture.provider.open('data.json') as stream:
                self.assertEqual(stream.read(), b'{"private":"updated"}')
            window.close()

    def test_source_conflict_keeps_draft_and_does_not_overwrite_external_changes(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            path = root / 'items.json'
            path.write_text('{"original":true}')
            window = NotesLibraryWindow(lambda: LocalFiles(root), 'Conflict')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            window.open_note('items.json')
            self.wait_until(lambda: not window.progress.busy)
            editor = window.text_document
            editor.editor.selectAll()
            editor.editor.insertPlainText('{"draft":true}')
            path.write_text('{"external":true}')
            self.assertTrue(editor.save())
            self.wait_until(lambda: not editor.busy)
            self.assertTrue(editor.dirty)
            self.assertEqual(editor.editor.toPlainText(), '{"draft":true}')
            self.assertEqual(path.read_text(), '{"external":true}')
            editor.editor.document().setModified(False)
            window.close()

    def test_json_and_scripts_edit_in_library_and_refresh_markdown_view(self):
        from unittest.mock import patch
        from commonUtils.ui.code_editor.widget import CodeEdit
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            (root / '_Resources/dataview').mkdir(parents=True)
            path = root / '_Resources/dataview/items.json'
            path.write_bytes(b'\xef\xbb\xbf{\r\n  "name": "Original"\r\n}\r\n')
            script = root / '_Resources/dataview/show.js'
            script.write_text('dv.paragraph(JSON.parse(await dv.io.load("_Resources/dataview/items")).name);')
            source = '# Dashboard\n\n```dataviewjs\nawait dv.view("_Resources/dataview/show");\n```\n'
            (root / 'Home.md').write_text(source)
            window = NotesLibraryWindow(lambda: LocalFiles(root), 'Text fixtures')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            window.list_folder('_Resources/dataview')
            self.wait_until(lambda: not window.progress.busy)
            self.assertIn('_Resources/dataview/items.json', window.items)
            self.assertIn('_Resources/dataview/show.js', window.items)
            window.open_note('_Resources/dataview/items.json')
            self.wait_until(lambda: not window.progress.busy)
            editor = window.text_document
            self.assertIs(window.document_stack.currentWidget(), editor)
            self.assertIsInstance(editor.editor, CodeEdit)
            editor.editor.selectAll()
            editor.editor.insertPlainText('{\n  "name": "Edited in library"\n}\n')
            window.save_current_document()
            self.wait_until(lambda: not editor.busy)
            self.assertEqual(path.read_bytes(), b'\xef\xbb\xbf{\r\n  "name": "Edited in library"\r\n}\r\n')
            window.open_note('Home.md')
            self.wait_until(lambda: 'Edited in library' in window.viewer.browser.toPlainText(), timeout=15)
            self.assertEqual(window.viewer.markdown_text(), source)
            # Explicit links route to the embedded source editor, too.
            window.open_note('_Resources/dataview/show.js', resolve_link=True)
            self.wait_until(lambda: not window.progress.busy)
            self.assertIs(window.document_stack.currentWidget(), editor)
            self.assertIn('dv.paragraph', editor.editor.toPlainText())
            editor.editor.insertPlainText('// Source editing\n')
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                window.open_note('Home.md')
            self.assertIs(window.document_stack.currentWidget(), editor)
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Save):
                window.open_note('Home.md')
            self.wait_until(lambda: not editor.busy and not window.progress.busy)
            self.wait_until(lambda: window.document_stack.currentWidget() is window.viewer)
            self.assertIn('// Source editing', script.read_text())
            window.close()

    def test_rooted_json_reads_relative_origins_missing_files_and_containment(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Vault/Sub').mkdir(parents=True)
            (root / 'Vault/data.json').write_text('[1,2]')
            (root / 'Vault/Sub/data.json').write_text('[3]')
            (root / 'outside.json').write_text('secret')
            (root / 'Vault/link.json').symlink_to(root / 'outside.json')
            files = ViewFiles(NotesLibrary(LocalFiles(root), 'Vault'), 'Vault/Sub/Home.md')
            def load(path, **kwargs):
                return files.request(dict(id=1, kind='load', path=path, **kwargs))
            self.assertEqual(load('data.json')['value'], '[1,2]')
            self.assertEqual(load('data')['value'], '[1,2]')
            self.assertEqual(load('./data.json')['value'], '[3]')
            self.assertEqual(load('./data')['value'], '[3]')
            self.assertEqual(load('data.json', origin='Sub/Home.md')['value'], '[3]')
            self.assertIsNone(load('missing.json')['value'])
            for path in ('../../outside.json', 'link.json', '.obsidian/config.json',
                         'Sub/../.obsidian/config.json', 'https://host/data.json', r'Sub\data.json'):
                with self.subTest(path=path):
                    self.assertIn('error', load(path))
            (root / 'Vault/large.json').write_bytes(b'x' * (2 * 1024 * 1024 + 1))
            self.assertIn('2 MiB', load('large.json')['error'])
            error = files.request(dict(id=1, kind='view', path='views/missing'))['error']
            self.assertIn('views/missing.js', error)
            self.assertIn('views/missing/view.js', error)

    def test_only_complete_top_level_fences_execute_and_source_is_preserved(self):
        source = ('# Home\n\n```dataviewjs\ndv.paragraph("yes");\n```\n'
                  '\n> ```dataviewjs\n> fail();\n> ```\n\n'
                  '````markdown\n```dataviewjs\nexample();\n```\n````\n'
                  '\n```dataviewjs\nincomplete();\n')
        plan = view_plan(source)
        self.assertEqual(len(plan.scripts), 1)
        rendered = plan.render(['Result'])
        self.assertIn('Result', rendered)
        self.assertNotIn('dv.paragraph', rendered)
        self.assertIn('example();', rendered)
        self.assertIn('incomplete();', rendered)
        self.assertEqual(plan.source, source)

    def test_frontmatter_and_unicode_separators_preserve_script_boundaries(self):
        prefix = ('---\r\nexample: |\r\n  ```dataviewjs\r\n  metadata();\r\n  ```\r\n---\r\n')
        before = 'Text with a Unicode separator\u2028inside one Markdown line.\r\n\r\n'
        source = prefix + before + '```dataviewjs\r\ndv.paragraph("body");\r\n```\r\n\r\nAfter\u2029text.\r\n'
        plan = view_plan(source)
        self.assertEqual(len(plan.scripts), 1)
        rendered = plan.render(['Generated body'])
        self.assertTrue(rendered.startswith(prefix + before))
        self.assertIn('Generated body', rendered)
        self.assertNotIn('dv.paragraph', rendered)
        self.assertTrue(rendered.endswith('After\u2029text.\r\n'))
        self.assertFalse(view_plan('---\n```dataviewjs\nmetadata();\n```\n').scripts)

    def test_total_read_budget_refuses_additional_io_before_opening_files(self):
        from unittest.mock import patch
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'data.json').write_text('[123]')
            provider = LocalFiles(root)
            files = ViewFiles(NotesLibrary(provider), 'Home.md')
            request = dict(id=1, kind='load', path='data.json')
            with patch('features.notes_library.dataview.MAX_TOTAL', 8), patch.object(provider, 'open', wraps=provider.open) as opened:
                self.assertEqual(files.request(request)['value'], '[123]')
                calls = opened.call_count
                for _ in range(3):
                    self.assertIn('8 MiB', files.request(request)['error'])
                self.assertEqual(opened.call_count, calls)

    def test_desktop_view_renders_json_nested_views_errors_and_never_saves_output(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'views/custom').mkdir(parents=True)
            (root / '.obsidian').mkdir()
            (root / 'data.json').write_text('[{"name":"Café | <img>","quantity":3}]')
            (root / 'views/custom/view.js').write_text('await dv.view("views/row.js", input);')
            (root / 'views/row.js').write_text('const rows=JSON.parse(await dv.io.load(input.path));'
                'dv.header(2,"Inventory");dv.table(["Name","Quantity"],rows.map(r=>[r.name,r.quantity]));'
                'dv.list(["One","Two"]);dv.paragraph("Done");')
            source = ('# Home\n\n```dataviewjs\nawait dv.view("views/custom", {path:"data.json"});\n```\n'
                      '\n```dataviewjs\ndv.unsupported();\n```\n')
            (root / 'Home.md').write_text(source)
            window = NotesLibraryWindow(lambda: LocalFiles(root), 'Test')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            window.open_note('Home.md')
            self.wait_until(lambda: 'Inventory' in window.viewer.browser.toPlainText(), timeout=20,
                            message=lambda: repr((window.viewer.browser.toPlainText(), window.viewer.view_output,
                                                  window.viewer.status.text(), window.viewer.data_views)))
            self.wait_until(lambda: 'Unsupported Dataview API' in window.viewer.browser.toPlainText())
            visible = window.viewer.browser.toPlainText()
            for expected in ('Café | <img>', '3', 'One', 'Two', 'Done'):
                self.assertIn(expected, visible)
            self.assertEqual(window.viewer.markdown_text(), source)
            self.assertFalse(window.viewer.is_modified)
            self.assertEqual((root / 'Home.md').read_text(), source)
            # Reopening sees changed JSON even when the Markdown did not change.
            (root / 'data.json').write_text('[{"name":"Refreshed","quantity":7}]')
            window.open_note('Home.md', remember=False)
            self.wait_until(lambda: 'Refreshed' in window.viewer.browser.toPlainText(), timeout=15)
            # Editing and saving must not execute the hidden reading surface.
            window.viewer.set_editing(True)
            (root / 'data.json').write_text('[{"name":"Changed during editing","quantity":8}]')
            window.viewer._render_source(window.viewer.markdown_text())
            self.assertIsNone(window.viewer.data_views.page)
            self.assertIsNone(window.viewer.view_key)
            window.viewer.set_editing(False)
            self.wait_until(lambda: 'Changed during editing' in window.viewer.browser.toPlainText(), timeout=15)
            window.close()

    def test_mobile_preview_policy_runs_shared_worker_and_json_io(self):
        from PySide6.QtWebEngineWidgets import QWebEngineView
        web = QWebEngineView()
        self.addCleanup(web.deleteLater)
        loaded = []
        web.loadFinished.connect(loaded.append)
        plan = view_plan('```dataviewjs\nconst data=JSON.parse(await dv.io.load("data.json"));'
                         'dv.table(["Item"],data.map(x=>[x])); dv.paragraph("Before tree");'
                         'const ordered=dv.container.createEl("ol");'
                         'const item=ordered.createEl("li",{text:"Old text"});'
                         'item.createEl("span",{text:"Removed child"}); item.textContent="First";'
                         'ordered.createEl("li",{text:"Second"});\n' + FOLDER_INDEX +
                         '\n' + FILE_SIZES +
                         '\ndv.paragraph("After tree");\n```\n')
        web.setHtml(worker_policy(markdown_preview(plan.render())))
        self.wait_until(lambda: loaded, timeout=10)
        def evaluate(script):
            values = []
            web.page().runJavaScript(script, values.append)
            self.wait_until(lambda: values)
            return values[0]
        evaluate(runtime_script(plan))
        states = []
        def requested():
            state = json.loads(evaluate(POLL))
            states.append(state)
            return bool(state['requests']) or state['done']
        self.wait_until(requested, timeout=10)
        request = states[-1]['requests'][0]
        self.assertEqual(request['kind'], 'index')
        index = dict(current=dict(file=dict(path='Home.md', folder='', name='Home')),
                     pages=[dict(file=dict(path='Mobile.md', folder='', name='Mobile', size=2048))])
        self.assertTrue(request['metadata'])
        evaluate('window.logisticsDataView.reply(' + javascript(dict(id=request['id'], value=index)) + ')')
        self.wait_until(requested, timeout=10)
        request = states[-1]['requests'][0]
        self.assertEqual(request['kind'], 'load')
        evaluate('window.logisticsDataView.reply(' + javascript(dict(id=request['id'], value='["Mobile"]')) + ')')
        def complete():
            state = json.loads(evaluate(POLL))
            states.append(state)
            return state['done']
        self.wait_until(complete, timeout=10)
        self.assertIn('| Mobile |', states[-1]['results'][0])
        self.assertIn('- [Mobile](<Mobile.md>)', states[-1]['results'][0])
        self.assertIn('| [Mobile](<Mobile.md>) | 2\\.0 KB |', states[-1]['results'][0])
        result = states[-1]['results'][0]
        self.assertIn('1. First\n2. Second', result)
        self.assertNotIn('Old text', result)
        self.assertNotIn('Removed child', result)
        self.assertLess(result.index('Before tree'), result.index('1. First'))
        self.assertLess(result.index('1. First'), result.index('- [Mobile]'))
        self.assertLess(result.index('- [Mobile]'), result.index('After tree'))

    def test_close_waits_for_data_view_provider_read_before_releasing_access(self):
        from threading import Event
        from unittest.mock import patch
        from shiboken6 import isValid
        entered, release = Event(), Event()
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            (root / 'Home.md').write_text('```dataviewjs\nawait dv.io.load("data.json");\n```\n')
            class RetainedFiles(LocalFiles):
                released = False
                def acquire(self):
                    return lambda: setattr(self, 'released', True)
            provider = RetainedFiles(root)
            original = ViewFiles.read
            def slow(files, path, cancelled):
                entered.set()
                release.wait(5)
                return original(files, path, cancelled)
            window = NotesLibraryWindow(lambda: provider, 'Lifetime')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            try:
                with patch.object(ViewFiles, 'read', slow):
                    window.open_note('Home.md')
                    self.wait_until(entered.is_set, timeout=10)
                    window.close()
                    self.assertTrue(isValid(window))
                    self.assertFalse(provider.released)
                    release.set()
                    self.wait_until(lambda: not isValid(window))
                    self.assertTrue(provider.released)
            finally:
                release.set()
