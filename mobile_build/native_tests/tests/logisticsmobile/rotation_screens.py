"""Maintained rotation screens and their explicit, synthetic setup journeys.

Screen IDs are stable report/filter keys. Titles follow visible navigation; a
group keeps dependent actions together without opening unrelated features in a
focused run. Native geometry and retention assertions live in rotation_checks.
"""
from dataclasses import dataclass
from functools import cached_property

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.EXTENDED


@dataclass(frozen=True)
class RotationScreen:
    panel: str
    title: str
    group: str


SETTINGS_SCREENS = (
    ('settings-app', 'App'), ('settings-appearance', 'Appearance'),
    ('settings-text', 'Text'), ('settings-epub', 'EPUB'), ('settings-workspaces', 'Workspaces'),
    ('settings-privacy', 'Privacy & Security'), ('settings-help', 'Help'),
    ('settings-about', 'About'),
)


SCREENS = (
    RotationScreen('workspaces', 'Workspaces', 'workspaces'),
    RotationScreen('workspace-rclone', 'Workspaces → rclone', 'workspaces'),
    RotationScreen('workspace-Network shares', 'Workspaces → Network shares', 'workspaces'),
    RotationScreen('workspace-Local', 'Workspaces → Local', 'workspaces'),
    RotationScreen('folder', 'Workspaces → Local → Folder', 'folders'),
    RotationScreen('nested-folder', 'Workspaces → Local → Folder → Child', 'folders'),
    RotationScreen('home', 'Home', 'home'),
    RotationScreen('documents', 'Documents', 'documents'),
    RotationScreen('chat', 'Chat', 'chat'),
    RotationScreen('chat-configuration', 'Chat → Configuration', 'chat'),
    RotationScreen('settings', 'Settings', 'settings'),
    *(RotationScreen(panel, 'Settings → ' + title, 'settings') for panel, title in SETTINGS_SCREENS),
    RotationScreen('connections', 'Settings → Workspaces → rclone connections', 'connections'),
    RotationScreen('home-file-picker', 'Home → Open file', 'home-file-picker'),
    RotationScreen('markdown-preview', 'Home → Markdown preview', 'text'),
    RotationScreen('text-editor', 'Home → Text editor', 'text'),
    RotationScreen('epub', 'Books → EPUB reader', 'readers'),
    RotationScreen('comic', 'Books → Comic reader', 'readers'),
    RotationScreen('provider-markdown', 'Workspaces → Markdown preview', 'provider-text'),
    RotationScreen('provider-text-editor', 'Workspaces → Text editor', 'provider-text'),
    RotationScreen('provider-epub', 'Workspaces → EPUB reader', 'provider-epub'),
    RotationScreen('provider-epub-find', 'Workspaces → EPUB reader → Find', 'provider-epub'),
    RotationScreen('notes-library', 'Notes Library', 'notes'),
    RotationScreen('notes-article', 'Notes Library → Note', 'notes'),
    RotationScreen('documentation', 'Settings → Help → Documentation', 'documentation'),
)


def select_screens(panels=None):
    """Reject mistaken/empty selectors before any app or fixture mutation."""
    if panels is None:
        return SCREENS
    if isinstance(panels, str):
        raise ValueError('Rotation panels must be a collection of screen IDs, not a string.')
    requested = set(panels)
    if not requested:
        raise ValueError('Select at least one rotation screen.')
    unknown = requested - {screen.panel for screen in SCREENS}
    if unknown:
        raise ValueError('Unknown rotation screens: ' + ', '.join(sorted(map(str, unknown))))
    return tuple(screen for screen in SCREENS if screen.panel in requested)


