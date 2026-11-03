"""Library-scoped document tabs with independent editor and resource lifetimes."""
from pathlib import PurePosixPath
from shiboken6 import isValid
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspaces.scoped_tabs import ScopedTabBar
from .notes_library import NotesLibraryWindow


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
        if child in self.documents and child.index >= 0 and not child.closing:
            self.owner.activate_document(child)

    def open(self, path, *, fragment='', remember=True, index=None):
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
        for widget in (child.panel_tabs, child.links_tree, child.menu, child.back,
                       child.forward, child.up, child.links_button):
            widget.hide()
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
        child.destroyed.connect(lambda obj=None, child=child: self.detach(child))
        group.addTab(child, PurePosixPath(path).name)
        group.setCurrentWidget(child)
        self.setCurrentWidget(self.splitter)
        child.show()
        return child

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
            record['history'] = remember, index
            child.open_note(path, fragment=fragment)
            return
        if child.index >= 0 and not child.closing:
            record['path'] = self.path(child)
            group = record['group']
            group.setTabText(group.indexOf(child), PurePosixPath(record['path']).name)
            if child is self.current:
                remember, index = record.pop('history', (True, None))
                self.owner.activate_document(child, remember=remember, index=index)
        if child.progress._result[1]:
            self.owner.pending_close = False
        elif self.owner.pending_close or self.owner.closing:
            qt.QTimer.singleShot(0, self.owner, self.owner.close)
        self.owner.idle.emit()

    def detach(self, child):
        record = self.documents.pop(child, None)
        if record is None:
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
        reopen, selected = [], self.current
        self.retaining_groups = True
        try:
            for child in list(self.documents):
                path = self.path(child)
                if deleted and (path == deleted or path.startswith(deleted + '/')):
                    self.close_tab(child, approved=True)
                elif source and (path == source or path.startswith(source + '/')):
                    reopen.append((destination + path[len(source):], self.documents[child]['group'], child is selected))
                    self.close_tab(child, approved=True)
            for path, group, was_selected in reopen:
                self.active_group = group
                child = self.open(path)
                if was_selected:
                    selected = child
            if selected in self.documents:
                self.active_group = self.documents[selected]['group']
                self.active_group.setCurrentWidget(selected)
        finally:
            self.retaining_groups = False
            self.trim_groups()


class TabbedNotesLibrary(NotesLibraryWindow):
    def __init__(self, factory, label, **kwargs):
        self.document_tabs = None
        super().__init__(factory, label, **kwargs)
        tabs = LibraryTabs(self, label)
        old = self.split.replaceWidget(1, tabs)
        old.hide()
        old.setParent(self)
        self.document_tabs = tabs
        self.save_action.setShortcuts([])
        self.resize(1200, 800)

    def open_note(self, path, *, remember=True, fragment='', index=None, resolve_link=False):
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
        return self.document_tabs.open(path, fragment=fragment, remember=remember, index=index)

    def activate_document(self, child, *, remember=True, index=None):
        if child.index < 0:
            return
        path = child.history[child.index]
        self.document_resource_path = child.document_resource_path
        self.document_provider = child.provider
        if index is not None:
            self.index = index
        elif remember and (self.index < 0 or self.history[self.index] != path):
            del self.history[self.index + 1:]
            self.history.append(path)
            self.index = len(self.history) - 1
        self.back.setEnabled(self.index > 0)
        self.forward.setEnabled(0 <= self.index < len(self.history) - 1)
        self.up.setEnabled(True)
        self.refresh_connections()
        self.idle.emit()

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
        if self.document_tabs is not None and self.document_tabs.current is not None:
            return self.document_tabs.current.save_current_document()
        return super().save_current_document()

    def mutate(self, *args, **kwargs):
        super().mutate(*args, **kwargs)
        if self.document_tabs is not None and self.progress.busy:
            self.document_tabs.setEnabled(False)

    def completed(self, result, error):
        mutation = self.pending if self.pending[0] == 'mutation' else None
        super().completed(result, error)
        if self.document_tabs is not None and not self.locked:
            self.document_tabs.setEnabled(True)
            if mutation is not None and not error:
                self.document_tabs.remap(mutation[1], result[0], mutation[2])

    def clear_document(self):
        if self.document_tabs is None:
            return super().clear_document()
        self.document_resource_path = None
        self.up.setEnabled(False)

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
