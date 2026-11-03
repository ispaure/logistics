"""Library-scoped document tabs with independent editor and resource lifetimes."""
from pathlib import PurePosixPath
from shiboken6 import isValid
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspaces.scoped_tabs import ScopedTabBar
from .notes_library import NotesLibraryWindow
from ..navigation import PathChange


class LibraryTabs(qt.QStackedWidget):
    def __init__(self, owner, label):
        super().__init__()
        self.owner, self.label = owner, label
        self.documents, self.groups = {}, []
        self.retaining_groups = False
        self.splitter = qt.QSplitter()
        self.splitter.setChildrenCollapsible(False)
        self.addWidget(owner.welcome)
        self.addWidget(self.splitter)
        self.active_group = self.add_group()
        qt.QApplication.instance().focusChanged.connect(self.focus_changed)
        self.setCurrentWidget(owner.welcome)

    @property
    def current(self):
        return self.active_group.currentWidget() if self.active_group in self.groups else None

    def focus_changed(self, before, after):
        if after is None:
            return
        for child, record in self.documents.items():
            if after is child or child.isAncestorOf(after):
                if self.active_group is not record['group']:
                    self.activate(record['group'])
                return

    def parent_folder(self, child):
        if child.index < 0 or child.closing:
            return
        group = self.documents[child]['group']
        group.setCurrentWidget(child)
        self.activate(group)
        parent = str(PurePosixPath(self.path(child)).parent)
        self.owner.reveal_folder('' if parent == '.' else parent)

    def add_group(self, position=None):
        group = qt.QTabWidget()
        group.setMinimumWidth(240)
        group.setTabBar(ScopedTabBar(group, self.splitter, lambda: self.groups, self.move, self.can_move))
        group.setTabsClosable(True)
        group.tabCloseRequested.connect(lambda index: self.close_tab(group.widget(index)))
        group.currentChanged.connect(lambda index: self.activate(group))
        group.tabBar().setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        group.tabBar().customContextMenuRequested.connect(lambda point: self.menu(group, point))
        position = len(self.groups) if position is None else position
        self.groups.insert(position, group)
        self.splitter.insertWidget(position, group)
        self.splitter.setSizes([1] * len(self.groups))
        return group

    def path(self, child):
        return child.history[child.index] if child.index >= 0 else self.documents[child]['path']

    def activate(self, group):
        if group not in self.groups:
            return
        self.active_group = group
        child = group.currentWidget()
        if child in self.documents and not child.closing:
            self.owner.activate_document(child)

    def open(self, path, *, fragment='', remember=True, index=None, replace=False):
        if replace and self.current is not None:
            child = self.current
            if child.progress.busy or child.closing:
                return child
            if getattr(self.owner, 'edit_created', None) == path:
                child.edit_created, self.owner.edit_created = path, None
            if self.path(child) != path:
                child.open_note(path, fragment=fragment, remember=remember, index=index)
            elif fragment:
                child.viewer.browser.scrollToAnchor(fragment)
            return child
        for child in self.documents:
            if not child.closing and self.path(child) == path:
                group = self.documents[child]['group']
                self.active_group = group
                group.setCurrentWidget(child)
                self.owner.activate_document(child, remember=remember, index=index)
                if fragment:
                    child.viewer.browser.scrollToAnchor(fragment)
                return child
        provider = self.owner.provider
        child = NotesLibraryWindow(lambda provider=provider: provider, self.label,
                                   root=self.owner.library.root, document_only=True)
        child.setWindowFlags(qt.Qt.WindowType.Widget)
        for widget in (child.panel_tabs, child.links_tree, child.menu):
            widget.hide()
        child.up.clicked.disconnect()
        child.up.clicked.connect(lambda: self.parent_folder(child))
        self.owner.operation_footer.layout().addWidget(child.operation_footer, 1)
        child.open_card.hide()
        child.new_card.hide()
        child.viewer.new_action.triggered.disconnect()
        child.viewer.new_action.triggered.connect(self.owner.new_note)
        if getattr(self.owner, 'edit_created', None) == path:
            child.edit_created, self.owner.edit_created = path, None
        group = self.active_group
        self.documents[child] = dict(group=group, path=path,
                                     pending=(path, fragment, remember, index))
        child.idle.connect(lambda child=child: self.ready(child))
        child.document_saved.connect(lambda child=child: self.refresh_connections(exclude=child))
        child.destroyed.connect(lambda obj=None, child=child: self.detach(child))
        group.addTab(child, PurePosixPath(path).name)
        group.setCurrentWidget(child)
        self.setCurrentWidget(self.splitter)
        child.show()
        return child

    def refresh_connections(self, *, exclude=None):
        for child in self.documents:
            if child is not exclude and not child.progress.busy and not child.closing:
                child.refresh_connections()

    def ready(self, child):
        if child not in self.documents or not isValid(self.owner):
            return
        record = self.documents[child]
        for action in child.findChildren(qt.QAction):
            action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            if action is not child.save_action and qt.QKeySequence(qt.QKeySequence.StandardKey.Save) in action.shortcuts():
                action.setShortcuts([])
        pending = record['pending']
        if pending is not None and child.library is not None and not child.closing:
            record['pending'] = None
            path, fragment, remember, index = pending
            child.open_note(path, fragment=fragment, remember=remember, index=index)
            return
        if child.index >= 0 and not child.closing:
            record['path'] = self.path(child)
            group = record['group']
            group.setTabText(group.indexOf(child), PurePosixPath(record['path']).name)
        if child is self.current and not child.closing:
            self.owner.activate_document(child)
        if child.progress._result[1]:
            self.owner.pending_close = False
        elif self.owner.pending_close or self.owner.closing:
            qt.QTimer.singleShot(0, self.owner, self.owner.close)
        self.owner.idle.emit()

    def detach(self, child):
        record = self.documents.pop(child, None)
        if record is not None and isValid(child.operation_footer):
            self.owner.operation_footer.layout().removeWidget(child.operation_footer)
            child.operation_footer.hide()
            child.operation_footer.deleteLater()
        if record is None or not isValid(self) or not isValid(self.owner) or not isValid(self.owner.up):
            return
        group = record['group']
        if isValid(group):
            index = group.indexOf(child) if isValid(child) else -1
            if index >= 0:
                group.removeTab(index)
        self.trim_groups()
        if not self.documents and not self.owner.closing:
            self.owner.clear_document()
            self.setCurrentWidget(self.owner.welcome)
        elif self.documents and not self.retaining_groups:
            self.activate(self.active_group)

    def trim_groups(self):
        if self.retaining_groups:
            return
        for group in list(self.groups):
            if isValid(group) and not group.count() and len(self.groups) > 1:
                self.groups.remove(group)
                if self.active_group is group:
                    self.active_group = self.groups[0]
                group.hide()
                group.setParent(None)
                group.deleteLater()

    def close_tab(self, child, *, approved=False):
        if child not in self.documents or not isValid(child):
            return True
        if approved:
            child.closing = True
        if not child.prepare_close():
            return False
        child.close()
        self.detach(child)
        return True

    def close_all(self, *, approved=False):
        ready = True
        for child in list(self.documents):
            if not self.close_tab(child, approved=approved):
                ready = False
        return ready

    def can_leave(self):
        return all(child.closing or child.can_leave_document() for child in list(self.documents))

    def can_move(self, child, target, placement, index):
        return (child in self.documents and target in self.groups
                and (placement == 'tabs' or len(self.groups) < 3)
                and not (placement != 'tabs' and target.count() == 1 and target.widget(0) is child))

    def move(self, child, target, placement='tabs', index=None):
        if not self.can_move(child, target, placement, index):
            return False
        source = self.documents[child]['group']
        if placement != 'tabs':
            position = self.groups.index(target) + (placement == 'right')
            target = self.add_group(position)
        old_index = source.indexOf(child)
        title = source.tabText(old_index)
        source.removeTab(old_index)
        target.insertTab(target.count() if index is None else min(index, target.count()), child, title)
        self.documents[child]['group'] = target
        self.active_group = target
        target.setCurrentWidget(child)
        self.trim_groups()
        self.owner.activate_document(child)
        return True

    def menu(self, group, point):
        child = group.widget(group.tabBar().tabAt(point))
        if child is None:
            return
        menu = qt.QMenu(self)
        for placement in ('left', 'right'):
            action = menu.addAction('Move to new ' + placement + ' group',
                                    lambda checked=False, placement=placement: self.move(child, group, placement))
            action.setEnabled(self.can_move(child, group, placement, None))
        for number, target in enumerate(self.groups, 1):
            if target is not group:
                menu.addAction('Move to group ' + str(number), lambda checked=False, target=target: self.move(child, target))
        menu.addAction('Close tab', lambda: self.close_tab(child))
        menu.exec(group.tabBar().mapToGlobal(point))

    def remap(self, source, destination, deleted):
        change = PathChange(source, destination, deleted)

        for child in list(self.documents):
            current = self.path(child)
            if change.removes(current):
                self.close_tab(child, approved=True)
                continue
            # Preserve history occurrences and cursor, even when the same file
            # appears more than once or only an earlier visit was affected.
            child.history, index = change.history(child.history, child.index)
            child.index = index
            child.positions = change.positions(child.positions)
            path = change.remap(current)
            self.documents[child]['path'] = path
            group = self.documents[child]['group']
            group.setTabText(group.indexOf(child), PurePosixPath(path).name)
            child.back.setEnabled(index > 0)
            child.forward.setEnabled(0 <= index < len(child.history) - 1)
            if path != current and not child.progress.busy:
                child.open_note(path, remember=False, index=index)
        self.activate(self.active_group)


