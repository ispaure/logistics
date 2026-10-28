"""Synthetic iOS toolbar ownership, native dispatch and resize evidence.

Launch with a separate QA bundle ID; never install over the normal app. Results
and screenshots are written to that QA app's cache. No remote service is used.
"""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile
from mobile.ios_toolbar import vertical_edge

BUNDLE = 'io.github.ispaure.logisticsduotoolbarqa'


class ToolbarProbe(LogisticsMobile):
    def startup(self):
        import mobile.incoming_files
        mobile.incoming_files.native_queues = lambda app: []
        self.storage_root = Path(self.paths.cache) / ('synthetic-toolbar-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.check())

    async def record(self, name):
        await asyncio.sleep(.5)
        navigation = self.native_host.adapter.navigation[
            self.native_host.destinations.index(self.native_host.state.destination)]
        controller = navigation.topViewController
        nav = controller.navigationItem
        leading = [item for group in nav.leadingItemGroups for item in group.barButtonItems]
        trailing = [item for group in nav.trailingItemGroups for item in group.barButtonItems]
        pinned = list(nav.pinnedTrailingGroup.barButtonItems) if nav.pinnedTrailingGroup is not None else []
        for item in (*leading, *trailing, *pinned):
            assert item.customView is None, (name, 'horizontal custom view')
            assert item.accessibilityLabel, (name, 'missing accessible title')
            # UIKit's system Close item can have a nil title even when its
            # accessible name is "Hide Find" or another contextual dismissal.
        sample = dict(name=name, edge=vertical_edge(controller),
                      leading=[str(item.title or item.accessibilityLabel) for item in leading],
                      trailing=[str(item.title) for item in trailing],
                      pinned=[str(item.title) for item in pinned],
                      overflow=nav.additionalOverflowItems is not None,
                      width=float(self.main_window.size.width), height=float(self.main_window.size.height))
        self.report['screens'].append(sample)
        (self.output / 'progress.json').write_text(json.dumps(self.report, indent=2))
        from rubicon.objc import Block, objc_id
        from toga_iOS.libs import UIGraphicsImageRenderer
        from toga_iOS.images import nsdata_to_bytes
        window = self.main_window._impl.native
        renderer = UIGraphicsImageRenderer.alloc().initWithSize(window.bounds.size)
        def draw(context):
            window.drawViewHierarchyInRect(window.bounds, afterScreenUpdates=True)
        (self.output / (name + '.png')).write_bytes(nsdata_to_bytes(
            renderer.PNGDataWithActions(Block(draw, None, objc_id))))
        return sample

    async def press(self, button):
        """Dispatch the actual bar item's target/action, not the Python callback."""
        item = button._ios_action_item
        assert item.isEnabled()
        item.target.performSelector(item.action, withObject=item)
        await asyncio.sleep(.5)

    async def additional_checks(self):
        """Focused audit subclasses can add panels before success is published."""

    async def check(self):
        self.output = Path(self.paths.cache) / 'toolbar-qa'
        self.output.mkdir(exist_ok=True)
        (self.output / 'result.json').unlink(missing_ok=True)
        self.report = dict(success=False, screens=[], checks=[])
        try:
            from commonUtils.runtime.resources.documents import LocalDocuments
            from commonUtils.runtime.resources.local import LocalFiles
            from features.text_editor.resources import LocalTextCopies
            from services.documents.locations import collection_path
            from tests.logisticsmobile.fixtures import make_books, png_page
            from types import SimpleNamespace
            from services.documents.readers import PrivateReader
            from pypdf import PdfWriter
            import io
            await asyncio.sleep(1)
            self.show_home(); await self.record('home')
            self.show_locations(); await self.record('workspaces')
            self.show_documents_hub(); await self.record('documents')
            self.show_home()
            root = collection_path(self.private_root) / 'Comics'
            root.mkdir(exist_ok=True, parents=True)
            (root / 'Example.txt').write_text('Synthetic toolbar fixture')
            (root / 'Note.md').write_text('# Synthetic note\n\nToolbar fixture.')
            await self.show_files(location=('Local files', 'Comics'))
            sample = await self.record('folder')
            assert 'Search this folder' in sample['trailing']
            if sample['edge']:
                assert sample['overflow'] and len(sample['trailing']) == 1, sample
            await self.press(self.file_browser.search_button)
            assert self.file_browser.search_open
            await self.record('folder-search')
            await self.press(self.file_browser.search_button)
            assert not self.file_browser.search_open
            self.report['checks'].append('native-search-target-action')
            self.show_chat(); self.adaptive.render()
            await self.record('chat')
            await self.press(self.chat_header_new)
            assert self.chat_current is not None
            self.show_chat_configuration()
            sample = await self.record('chat-settings')
            assert sample['pinned'] == ['Save & return to chat'], sample
            self.show_home()
            await self.choose_document_type()
            sample = await self.record('new-document')
            assert sample['pinned'] == ['Create document'], sample
            self.routes.back()
            assert self.create_chosen_document('md', name='Toolbar.md', content='# Toolbar')
            await self.record('markdown-editor')
            self.editor_view.editor.value = '# Toolbar changed'
            self.adaptive.render()
            sample = await self.record('editor-dirty')
            assert sample['pinned'] == ['Save'], sample
            assert sample['leading'][0] == 'Close document', sample
            await self.press(self.editor_view.save_button)
            assert not self.editor_view.document.modified
            self.report['checks'].append('native-save-target-action')
            self.show_home()
            epub, comic = make_books(root)
            if getattr(self, 'page_turns', False):
                from .page_motion_checks import expand_epub, expand_comic
                expand_epub(epub)
                expand_comic(comic)
            for path, kind in ((epub, 'epub'), (comic, 'comic')):
                book = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), path)
                assert await self.open_book(book['id'])
                owner = self.readers.active
                owner.set_reading_mode(False)
                await self.record(kind)
                owner.show_reader_appearance()
                sample = await self.record(kind + '-appearance')
                assert sample['pinned'] == ['Apply and return'], sample
                self.show_home()
            from mobile.obsidian import open_vault
            vault = await open_vault(self, LocalFiles(root), '', destination='home')
            await self.record('notes-library')
            await vault.open_note('Note.md')
            await self.record('notes-article')
            self.show_home()
            for key in ('Example.txt', 'Note.md'):
                assert await asyncio.wait_for(self.open_crypt(copies=LocalTextCopies(LocalFiles(root)), key=key), 20)
                await self.record('provider-' + key.replace('.', '-'))
                self.show_home()
            writer = PdfWriter(); writer.add_blank_page(width=300, height=400)
            writer.add_blank_page(width=300, height=400)
            data = io.BytesIO(); writer.write(data)
            (root / 'Page.pdf').write_bytes(data.getvalue())
            (root / 'Image.png').write_bytes(png_page())
            def opened(key, **kwargs):
                if key.endswith('.png'):
                    from features.rclone.mobile.remote_readers import RemoteImageReader
                    reader = RemoteImageReader(key, (root / key).read_bytes(), SimpleNamespace(check=lambda: None))
                else:
                    reader = PrivateReader(key, (root / key).read_bytes())
                reader.key = key
                return reader
            copies = SimpleNamespace(root=root, provider=LocalFiles(root), encrypted=False, offline=True, open=opened)
            extra_readers = (epub.name, comic.name) if getattr(self, 'page_turns', False) else ()
            for key in ('Page.pdf', 'Image.png') + extra_readers:
                assert await asyncio.wait_for(self.open_crypt(copies=copies, key=key), 20)
                await self.record(key.replace('.', '-'))
                if getattr(self, 'page_turns', False):
                    self.private_sessions.active.close_crypt()
                self.show_home()
            self.show_home()
            self.show_library()
            await self.record('library')
            self.show_transfers()
            await self.record('transfers')
            self.show_transfer_options()
            sample = await self.record('transfer-settings')
            assert sample['pinned'] == ['Save settings'], sample
            self.show_settings()
            await self.record('settings')
            from mobile.documentation_ui import show_documentation
            show_documentation(self)
            await self.record('documentation')
            # Real scene geometry requests exercise axis changes on both standard
            # iPhone and Duo without overriding traits or fabricating device IDs.
            from rubicon.objc import ObjCClass
            for name, mask in (('landscape', 8), ('portrait-return', 2)):
                preferences = ObjCClass('UIWindowSceneGeometryPreferencesIOS').alloc().initWithInterfaceOrientations(mask)
                self.main_window._impl.native.windowScene.requestGeometryUpdateWithPreferences(preferences, errorHandler=None)
                await asyncio.sleep(1.2)
                self.adaptive.render()
                await self.record('documentation-' + name)
            await self.additional_checks()
            self.report['success'] = True
        except BaseException:
            self.report['error'] = traceback.format_exc()
        (self.output / 'result.json').write_text(json.dumps(self.report, indent=2))


def main():
    return ToolbarProbe('Toolbar QA', BUNDLE)