def coverage_inventory(destination_items, categories, *, panels=None):
    """Compare with source catalogs; new destinations/categories remain visible gaps.

    Catalog entries describe navigation, not fixture setup. Readers, private
    sessions and nested routes still require the explicit scenarios below.
    This describes registration only; samples establish actual execution.
    """
    selected = {screen.panel for screen in select_screens(panels)}
    rows = [dict(panel=s.panel, title=s.title, group=s.group, selected=s.panel in selected)
            for s in SCREENS]
    titles = {s.title for s in SCREENS}
    source_titles = [row[1] for row in destination_items]
    source_titles.extend('Settings → ' + category.title for category in categories)
    gaps = [dict(title=title, reason='No shared rotation scenario registered; native coverage is unverified by this sweep.')
            for title in source_titles if title not in titles]
    return dict(screens=rows, gaps=gaps)


class _Fixtures:
    def __init__(self, app):
        self.app = app

    @cached_property
    def root(self):
        from services.documents.locations import collection_path
        root = collection_path(self.app.private_root) / 'Rotation fixture'
        (root / 'Child').mkdir(parents=True, exist_ok=True)
        (root / 'Child' / 'Note.md').write_text('# Rotation fixture\n\nRetain this panel.')
        return root

    @cached_property
    def books(self):
        from .fixtures import make_books
        folder = self.root / 'Readers'
        folder.mkdir(exist_ok=True)
        return make_books(folder)


async def _workspaces(app, fixtures, selected, check):
    app.show_locations()
    if 'workspaces' in selected:
        await check('workspaces')
    for source in ('rclone', 'Network shares', 'Local'):
        name = 'workspace-' + source
        if name in selected:
            app.change_folder_source(source)
            assert app.folder_source == source
            await check(name)


async def _folders(app, fixtures, selected, check):
    # The explicit local location avoids restoring a previously selected remote.
    await app.show_files(location=('Local files', fixtures.root.name))
    if 'folder' in selected:
        await check('folder')
    if 'nested-folder' in selected:
        await app.browser_file_folder(next(row for row in app.file_rows.values() if row['name'] == 'Child'))
        await check('nested-folder')


async def _home(app, fixtures, selected, check):
    app.show_home()
    await check('home')


async def _documents(app, fixtures, selected, check):
    app.show_documents_hub()
    await check('documents')


async def _chat(app, fixtures, selected, check):
    app.show_chat()
    if 'chat' in selected:
        await check('chat')
    if 'chat-configuration' in selected:
        app.show_chat_configuration()
        await check('chat-configuration')


async def _settings(app, fixtures, selected, check):
    from mobile.routes import contains
    app.show_settings()
    assert app.native_host.state.destination == 'settings', 'Settings navigation was refused'
    # Reselecting the active tab is the ordinary app action that clears retained
    # wide detail as well as compact routes. Showing the root alone retains it.
    assert app.select_destination('settings'), 'Settings root checkpoint was refused'
    navigation = app.settings_navigation
    assert not navigation.detail_requested and not app.routes.screens['settings']
    assert contains(app.body, navigation), 'Settings root is not mounted'
    if 'settings' in selected:
        await check('settings')
    for name, category in SETTINGS_SCREENS:
        if name in selected:
            navigation.choose(category)
            assert navigation.detail_requested and navigation.selected == category, ('Settings category was refused', category)
            assert contains(app.body, navigation.options[category]), ('Settings category is not mounted', category)
            await check(name)
            if category != 'About':
                app.routes.back()


async def _connections(app, fixtures, selected, check):
    app.show_cloud_connections()
    await check('connections')


async def _home_file_picker(app, fixtures, selected, check):
    app.show_home()
    assert await app.open_hub_file()
    await check('home-file-picker')
    app.adaptive.browser('home').cancel_browser()


async def _text(app, fixtures, selected, check):
    app.show_home()
    document = app.store.create('Rotation.md', b'# Rotation\n\nRetain this document.')
    app.open_document(document.id)
    if 'markdown-preview' in selected:
        app.show_documents(destination='home')
        await check('markdown-preview')
    if 'text-editor' in selected:
        app.show_documents(edit=True, destination='home')
        await check('text-editor')
    app.show_home()


