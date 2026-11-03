"""Desktop favourites/recent projection and credential-aware resource reopening."""
from pathlib import Path
from types import SimpleNamespace
from commonUtils.ui import pyside as qt
from commonUtils.filesystem.storage import cache_directory
from services.documents.catalog import DocumentCatalog
from services.documents.credential_state import DesktopCredentialCipher


def catalog(*, recent=False):
    return DocumentCatalog(cache_directory(create=False), recent=recent)


def unlocked_ciphers():
    from features.rclone import session
    result, seen = [], set()
    for context in session.paths():
        cipher = DesktopCredentialCipher(SimpleNamespace(context=context))
        try:
            identity = cipher.identity
        except PermissionError:
            continue
        if identity not in seen:
            result.append(cipher)
            seen.add(identity)
    return result


def source_reference(path, provider=None):
    path = Path(path)
    cipher = None
    if provider is None or not getattr(provider, 'private', False):
        source = dict(type='local', path=str(path.resolve()))
    elif getattr(provider, 'connection', None) is not None:
        item = provider.connection
        source = dict(type='crypt', package=str(item.package), root=str(item.root),
                      remote=item.remote, path=provider.relative(path))
    elif getattr(provider, 'remote_storage', False):
        source = dict(type='remote', config=str(provider.config_path), remote=provider.remote,
                      path=provider.relative(path))
    else:
        raise ValueError('This document has no reusable storage reference.')
    if provider is not None and getattr(provider, 'session_only', False):
        cipher = DesktopCredentialCipher(provider)
        cipher.identity  # Fail closed before any plaintext write.
    return source, cipher


def reference(window):
    from .location_context import document_location
    path, provider = document_location(window)
    if not path:
        raise ValueError('Save or open a file before adding it to favourites.')
    path = Path(path)
    source, cipher = source_reference(path, provider)
    opener = dict(editor=getattr(window, 'document_editor_id', '') or path.suffix.lower())
    from features.notes_library.ui.notes_library import NotesLibraryWindow
    if isinstance(window, NotesLibraryWindow):
        opener = dict(editor='notes', root=str((provider.root / window.library.root).resolve())
                      if source['type'] == 'local' else window.library.root)
    return source, path.name, opener, cipher


def relocate(provider, source, destination, *, deleted=None):
    source, cipher = source_reference(provider.root / (deleted or source), provider)
    target = None if deleted is not None else source_reference(provider.root / destination, provider)[0]
    for recent in (False, True):
        catalog(recent=recent).relocate(source, target, cipher=cipher)


def remember(window, *, favourite=False):
    source, title, opener, cipher = reference(window)
    catalog(recent=not favourite).remember(source, title, opener, favourite=favourite, cipher=cipher)


def favourite(window):
    try:
        remember(window, favourite=True)
    except (OSError, ValueError, PermissionError) as error:
        qt.QMessageBox.warning(window, 'Favourite file', str(error))


def provider_for(source):
    from commonUtils.runtime.resources.local import LocalFiles
    if source['type'] == 'local':
        path = Path(source['path'])
        return LocalFiles(path.parent), path.name
    from features.rclone.desktop_service import service
    if source['type'] == 'crypt':
        from features.rclone.localcrypt.mapping import Connection
        return service.localcrypt.open(Connection(Path(source['package']), source['remote'], Path(source['root']))), source['path']
    if source['type'] == 'remote':
        from features.rclone.remote_access import DesktopRemoteLocation
        return service.remotes.open(DesktopRemoteLocation(Path(source['config']), source['remote'])), source['path']
    raise ValueError('Unknown document source.')


