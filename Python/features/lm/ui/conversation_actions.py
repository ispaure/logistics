"""LM workspace presentation and navigation, backed by an owned conversation session."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from commonUtils.ui import pyside as qt
from commonUtils.persistence import atomic_write_bytes, atomic_write_json
from ..domain import conversation, defaults
from ..storage import export_markdown


class ConversationActions:
    """Own conversation/folder mutations and their confirmation dialogs."""
    def __init__(self, page):
        self.page = page

    def conversation_menu(self, point):
        page = self.page
        item = page.list.itemAt(point)
        if item is None or page.client.busy:
            return
        page.list.setCurrentItem(item)
        key = item.data(0, qt.Qt.ItemDataRole.UserRole)
        menu = qt.QMenu(page.list)
        if key:
            if page.data is None or page.data['id'] != key:
                return  # Opening may have been refused by a lease or save conflict.
            for action in (page.pin_action, page.fork_action, page.rename_button, page.move_button,
                           page.export_button, page.delete_button):
                menu.addAction(action)
        else:
            menu.addAction('New conversation here', page.conversations.new_conversation)
            menu.addAction('New folder…', page.conversations.new_folder)
        menu.exec(page.list.viewport().mapToGlobal(point))


    def toggle_pin(self):
        page = self.page
        if page.client.busy or page.data is None or page.lease is None or not page.persist():
            return
        page.data['pinned'] = not page.data.get('pinned', False)
        page.dirty = True
        if page.persist():
            page.refresh(reveal_current=True)
        page.update_controls()


    def fork_conversation(self):
        page = self.page
        if page.client.busy or page.data is None or page.lease is None or not page.persist():
            return
        from ..domain import now
        fork = deepcopy(page.data)
        fork.update(id=uuid4().hex, revision=0, title=(fork['title'] + ' (fork)')[:200],
                    pinned=False, created=now(), updated=now())
        for entry in fork['messages']:
            entry['id'] = uuid4().hex
        try:
            page.session.create(fork)
        except (OSError, ValueError) as error:
            page.status.setText(str(error))
            return
        page.restore()
        page.search.clear()
        page.refresh(reveal_current=True)
        page.status.setText('Conversation forked. The original is unchanged.')


    def move_tree_item(self, source, destination):
        page = self.page
        if page.client.busy or not page.persist():
            return
        key, folder = source
        try:
            if key:
                active = page.data is not None and page.data['id'] == key
                data = page.data if active else page.store.load(key)
                page.store.move(data, destination, lease=page.lease if active else None)
            else:
                moved_folder = page.store.move_folder(folder, destination, active=page.data, lease=page.lease)
        except (OSError, ValueError) as error:
            page.status.setText(str(error))
            return
        page.refresh(reveal_current=True)
        if not key and moved_folder in page.folder_items:
            page.list.setCurrentItem(page.folder_items[moved_folder])
        page.status.setText('Moved to ' + (destination or '/') + '.')


    def new_folder(self):
        page = self.page
        if page.client.busy:
            return
        parent = page.selected_folder()
        name, accepted = qt.QInputDialog.getText(page, 'New conversation folder',
            'Folder name (use / for multiple nested levels)')
        if not accepted or not name:
            return
        path = '/'.join(part for part in (parent, name) if part)
        try:
            page.store.create_folder(path)
        except (OSError, ValueError) as error:
            page.status.setText(str(error))
            return
        page.search.clear()
        page.refresh()
        page.list.setCurrentItem(page.folder_items[path])
        page.status.setText(f'Folder created: {path}. New conversations will be saved here.')


    def move_conversation(self):
        page = self.page
        if page.client.busy or not page.data or not page.persist():
            return
        try:
            choices = ['/', *page.store.folders()]
        except (OSError, ValueError) as error:
            page.status.setText(str(error))
            return
        current = page.data.get('folder') or '/'
        destination, accepted = qt.QInputDialog.getItem(page, 'Move conversation',
            'Destination folder (/ for root; use / for nested levels)', choices,
            choices.index(current) if current in choices else 0, True)
        if not accepted:
            return
        try:
            page.store.move(page.data, '' if destination == '/' else destination, lease=page.lease)
        except (OSError, ValueError) as error:
            page.status.setText(str(error))
            return
        page.refresh(reveal_current=True)
        page.update_controls()
        page.status.setText(f'Conversation moved to {destination or "/"}.')


    def new_conversation(self):
        page = self.page
        if page.client.busy or not page.persist():
            return
        data = conversation(defaults(), page.profile.currentData() or '', page.model.currentText())
        data['folder'] = page.selected_folder()
        data['mode'] = page.mode.currentData()
        data['project_id'] = page.project_picker.currentData() or ''
        try:
            page.session.create(data)
        except (OSError, ValueError) as error:
            page.status.setText(str(error))
            return
        page.restore()
        page.search.clear()
        page.refresh(reveal_current=True)
        page.update_controls()
        page.composer.setFocus()


    def rename(self):
        page = self.page
        if page.client.busy or not page.data:
            return
        title, accepted = qt.QInputDialog.getText(page, 'Rename conversation', 'Title', text=page.data['title'])
        if accepted and title.strip():
            page.data['title'] = title.strip()[:200]
            page.dirty = True
            page.persist()


    def delete(self):
        page = self.page
        if page.client.busy or not page.data or not page.persist():
            return
        if qt.QMessageBox.question(page, 'Delete conversation', 'Permanently delete this saved conversation?',
                                  qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                                  qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Yes:
            return
        try:
            page.store.delete(page.data)
        except (OSError, ValueError) as error:
            page.status.setText(str(error))
            return
        page.release_lease()
        page.data = None
        page.draft_images = []
        page.refresh_draft_images()
        page.loading = True
        page.composer.clear()
        page.loading = False
        page.refresh()
        page.render()
        page.update_controls()


    def export(self):
        page = self.page
        if not page.data:
            return
        # Export is also available after save/conflict failures, without overwriting the source.
        page.data['draft'] = page.composer.toPlainText()
        page.data['draft_images'] = deepcopy(page.draft_images)
        path, chosen = qt.QFileDialog.getSaveFileName(page, 'Export conversation', page.data['id'] + '.md',
                                                     'Markdown (*.md);;JSON (*.json)')
        if not path:
            return
        try:
            if Path(path).resolve().is_relative_to(page.store.root.resolve()):
                raise ValueError('Choose an export destination outside the LM storage folder.')
            if 'JSON' in chosen:
                atomic_write_json(path, page.data)
            else:
                atomic_write_bytes(path, export_markdown(page.data).encode('utf-8'))
        except (OSError, ValueError) as error:
            page.status.setText(f'Export failed: {error}')
            return
        page.status.setText(f'Conversation exported to {path}')