class TabbedNotesLibrary(NotesLibraryWindow):
    document_destination = 'notes_library'
    def __init__(self, factory, label, **kwargs):
        self.document_tabs = None
        super().__init__(factory, label, **kwargs)
        tabs = LibraryTabs(self, label)
        old = self.split.replaceWidget(1, tabs)
        old.hide()
        old.setParent(self)
        self.document_tabs = tabs
        self.viewer.status.clear()
        self.navigation.hide()
        self.controls_bar.hide()
        self.links_button.hide()
        self.navigation.set_shortcuts_enabled(False)
        self.save_action.setShortcuts([])
        self.resize(1200, 800)

    def open_note(self, path, *, remember=True, fragment='', index=None, resolve_link=False, new_tab=False):
        if self.document_tabs is None:
            return super().open_note(path, remember=remember, fragment=fragment, index=index, resolve_link=resolve_link)
        if self.progress.busy or self.library is None or self.locked or self.closing:
            return
        if resolve_link and self.document_tabs.current is not None:
            return self.document_tabs.current.open_note(path, fragment=fragment, resolve_link=True)
        try:
            path = self.library.contained(path)
        except ValueError as error:
            self.viewer.status.setText(str(error))
            return
        return self.document_tabs.open(path, fragment=fragment, remember=remember, index=index, replace=not new_tab)

    def activate_document(self, child, *, remember=True, index=None):
        for document in self.document_tabs.documents:
            document.operation_footer.setVisible(document is child)
        if child.index < 0:
            self.clear_document()
            self.idle.emit()
            return
        self.document_resource_path = child.document_resource_path
        self.document_provider = child.provider
        # The outer owner projects the focused document for shared library tools.
        # Switching tabs must never append to any document's history.
        self.history, self.index = list(child.history), child.index
        self.back.setEnabled(child.index > 0)
        self.forward.setEnabled(0 <= child.index < len(child.history) - 1)
        self.up.setEnabled(True)
        self.refresh_connections()
        self.idle.emit()

    def navigate(self, offset):
        if self.document_tabs is None:
            return super().navigate(offset)
        child = self.document_tabs.current
        if child is not None:
            child.navigate(offset)

    def parent_folder(self):
        if self.document_tabs is None:
            return super().parent_folder()
        child = self.document_tabs.current
        if child is not None:
            self.document_tabs.parent_folder(child)

    @property
    def document_saving(self):
        if self.document_tabs is None:
            return super().document_saving
        return any(child.document_saving for child in self.document_tabs.documents if not child.closing)

    def can_leave_document(self):
        return super().can_leave_document() if self.document_tabs is None else self.document_tabs.can_leave()

    def defer_after_save(self, callback):
        if self.document_tabs is None:
            return super().defer_after_save(callback)
        for child in self.document_tabs.documents:
            if child.document_saving:
                child.defer_after_save(callback)
                return

    def save_current_document(self):
        if self.document_tabs is None:
            return super().save_current_document()
        child = self.document_tabs.current
        return child.save_current_document() if child is not None and child.index >= 0 else False

    def mutate(self, *args, **kwargs):
        if self.document_tabs is not None and any(
                child.progress.busy and child.pending[0] == 'note'
                for child in self.document_tabs.documents):
            return
        deleted = kwargs.get('deleted')
        if self.document_tabs is not None and deleted and any(
                self.document_tabs.path(child) == deleted or
                self.document_tabs.path(child).startswith(deleted + '/')
                for child in self.document_tabs.documents):
            kwargs['leave'] = True
        super().mutate(*args, **kwargs)
        if self.document_tabs is not None and self.progress.busy:
            self.document_tabs.setEnabled(False)

    def completed(self, result, error):
        mutation = self.pending if self.pending[0] == 'mutation' else None
        super().completed(result, error)
        if self.document_tabs is not None and not self.locked:
            self.document_tabs.setEnabled(True)
            if mutation is not None and not error:
                self.document_tabs.remap(mutation[1], result.destination, mutation[2])
                self.document_tabs.refresh_connections()

    def clear_document(self):
        if self.document_tabs is None:
            return super().clear_document()
        self.document_resource_path = None
        self.document_provider = None
        self.history, self.index = [], -1
        for button in (self.back, self.forward, self.up):
            button.setEnabled(False)
        self.cancel_connections()
        self.links_tree.clear()

    def clear_content(self):
        if self.document_tabs is not None:
            for child in list(self.document_tabs.documents):
                child.retire()
        super().clear_content()

    def prepare_close(self):
        ready = super().prepare_close()
        if not ready or self.document_tabs is None:
            return ready
        return self.document_tabs.close_all(approved=True)