def open_resource(provider, path, parent=None, *, editor=''):
    from commonUtils.runtime.resources.selection import ResourceChoice
    release = provider.acquire() if hasattr(provider, 'acquire') else lambda: None
    choice = ResourceChoice(provider, path, release)
    suffix = Path(path).suffix.lower()
    try:
        if suffix in {'.pdf', '.epub', '.cbz', '.zip'}:
            from services.documents.ui.readers import open_reader_choice
            return open_reader_choice(choice, parent, 'pdf' if suffix == '.pdf' else 'epub' if suffix == '.epub' else 'comic')
        if suffix == '.rmdoc':
            from services.documents.ui.notebooks import open_notebook_choice
            return open_notebook_choice(choice, parent)
        from features.video.formats import VIDEO_EXTENSIONS
        if suffix in VIDEO_EXTENSIONS:
            from features.video.ui.player import open_video_choice
            return open_video_choice(choice, parent)
        from features.images.document import IMAGE_EXTENSIONS
        if suffix in IMAGE_EXTENSIONS:
            from features.images.ui.viewer import open_image_choice
            return open_image_choice(choice, parent)
        from services.documents.ui.editors import open_editor_choice
        return open_editor_choice(choice, parent, markdown=editor != 'text' and suffix in {'.md', '.markdown'}, edit=False)
    except BaseException:
        choice.close()
        raise


def reopen(row, parent=None):
    try:
        if row['opener'].get('editor') == 'notes':
            from features.notes_library.ui.notes_library import open_notes
            if row['source']['type'] == 'local':
                from commonUtils.runtime.resources.local import LocalFiles
                library_root = Path(row['opener']['root'])
                factory = lambda: LocalFiles(library_root)
                path = Path(row['source']['path']).relative_to(library_root).as_posix()
                root = ''
            else:
                root = row['opener']['root']
                path = row['source']['path']
                factory = lambda: provider_for(row['source'])[0]
            window = open_notes(factory, row['title'], root=root)
            if window is None:
                return None
            def ready():
                if window.library is not None and not window.progress.busy:
                    window.idle.disconnect(ready)
                    window.open_note(path)
            if window.library is not None and not window.progress.busy:
                window.open_note(path)
            else:
                window.idle.connect(ready)
            return window
        provider, path = provider_for(row['source'])
        return open_resource(provider, path, parent, editor=row['opener'].get('editor', ''))
    except (OSError, ValueError, PermissionError) as error:
        qt.QMessageBox.warning(parent, 'Open document', str(error))


def populate(layout, parent, *, recent=False):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().hide()
            item.widget().deleteLater()
    try:
        store = catalog(recent=recent)
        rows = store.entries('recent' if recent else 'favourites', ciphers=unlocked_ciphers(), strict=False)
    except (OSError, ValueError, PermissionError):
        rows = []
    title = qt.QLabel('Recent' if recent else 'Favourites')
    title.setObjectName('sectionTitle')
    layout.addWidget(title)
    if 'store' in locals() and store.errors:
        layout.addWidget(qt.QLabel(store.errors[0]))
    if not rows:
        layout.addWidget(qt.QLabel('No recent files.' if recent else 'No favourite files.'))
    for row in rows:
        container = qt.QWidget()
        line = qt.QHBoxLayout(container)
        line.setContentsMargins(0, 0, 0, 0)
        button = qt.QPushButton(row['title'])
        button.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
        button.setToolTip(row['title'])
        button.clicked.connect(lambda checked=False, row=row: reopen(row, parent))
        line.addWidget(button, 1)
        if not recent:
            remove = qt.QToolButton()
            remove.setText('×')
            remove.setAccessibleName('Remove favourite ' + row['title'])
            def forget(checked=False, row=row):
                try:
                    cipher = next((value for value in unlocked_ciphers()
                        if any(item['id'] == row['id'] for item in catalog().read(value)['favourites'])), None)
                    catalog().remove(row['id'], cipher=cipher)
                    populate(layout, parent)
                except (OSError, ValueError, PermissionError) as error:
                    qt.QMessageBox.warning(parent, 'Remove favourite', str(error))
            remove.clicked.connect(forget)
            line.addWidget(remove)
        layout.addWidget(container)
