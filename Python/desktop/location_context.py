"""Desktop storage identity shared by document tabs and browser location rows."""
from dataclasses import dataclass
from pathlib import Path

from commonUtils.ui import pyside as qt


@dataclass(frozen=True)
class LocationContext:
    storage: str
    name: str = ''
    unlocked: bool = False
    session_only: bool = False
    locked: bool = False
    network: bool = False
    source_label: str = ''

    @property
    def suffix(self):
        session = ' (🕵️ Session-Only)' if self.session_only else ''
        return f'[{self.storage}: {self.name}{session}]'

    @property
    def status(self):
        parts = [self.source_label or ('Cloud' if self.storage == 'Remote' else 'Network' if self.network else 'Local')]
        if self.locked:
            parts.append('Locked')
        elif self.unlocked:
            parts.append('Unlocked')
        if self.name:
            parts.append(self.name)
        if self.session_only:
            parts.append('🕵️ Session-Only')
        return ' · '.join(parts)


class LocationCatalog(qt.QObject):
    changed = qt.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.roots = ()
        self._local_root = None

    def publish(self, sources):
        from services.folders.workspaces import local_entries
        self.roots = tuple((entry.local.path, entry.name) for entry in local_entries(sources))
        self.changed.emit()

    def local(self, path):
        path = Path(path).absolute()
        matches = [(Path(root).absolute(), name) for root, name in self.roots
                   if path == Path(root).absolute() or Path(root).absolute() in path.parents]
        if matches:
            return LocationContext('Local', max(matches, key=lambda item: len(item[0].parts))[1])
        if self._local_root is None:
            import config
            self._local_root = Path(config.LogisticsConfig(create_resources=False).path_remote_local).absolute()
        try:
            relative = path.relative_to(self._local_root)
        except ValueError:
            return LocationContext('Local')
        return LocationContext('Local', relative.parts[0] if relative.parts else '')


def location_catalog():
    app = qt.QApplication.instance()
    if not hasattr(app, '_logistics_location_catalog'):
        app._logistics_location_catalog = LocationCatalog(app)
    return app._logistics_location_catalog


def location_context(path, provider=None):
    if provider is not None:
        connection = getattr(provider, 'connection', None)
        if connection is not None:
            return LocationContext('Local', connection.remote, unlocked=True, session_only=True)
        if getattr(provider, 'remote_storage', False):
            # Buffer privacy is independent of credential persistence.
            return LocationContext('Remote', provider.remote,
                unlocked=bool(getattr(provider, 'encrypted', False)),
                session_only=bool(getattr(provider, 'session_only', False)),
                source_label=getattr(provider, 'storage_label', 'Cloud'))
    return location_catalog().local(path)


def document_location(window):
    """Read the active identity, including Save As and adjacent reader navigation."""
    guard = getattr(window, '_private_view_guard', None)
    if guard is not None and guard.locked:
        return None, None
    current = getattr(window, 'current', None)
    if current is not None and getattr(current, 'path', None):
        return current.path, None
    choice = getattr(window, 'choice', None)
    if choice is not None:
        return choice.provider.root / choice.path, choice.provider
    viewer = getattr(window, 'viewer', None)
    if viewer is not None and getattr(viewer, 'current_path', None):
        return viewer.current_path, getattr(getattr(viewer, 'storage', None), 'provider', None)
    book = getattr(getattr(window, 'reader', None), 'book', None)
    if book is not None:
        return book.path, book.source
    pages = getattr(window, 'pages', None)
    if pages is not None:
        return pages.path, getattr(pages.document, 'source', None)
    path = (getattr(window, 'document_resource_path', None) or window.windowFilePath()
            or getattr(getattr(window, 'editor', None), 'path', None))
    return path, getattr(window, 'document_provider', None)


def document_title(window, original=None):
    original = window.windowTitle() if original is None else original
    path, provider = document_location(window)
    if not path:
        return original
    context = location_context(path, provider)
    modified = ' *' if ' *' in original or window.isWindowModified() else ''
    suffix = (' (🕵️ Session-Only)' if context.session_only else
              f' {context.suffix}' if context.name and context.storage != 'Remote' else '')
    return f'{Path(path).name}{modified}{suffix}'


class BrowserLocationRow(qt.QWidget):
    """A source/state row just below the path; no virtual paths or credentials."""
    def __init__(self, browser, provider=None):
        super().__init__(browser)
        self.browser, self.provider = browser, provider
        row = qt.QHBoxLayout(self)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(6)
        self.icon = qt.QLabel()
        self.label = qt.QLabel()
        self.label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        row.addWidget(self.icon)
        row.addWidget(self.label, 1)
        browser.layout().insertWidget(1, self)
        signal = getattr(browser, 'directory_changed', None)
        if signal is None:
            signal = browser.views.directory_changed
        signal.connect(self.refresh)
        location_catalog().changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        context = location_context(self.browser.navigation.directory, self.provider)
        if self.provider is not None and getattr(self.provider, 'private', False):
            from features.rclone import session
            locked = (getattr(self.provider, 'closed', False)
                      or session.credentials(self.provider.context) is None)
            if locked:
                context = LocationContext(context.storage, locked=True, session_only=context.session_only,
                                          source_label=context.source_label)
        if self.provider is None:
            from commonUtils.filesystem.network import is_network_location
            if is_network_location(self.browser.navigation.directory):
                context = LocationContext('Local', context.name, network=True)
        from desktop.pages.workspace_icons import folder_icon
        icon = folder_icon(self, 'locked' if context.locked else 'unlocked' if context.unlocked else
                           'cloud' if context.storage == 'Remote' else None)
        self.icon.setPixmap(icon.pixmap(20, 20))
        self.label.setText(context.status)
        self.setAccessibleName('Storage location: ' + context.status)
        self.setToolTip(context.status + (' · Read-only' if context.storage == 'Remote' else ''))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == qt.QEvent.Type.PaletteChange and hasattr(self, 'label'):
            self.refresh()


def install_browser_location(browser, provider=None):
    row = BrowserLocationRow(browser, provider)
    browser.storage_location = row
    return row


class DocumentLocationRow(qt.QWidget):
    """Storage identity below the document tab, matching browser location rows."""
    def __init__(self, window, parent):
        super().__init__(parent)
        self.document = window
        row = qt.QHBoxLayout(self)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(6)
        self.icon, self.label = qt.QLabel(), qt.QLabel()
        self.label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        row.addWidget(self.icon)
        row.addWidget(self.label, 1)
        self.refresh()

    def refresh(self):
        path, provider = document_location(self.document)
        self.setVisible(bool(path))
        if not path:
            self.label.clear()
            return
        context = location_context(path, provider)
        from services.documents.storage import document_writable
        readonly = (getattr(self.document, 'document_read_only', False)
                    or not document_writable(provider))
        if getattr(self.document, 'document_editor_id', None) != 'text':
            readonly = readonly or getattr(self.document, 'read_only', False)
        from desktop.pages.workspace_icons import folder_icon
        icon = folder_icon(self, 'unlocked' if context.unlocked else
                           'cloud' if context.storage == 'Remote' else None)
        self.icon.setPixmap(icon.pixmap(20, 20))
        text = context.status + (' · (Read-Only)' if readonly else '')
        self.label.setText(text)
        self.setAccessibleName('Storage location: ' + text)
        self.setToolTip(text)
