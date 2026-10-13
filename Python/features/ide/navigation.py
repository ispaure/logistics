"""Project navigation UI; snapshots enter workers and stale results are ignored."""
from pathlib import Path
from copy import deepcopy
from commonUtils.ui import pyside as qt
from .analysis import analyze, project_files


class Navigation:
    def init_navigation(self):
        self.history = []
        self.history_index = -1
        for label, callback, shortcut in [
            ('Find in project…', self.find_project, 'Ctrl+Shift+F'),
            ('Definition', lambda: self.query('definition'), 'F12'),
            ('Find usages…', lambda: self.query('usages'), 'Shift+F12'),
            ('Back', lambda: self.travel(-1), 'Alt+Left'),
            ('Forward', lambda: self.travel(1), 'Alt+Right'),
            ('Go to line…', self.go_line, 'Ctrl+L'),
            ('Go to file…', self.go_file, 'Ctrl+P'),
            ('Symbols…', lambda: self.query('symbols'), 'Ctrl+Shift+O'),
            ('Complete…', lambda: self.query('completion'), 'Ctrl+Space'),
            ('Documentation', lambda: self.query('help'), 'Shift+F1'),
            ('Comment / Uncomment', lambda: self.current.toggle_comment() if self.current else None, 'Ctrl+/')]:
            self.action(label, callback, shortcut)

    def eventFilter(self, watched, event):
        # Qt maps ControlModifier to Command on macOS, matching StandardKey.
        if event.type() == qt.QEvent.Type.MouseButtonPress and event.button() == qt.Qt.MouseButton.LeftButton and event.modifiers() & qt.Qt.KeyboardModifier.ControlModifier:
            doc = next((doc for doc in self.views() if hasattr(doc, 'viewport') and doc.viewport() is watched), None)
            if doc:
                doc.setTextCursor(doc.cursorForPosition(event.position().toPoint()))
                self.activate(self.group_for(doc))
                self.query('usages' if event.modifiers() & qt.Qt.KeyboardModifier.ShiftModifier else 'navigate')
                return True
        return super().eventFilter(watched, event)

    def query_link(self, doc, request):
        # Retain only the latest hover while this view has an analysis in flight.
        if getattr(doc, 'link_busy', False):
            doc.link_pending = request
            return
        doc.link_busy = True
        token, line, column = request
        project = deepcopy(self.project)
        code = doc.toPlainText()
        def valid():
            return (doc in self.views() and doc.link_token == token
                    and doc.path == token[0] and doc.document().revision() == token[1]
                    and doc.isVisible() and self.isVisible()
                    and all(getattr(self.project, key) == getattr(project, key)
                            for key in ('root_path', 'source_paths', 'python_interpreter', 'excluded_paths')))
        def done(result):
            if doc not in self.views():
                return
            doc.link_busy = False
            if valid():
                doc.show_link(token, any(Path(path).is_file() for path, *_ in result))
            pending = getattr(doc, 'link_pending', None)
            doc.link_pending = None
            if pending and pending[0] == doc.link_token:
                self.query_link(doc, pending)
        self.run(lambda: analyze(project, token[0], code, line, column), done,
                 lambda error: done([]))

    @staticmethod
    def place_view(view, *, position=None, line=None, column=0, scroll=None):
        """Apply a location to a specific view. Lines are 1-based, columns code points;
        absolute cursor positions and persisted positions use Qt UTF-16 units.
        """
        if line is not None:
            block = view.document().findBlockByNumber(max(0, line - 1))
            if block.isValid():
                offset = len(block.text()[:max(0, column)].encode('utf-16-le')) // 2
                position = block.position() + offset
        if position is not None:
            cursor = view.textCursor()
            cursor.setPosition(max(0, min(position, view.document().characterCount() - 1)))
            view.setTextCursor(cursor)
            view.centerCursor()
        if scroll is not None:
            view.verticalScrollBar().setValue(max(0, scroll))

    def navigate_to(self, path, *, group=None, position=None, line=None, column=0, scroll=None):
        # Apply to the view actually opened, not whichever tab is current when a
        # separate queued callback eventually runs.
        self.open_path(path, group=group, on_open=lambda view: self.place_view(
            view, position=position, line=line, column=column, scroll=scroll))

    def location(self):
        doc = self.current
        return (str(doc.path), doc.textCursor().position(), doc.verticalScrollBar().value(), self.group_for(doc)) if doc else None

    def remember(self):
        location = self.location()
        # A new jump from a historical location replaces the forward branch,
        # even when the source cursor has not moved.
        self.history = self.history[:self.history_index + 1]
        if location and (self.history_index < 0 or self.history[self.history_index] != location):
            self.history = self.history[:self.history_index + 1] + [location]
            self.history = self.history[-200:]
            self.history_index = len(self.history) - 1

    def travel(self, direction):
        if direction < 0 and (self.history_index < 0 or self.location() != self.history[self.history_index]):
            self.remember()
        index = self.history_index + direction
        if 0 <= index < len(self.history):
            self.history_index = index
            path, position, scroll, group = self.history[index]
            self.navigate_to(path, group=group if group in self.groups else None, position=position, scroll=scroll)

    def go_line(self):
        doc = self.current
        if doc:
            line, ok = qt.QInputDialog.getInt(self, 'Go to line', 'Line', 1, 1, doc.blockCount())
            if ok:
                self.remember()
                self.place_view(doc, line=line)

    def go_file(self):
        query, ok = qt.QInputDialog.getText(self, 'Go to file', 'Filename or relative path contains')
        if ok:
            project = deepcopy(self.project)
            def choose(files):
                if not files:
                    self.error('No matching files in the bounded project scan.')
                    return
                value, accepted = qt.QInputDialog.getItem(self, 'Go to file', 'Matches (up to 500)', files, 0, False)
                if accepted:
                    self.remember()
                    self.navigate_to(project.root / value)
            self.run(lambda: project_files(project, query, cancelled=self.cancelled), choose)

    def query(self, kind):
        doc = self.current
        if not doc or doc.path.suffix.lower() not in ('.py', '.pyi'):
            self.error('Python navigation requires a .py or .pyi file.')
            return
        cursor = doc.textCursor()
        line = cursor.blockNumber() + 1
        # Jedi columns count Unicode characters; QTextCursor counts UTF-16 units.
        prefix = cursor.block().text().encode('utf-16-le')[:cursor.positionInBlock() * 2]
        column = len(prefix.decode('utf-16-le'))
        code, revision, path = doc.toPlainText(), doc.document().revision(), doc.path
        position = cursor.position()
        project = deepcopy(self.project)
        self.status.setText('Analyzing Python…')
        def stale():
            return (doc not in self.views() or doc.document().revision() != revision
                    or self.current is not doc or doc.textCursor().position() != position or not self.isVisible()
                    or any(getattr(self.project, key) != getattr(project, key)
                           for key in ('root_path', 'source_paths', 'python_interpreter', 'excluded_paths')))
        def done(result):
            if stale():
                self.status.setText('Analysis result superseded by edits or focus changes.')
                return
            result_kind = kind
            previews = []
            if isinstance(result, dict):
                previews = result.get('previews', [])
                result_kind, result = result['kind'], result['targets']
            self.status.setText('Python analysis complete.')
            if result_kind == 'help':
                qt.QMessageBox.information(self, 'Python documentation', result or 'No documentation resolved.')
            elif result_kind == 'completion':
                labels = [entry[0] for entry in result]
                if not labels:
                    self.error('No completions resolved.')
                    return
                value, ok = qt.QInputDialog.getItem(self, 'Complete symbol', 'Completion', labels, 0, False)
                if ok and not stale():
                    doc.insertPlainText(result[labels.index(value)][1])
            elif result_kind == 'usages':
                from .usages import UsagePopup
                if not hasattr(self, 'usage_popup'):
                    self.usage_popup = UsagePopup(self)
                def choose(target):
                    if stale():
                        self.error('Usage result superseded by edits or focus changes.')
                        return
                    file, target_line, target_column, name = target
                    self.remember()
                    self.navigate_to(file, line=target_line, column=target_column)
                word = qt.QTextCursor(cursor)
                word.select(qt.QTextCursor.SelectionType.WordUnderCursor)
                self.usage_popup.present(doc, project, result, previews,
                                         word.selectedText() or 'symbol', choose)
            elif result:
                labels = [f'{name} — {file}:{line}' for file, line, column, name in result]
                selection = 0
                if len(result) > 1 or result_kind == 'symbols':
                    value, ok = qt.QInputDialog.getItem(self, 'Python targets', 'Target', labels, 0, False)
                    if not ok or stale():
                        return
                    selection = labels.index(value)
                file, target_line, target_column, name = result[selection]
                self.remember()
                self.navigate_to(file, line=target_line, column=target_column)
            else:
                self.error('No static usages found in this project.' if result_kind == 'usages' else
                           'No static definition resolved. Dynamic Python references may not be resolvable.')
        def resolve():
            result = analyze(project, path, code, line, column, kind)
            resolved_kind = result['kind'] if isinstance(result, dict) else kind
            if resolved_kind == 'usages':
                from .usages import usage_previews
                targets = result['targets'] if isinstance(result, dict) else result
                return {'kind': 'usages', 'targets': targets,
                        'previews': usage_previews(targets, path, code)}
            return result
        if hasattr(self, 'usage_popup'):
            self.usage_popup.hide()
        self.run(resolve, done)

    def find_project(self):
        from .find_files import FindFiles
        if getattr(self, 'project_find', None) is None:
            self.project_find = FindFiles(self)
        self.project_find.reveal()
