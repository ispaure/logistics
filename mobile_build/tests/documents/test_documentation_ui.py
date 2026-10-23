"""Offline help entry, nested folder selection, inline search and adaptive layout."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile.app import LogisticsMobile
from commonUtils.ui.native.markdown import MarkdownWikiView
from mobile.preview import markdown_preview


def widgets(root):
    yield root
    for child in root.children:
        yield from widgets(child)


class DocumentationTests(unittest.TestCase):
    def test_bundled_settings_guide_renders_real_tables(self):
        root = Path(__file__).resolve().parents[3] / 'docs/user_mobile'
        html = markdown_preview((root / 'user_mobile.md').read_text(), local_links=True)
        self.assertIn('<table>', html)
        self.assertIn('<th>Logistics capability</th>', html)
        for guide in root.rglob('*.md'):
            with self.subTest(guide=guide.name):
                self.assertIn('</html>', markdown_preview(guide.read_text(), local_links=True))

    def test_feature_links_and_history_restore_scoped_tree(self):
        root = Path(__file__).resolve().parents[3]
        app_scope = root / 'docs'
        feature_scope = root / 'docs/features/lm'
        first = app_scope / 'user_mobile/user_mobile.md'
        second = feature_scope / 'user_mobile/user_mobile.md'
        owner = MarkdownWikiView(app_scope, first)
        owner.follow_link(owner.web, '../features/lm/user_mobile/user_mobile.md')
        self.assertEqual(owner.path, second)
        self.assertEqual(owner.catalog.root, app_scope)
        self.assertTrue(any(row.children[-1].text.startswith('✓ ') and
                            row.children[-1].text.endswith('on mobile') for row in owner.rows.children))
        self.assertTrue(owner.back())
        self.assertEqual(owner.path, first)
        self.assertEqual(owner.catalog.root, app_scope)
        self.assertTrue(owner.forward())
        self.assertEqual(owner.catalog.root, app_scope)

    def test_same_named_root_indents_and_reveals_child(self):
        root = Path(self.temporary.name).resolve() / 'docs'
        root.mkdir()
        (root / 'docs.md').write_text('# Home')
        child = root / 'child.md'
        child.write_text('# Child')
        owner = MarkdownWikiView(root)
        self.assertEqual(len(owner.rows.children), 2)
        self.assertEqual([row.children[0].style.width for row in owner.rows.children], [0, 20])
        owner.rows.children[1].children[-1].on_press()
        self.assertEqual(owner.path, child)
        self.assertIn(root, owner.expanded)
        self.assertTrue(owner.up())
        self.assertEqual(owner.path, root / 'docs.md')

    def test_expansion_indents_pages_and_folders_in_same_columns(self):
        root = Path(self.temporary.name).resolve() / 'docs'
        nested = root / 'folder' / 'nested'
        nested.mkdir(parents=True)
        (root / 'README.md').write_text('# Home')
        (root / 'folder' / 'folder.md').write_text('# Folder')
        (nested / 'nested.md').write_text('# Nested')
        (nested / 'leaf.md').write_text('# Leaf')
        owner = MarkdownWikiView(root)
        def row(title):
            return next(row for row in owner.rows.children if row.children[-1].text.endswith(title))
        row('Folder').children[1].on_press()
        row('Nested').children[1].on_press()
        parent, child, leaf = row('Folder'), row('Nested'), row('Leaf')
        self.assertEqual([r.children[0].style.width for r in (parent, child, leaf)], [0, 20, 40])
        self.assertEqual([r.children[1].style.width for r in (parent, child, leaf)], [48, 48, 48])
        row('Nested').children[1].on_press()
        self.assertFalse(any(r.children[-1].text.endswith('Leaf') for r in owner.rows.children))

    def test_heading_links_scroll_locally_and_after_page_load(self):
        root = Path(self.temporary.name).resolve()
        (root / 'README.md').write_text('# Home\n\n[Section](#home)')
        (root / 'other.md').write_text('# Other\n\n## Detail')
        owner = MarkdownWikiView(root)
        with patch.object(owner.web, 'evaluate_javascript') as evaluate:
            history = list(owner.history)
            self.assertFalse(owner.follow_link(owner.web, '#home'))
            self.assertIn('getElementById("home")', evaluate.call_args.args[0])
            self.assertEqual(owner.history, history)
            owner.follow_link(owner.web, 'other.md#detail')
            self.assertEqual(owner.pending_fragment, 'detail')
            owner.page_loaded()
            self.assertIn('getElementById("detail")', evaluate.call_args.args[0])
            self.assertEqual(owner.pending_fragment, '')

    def setUp(self):
        self.temporary = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.temporary.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.temporary.cleanup()

    def test_settings_entry_opens_bundled_guide(self):
        self.app.show_settings()
        navigation = self.app.settings_navigation
        navigation.choose('Help')
        box = navigation.sections['Help']
        button = next(child for child in widgets(box) if getattr(child, 'text', '') == 'Mobile documentation')
        button.on_press()
        owner = self.app.documentation
        self.assertEqual(owner.title.text, 'Logistics on mobile')
        self.assertGreaterEqual(len(owner.catalog.pages), 5)
        self.assertEqual(self.app.native_host.state.destination, 'settings')
        self.assertTrue(self.app.routes.back())
        self.assertEqual(navigation.selected, 'Help')
        self.assertIs(navigation.options['Help'].content, box)
        self.assertIn(navigation.options['Help'],
                      navigation.detail.children if navigation.wide else self.app.body.children)

    def test_documentation_speaker_opens_current_page_and_stops_on_navigation(self):
        import json
        from unittest.mock import AsyncMock
        from mobile_build.tests.editing.test_markdown_speech import Engine
        from mobile.documentation_ui import show_documentation
        root = Path(self.temporary.name).resolve() / 'help'
        root.mkdir()
        first, second = root / 'README.md', root / 'next.md'
        first.write_text('# Home\n\nRead this page.')
        second.write_text('# Next\n\nAnother page.')
        owner = show_documentation(self.app, root, first)
        self.assertEqual(list(owner.navigation.children)[-4:],
            [owner.back_button, owner.forward_button, owner.up_button, owner.speech.button])
        self.assertEqual(owner.speech.button.control_icon, 'speaker')

        async def exercise():
            with patch('features.books.mobile.speech_view.NativeSpeech', Engine):
                owner.show_browse()
                owner.speech.button.on_press()
                self.assertTrue(owner.reading)
                panel = owner.speech.panel
                await panel.ready_task
                with patch.object(owner.web, 'evaluate_javascript', AsyncMock(return_value=json.dumps('Home selected passage'))):
                    await panel.play()
                self.assertEqual(panel.engine.calls[0][0], 'Home selected passage')
                owner.open_page(second)
                self.assertTrue(panel.closed and panel.engine.closed)
                self.assertEqual(panel.session.ranges, [])
                owner.speech.button.on_press()
                panel = owner.speech.panel
                await panel.ready_task
                owner.back_button.on_press()
                self.assertEqual(owner.path, first)
                self.assertTrue(panel.closed)
                owner.speech.button.on_press()
                panel = owner.speech.panel
                await panel.ready_task
                self.app.show_settings()
                self.assertTrue(panel.closed)
        self.app.loop.run_until_complete(exercise())

    def test_host_wiki_icons_selection_and_toolbar_follow_article_pane(self):
        from mobile.documentation_ui import show_documentation
        root = Path(self.temporary.name).resolve() / 'docs'
        nested = root / 'folder'
        nested.mkdir(parents=True)
        home, child = root / 'README.md', nested / 'child.md'
        home.write_text('# Home')
        child.write_text('# Child')
        owner = show_documentation(self.app, root, child)
        for width in (900, 390, 900):
            owner.reflow(width)
            parent = owner.article if owner.wide else owner.view
            self.assertIs(owner.navigation.parent, parent)
            self.assertIs(parent.children[0], owner.navigation)
            selected = next(row for row in owner.rows.children if row.children[-1].wiki_path == child)
            self.assertEqual(selected._impl._surface_roles[0], 'hover')
            self.assertEqual(selected.children[2].browser_entry_kind, 'file')
            folder = next(row for row in owner.rows.children if row.children[-1].text == 'folder')
            self.assertEqual(folder.children[2].browser_entry_kind, 'folder')
            self.assertFalse(any(row.children[-1].text.startswith('✓') for row in owner.rows.children))
        owner.back()
        owner.open_page(home)
        self.assertTrue(all(row.children[-1].wiki_path != child or row._impl._surface_roles[0] == 'surface'
                            for row in owner.rows.children))

    def test_folder_landing_icon_opens_page_and_keeps_disclosure_separate(self):
        from mobile.documentation_ui import show_documentation
        root = Path(self.temporary.name).resolve() / 'docs'
        folder = root / 'guide'
        folder.mkdir(parents=True)
        (root / 'README.md').write_text('# Home')
        landing = folder / 'guide.md'
        landing.write_text('# Guide')
        (folder / 'child.md').write_text('# Child')
        owner = show_documentation(self.app, root, root / 'README.md')

        def folder_row():
            return next(row for row in owner.rows.children if row.children[-1].wiki_path == landing)

        row = folder_row()
        self.assertEqual(row.children[2].browser_entry_kind, 'folder_document')
        self.assertIn('Open folder page', row.children[-1].accessible_name)
        row.children[1].on_press()
        self.assertIn(folder, owner.expanded)
        self.assertEqual(owner.path, root / 'README.md')
        folder_row().children[-1].on_press()
        self.assertEqual(owner.path, landing)
        self.assertTrue(owner.reading)
        folder_row().children[1].on_press()
        self.assertNotIn(folder, owner.expanded)
        self.assertEqual(owner.path, landing)

    def test_phone_tablet_search_and_contained_links(self):
        root = Path(self.temporary.name).resolve() / 'docs'
        root.mkdir()
        (root / 'README.md').write_text('# Home\n\n[Next](test/test.md)')
        folder = root / 'test'
        folder.mkdir()
        (folder / 'test.md').write_text('# Apple\n\nLanding')
        child = folder / 'child.md'
        child.write_text('# Child\n\nneedle in source')
        owner = MarkdownWikiView(root)
        owner.reflow(390)
        self.assertEqual(owner.rows.style.width, 366)
        self.assertEqual(list(owner.content.children), [owner.article])
        owner.show_browse()
        self.assertEqual(list(owner.content.children), [owner.browse])
        owner.search.value = 'needle'
        owner.mode.value = 'Page text'
        owner.filter()
        self.assertEqual(len(owner.rows.children), 2)
        owner.rows.children[-1].children[-1].on_press()
        self.assertEqual(owner.path, child)
        self.assertTrue(owner.reading)
        self.assertEqual(owner.search.value, 'needle')
        owner.reflow(900)
        self.assertEqual(owner.rows.style.width, 260)
        self.assertEqual(list(owner.content.children), [owner.browse, owner.article])
        owner.reflow(390)
        self.assertEqual(owner.rows.style.width, 366)
        self.assertEqual(list(owner.content.children), [owner.article])
        self.assertFalse(owner.follow_link(owner.web, 'https://outside.invalid/guide.md'))
        self.assertEqual(owner.path, child)
        owner.follow_link(owner.web, 'test.md')
        self.assertEqual(owner.title.text, 'Apple')
        owner.follow_link(owner.web, '../../outside.md')
        self.assertEqual(owner.path, folder / 'test.md')
        owner.search.value = 'unfindable'
        owner.filter()
        self.assertEqual(owner.notice.text, 'No matching pages.')

    def test_wiki_links_are_opt_in_and_inert(self):
        text = '[Next](test/test.md) [Web](https://example.com/a.md) [Unsafe](javascript:alert)'
        html = markdown_preview(text, local_links=True)
        self.assertIn('href="test/test.md"', html)
        self.assertNotIn('href="https:', html)
        self.assertNotIn('href="javascript:', html)
        self.assertNotIn('<a href=', markdown_preview(text))

    def test_linked_code_opens_separate_text_session(self):
        import asyncio
        from mobile.documentation_ui import show_documentation
        root = Path(self.temporary.name).resolve() / 'docs'
        root.mkdir()
        (root / 'README.md').write_text('# Home')
        script = root / 'sample.py'
        script.write_text('print("hello")')
        owner = show_documentation(self.app, root)
        history = list(owner.history)
        destination = self.app.native_host.state.destination
        origin = self.app.body
        owner.follow_link(owner.web, 'sample.py')
        async def wait_for_editor():
            for _ in range(100):
                if (self.app.native_host.state.destination == destination and any(
                        session.title == 'sample.py' for session in self.app.workspace.sessions.values())):
                    return
                await asyncio.sleep(.01)
            self.fail('Linked code did not open in the text editor')
        self.app.loop.run_until_complete(wait_for_editor())
        self.assertEqual(owner.history, history)
        self.assertEqual(owner.path, root / 'README.md')
        self.assertEqual(self.app.native_host.state.destination, destination)
        self.assertTrue(self.app.routes.back())
        self.assertIs(self.app.body, origin)
        self.assertFalse(any(session.title == 'sample.py' for session in self.app.workspace.sessions.values()))
        self.assertFalse(self.app._document_tabs_hidden)


class DocumentationImageTests(unittest.TestCase):
    def test_native_wiki_renders_sized_gif_and_keeps_custom_renderer_compatible(self):
        from commonUtils.tests.test_gif_headers import GIF
        from commonUtils.ui.native.markdown_images import local_image_source
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs.md').write_text('# GIF\n\n![[colors #1.GIF|70]]\n')
            (root / 'colors #1.GIF').write_bytes(GIF)
            captured = []
            def render(text, size, **kwargs):
                html = markdown_preview(text, size, **kwargs)
                captured.append(html)
                return html
            owner = MarkdownWikiView(root, render=render, image_source_factory=local_image_source)
            self.assertIn('data:image/gif;base64,', captured[-1])
            self.assertIn('width="70"', captured[-1])
            # Existing custom callbacks need not adopt the new image-source keyword.
            legacy = MarkdownWikiView(root, render=lambda text, size, *, local_links: '<p>Legacy renderer</p>')
            self.assertEqual(legacy.path, owner.path)
            default = MarkdownWikiView(root)
            with patch.object(default.web, 'set_content') as load:
                self.assertTrue(default.open_page(default.path))
            self.assertIn('data:image/gif;base64,', load.call_args.args[1])
