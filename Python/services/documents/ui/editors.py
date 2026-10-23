"""Logistics Open/Save browser catalog and private document handoffs."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice
from commonUtils.runtime.platform import get_os, OS
from commonUtils.ui.resources.picker import choose_resource, ResourceTaskDialog

_windows = []


def choose_editor_resource(parent, mode, provider=None, name='', *, markdown=False, extensions=None, directory=None):
    from features.rclone.localcrypt.backend import connections
    from features.rclone.desktop_service import service
    from features.rclone.localcrypt.ui.views import ensure_session
    from services.local_storage import install_local_storage_policy
    install_local_storage_policy()
    locations = []
    if provider is not None:
        locations.append(('Current storage', lambda: (provider, provider.acquire() if hasattr(provider, 'acquire') else lambda: None)))
    local_root = Path.home().anchor
    locations.append(('Local files', lambda: (LocalFiles(local_root), lambda: None)))
    if get_os() is OS.WIN:
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            drive = Path(letter + ':/')
            if drive.exists() and str(drive) != local_root:
                locations.append((str(drive), lambda drive=drive: (LocalFiles(drive), lambda: None)))
    for item in connections():
        if item == getattr(provider, 'connection', None):
            continue
        def factory(item=item):
            if not ensure_session(item.context, package=item.package, parent=parent):
                raise ValueError('Unlock this storage to browse it.')
            backend = service.localcrypt.open(item)
            try:
                return backend, backend.acquire()
            except BaseException:
                backend.close()
                raise
        locations.append((f'LocalCrypt · {item.remote} · {item.package.name}', factory))
    if directory is None:
        directory = '' if provider else Path.home().relative_to(local_root).as_posix()
    return choose_resource(locations, parent=parent, mode=mode, name=name,
                           extensions=extensions if extensions is not None else (('.md', '.markdown') if markdown else ()), directory=directory)


def retain(window):
    _windows.append(window)
    window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
    from commonUtils.ui.document_host import show_document
    show_document(window)
    return window


def make_private_editor(choice, session, *, markdown=False, edit=True):
    if markdown:
        from features.rclone.localcrypt.ui.views import MarkdownStorage, PrivateMarkdownWindow
        def open_link(path, fragment=''):
            linked = ResourceChoice(choice.provider, choice.provider.relative(path),
                                    choice.provider.acquire() if hasattr(choice.provider, 'acquire') else lambda: None)
            open_editor_choice(linked, window, markdown=True, edit=False)
        storage = MarkdownStorage(choice.provider, choice.provider.root / choice.path, session.text.data,
                                  getattr(session, 'resources', {}), open_link)
        window = PrivateMarkdownWindow(storage.path, storage, edit=edit)
        window.destroyed.connect(choice.close)
    else:
        from commonUtils.ui.resources.editor import ResourceTextWindow
        window = ResourceTextWindow(choice, session, choose_editor_resource, open_editor_choice)
    from services.documents.ui.private_views import protect_private_view
    protect_private_view(window, choice.provider)
    return retain(window)


def open_editor_choice(choice, parent=None, *, markdown=False, fragment='', edit=True):
    """Load on a worker without putting a decrypted buffer in a persistent editor."""
    edit = bool(edit or qt.QApplication.keyboardModifiers() & qt.Qt.KeyboardModifier.AltModifier)
    loading = ResourceTaskDialog(parent, 'Opening document')
    progress = loading.operation
    def completed(session, error):
        try:
            if error:
                choice.close()
                qt.QMessageBox.warning(parent, 'Open', error)
            else:
                window = make_private_editor(choice, session, markdown=markdown, edit=edit)
                if markdown and fragment:
                    window.viewer.browser.scrollToAnchor(fragment)
        except Exception as error:
            choice.close()
            qt.QMessageBox.warning(parent, 'Open', str(error))
        finally:
            loading.accept()
            loading.deleteLater()
    progress.completed.connect(completed)
    loading.show()
    progress.start(lambda report, cancelled: prepare_editor(choice, markdown=markdown, cancelled=cancelled),
                   message='Opening session-only document…')
    return loading


from services.documents.preparation import prepare_editor


def markdown_action(viewer, mode):
    owner = getattr(viewer, "document_window", viewer.window())
    choice = choose_editor_resource(owner, mode, name=viewer.current_path.name if viewer.current_path else 'document.md', markdown=True)
    if not choice:
        return False
    if mode == 'open':
        if getattr(choice.provider, 'private', False):
            open_editor_choice(choice, owner, markdown=True)
            return False
        path = choice.provider.root / choice.path
        choice.close()
        return viewer.open_document(path)
    if not getattr(choice.provider, 'private', False):
        path = choice.provider.root / choice.path
        choice.close()
        return viewer.save_document(path)
    try:
        data = viewer.capture_save()
    except Exception as error:
        choice.close()
        qt.QMessageBox.warning(owner, 'Save As', str(error))
        return False
    def completed():
        viewer.editor.document().setModified(False)
        viewer.formatted_editor.document().setModified(False)
        viewer.new_document()
        from commonUtils.ui.document_host import close_document
        close_document(owner)
    return publish_handoff(choice, data, owner, markdown=True, completed=completed)


def publish_handoff(choice, data, parent, *, markdown=False, completed=lambda: None, before=lambda: None):
    from commonUtils.runtime.resources.mutations import save_resource_and_reopen
    dialog = ResourceTaskDialog(parent, 'Save As')
    operation = dialog.operation
    parent.setEnabled(False)
    def work(report, cancelled):
        before()
        def reopen():
            session = prepare_editor(choice, markdown=markdown)
            if session.text.data != data:
                raise ValueError('Saved document changed.')
            return session
        return save_resource_and_reopen(choice.provider, choice.path, data, reopen=reopen, cancelled=cancelled)
    def done(session, error):
        parent.setEnabled(True)
        transferred = False
        try:
            if error:
                choice.close()
                qt.QMessageBox.warning(parent, 'Save As', error)
            else:
                make_private_editor(choice, session, markdown=markdown)
                transferred = True
                completed()
        except Exception as error:
            if not transferred:
                choice.close()
            qt.QMessageBox.warning(parent, 'Save As', str(error))
        finally:
            dialog.accept()
            dialog.deleteLater()
    operation.completed.connect(done)
    dialog.show()
    operation.start(work, message='Saving verified copy…')
    return True


def open_linked_text(path, parent=None):
    from features.text_editor.ui.service import editor_service
    return editor_service().open(path)


def install_editor_dialogs():
    app = qt.QApplication.instance()
    if app:
        app._commonutils_markdown_resource_action = markdown_action
        app._commonutils_open_text_file = open_linked_text