async def _readers(app, fixtures, selected, check):
    from commonUtils.runtime.resources.documents import LocalDocuments
    app.show_home()
    for path, name in zip(fixtures.books, ('epub', 'comic')):
        if name not in selected:
            continue
        store = app.reader_manager().catalog.library_store
        book = store.import_book(LocalDocuments(), path)
        await app.open_book(book['id'])
        if name == 'comic':
            app.readers.active.set_reading_mode(False)
        await check(name)
        app.show_home()


async def _provider_text(app, fixtures, selected, check):
    from commonUtils.runtime.resources.local import LocalFiles
    from features.text_editor.resources import LocalTextCopies
    app.show_home()
    assert await app.open_crypt(copies=LocalTextCopies(LocalFiles(fixtures.root / 'Child')), key='Note.md')
    if 'provider-markdown' in selected:
        await check('provider-markdown')
    if 'provider-text-editor' in selected:
        app.private_sessions.active.toggle_private_preview()
        await check('provider-text-editor')
    app.show_home()


async def _provider_epub(app, fixtures, selected, check):
    from types import SimpleNamespace
    from commonUtils.runtime.resources.local import LocalFiles
    from services.documents.readers import PrivateReader
    app.show_home()
    epub, _ = fixtures.books
    folder = epub.parent
    def open_archive(key, **kwargs):
        reader = PrivateReader(key, (folder / key).read_bytes())
        reader.key = key
        return reader
    copies = SimpleNamespace(root=folder, provider=LocalFiles(folder),
                             encrypted=False, offline=True, open=open_archive)
    assert await app.open_crypt(copies=copies, key=epub.name), app.cloud_status.value
    if 'provider-epub' in selected:
        await check('provider-epub')
    if 'provider-epub-find' in selected:
        owner = app.private_sessions.active
        owner.show_provider_epub_find()
        await check('provider-epub-find')
        owner.provider_epub_view.close_find()
    app.show_home()


async def _notes(app, fixtures, selected, check):
    from commonUtils.runtime.resources.local import LocalFiles
    from mobile.obsidian import open_vault
    app.show_home()
    vault = await open_vault(app, LocalFiles(fixtures.root), 'Child', destination='home')
    if 'notes-library' in selected:
        await check('notes-library')
    if 'notes-article' in selected:
        await vault.open_note('Child/Note.md')
        await check('notes-article')


async def _documentation(app, fixtures, selected, check):
    from mobile.documentation_ui import show_documentation
    from .web_checks import wait_for_text
    app.show_settings()
    wiki = fixtures.root / 'Wiki'
    wiki.mkdir(exist_ok=True)
    page = wiki / 'docs.md'
    page.write_text('# Rotation guide\n\nRetain the current help page.')
    reader = show_documentation(app, wiki, page)
    await wait_for_text(reader.web, 'Retain the current help page.')
    assert reader.path == page.resolve() and reader.history == [reader.path] and reader.history_index == 0
    await check('documentation')


_SCENARIOS = {
    'workspaces': _workspaces, 'folders': _folders, 'home': _home,
    'documents': _documents, 'chat': _chat, 'settings': _settings,
    'connections': _connections, 'home-file-picker': _home_file_picker,
    'text': _text, 'readers': _readers, 'provider-text': _provider_text,
    'provider-epub': _provider_epub, 'notes': _notes, 'documentation': _documentation,
}


async def visit_screens(app, check, *, panels=None):
    """Run only required setup groups and require every selected screen once."""
    screens = select_screens(panels)
    selected = {screen.panel for screen in screens}
    visited = []
    async def checked(name):
        if name not in selected or name in visited:
            raise AssertionError('Unexpected or repeated rotation screen: ' + name)
        await check(name)
        visited.append(name)
    fixtures = _Fixtures(app)
    for group in dict.fromkeys(screen.group for screen in screens):
        await _SCENARIOS[group](app, fixtures, selected, checked)
    expected = [screen.panel for screen in screens]
    assert visited == expected, ('Incomplete rotation screen visit', expected, visited)
