"""Editor commands and status controls; native text navigation remains Qt-owned."""

from commonUtils.ui import pyside as qt
from commonUtils.text_files import ENCODINGS
from commonUtils.ui.code_editor.search import SearchPanel


class EditingCommands:
    def _build_editing(self, layout):
        self.search = SearchPanel(self)
        layout.insertWidget(layout.count() - 1, self.search)
        self.search.idle.connect(self.idle)
        self.search.idle.connect(self._search_idle)
        menu = qt.QMenu("&Search", self)
        self.menuBar().insertMenu(self._view_menu.menuAction(), menu)
        for key, label, callback, shortcut in [
            (
                "find",
                "Find…",
                lambda: self.search.open(),
                qt.QKeySequence.StandardKey.Find,
            ),
            ("replace", "Replace…", lambda: self.search.open(True), "Ctrl+H"),
            ("find_next", "Find Next", self.search.find, "F3"),
            (
                "find_previous",
                "Find Previous",
                lambda: self.search.find(-1),
                "Shift+F3",
            ),
            ("goto", "Go to Line / Column…", self.go_to, "Ctrl+G"),
        ]:
            self.action(menu, key, label, callback, shortcut)
        for key, label, callback, shortcut in [
            (
                "duplicate",
                "Duplicate Line / Selection",
                lambda: self.edit("duplicate"),
                "Ctrl+D",
            ),
            (
                "delete_line",
                "Delete Line",
                lambda: self.edit("delete_line"),
                "Ctrl+Shift+K",
            ),
            (
                "move_up",
                "Move Lines Up",
                lambda: self.current.editor.move_lines(-1) if self.current else None,
                "Alt+Up",
            ),
            (
                "move_down",
                "Move Lines Down",
                lambda: self.current.editor.move_lines(1) if self.current else None,
                "Alt+Down",
            ),
            (
                "comment",
                "Toggle Line Comment",
                lambda: self.edit("toggle_comment"),
                "Ctrl+/",
            ),
            (
                "indent",
                "Indent",
                lambda: self.current.editor.indent() if self.current else None,
                None,
            ),
            (
                "unindent",
                "Unindent",
                lambda: self.current.editor.indent(True) if self.current else None,
                None,
            ),
        ]:
            self.action(self._edit_menu, key, label, callback, shortcut)
        tools = self.menuBar().addMenu("&Tools")
        for language in ("json", "xml"):
            for operation in ("format", "validate"):
                self.action(tools, operation + "_" + language,
                            operation.title() + " " + language.upper(),
                            lambda language=language, operation=operation:
                            self.structured_text(language, operation))
        transforms = self._edit_menu.addMenu("Text Transformations")
        for key, label in [
            ("sort", "Sort Lines Ascending"), ("sort_reverse", "Sort Lines Descending"),
            ("unique", "Remove Duplicate Lines"), ("trim", "Trim Trailing Whitespace"),
            ("upper", "UPPERCASE"), ("lower", "lowercase"), ("title", "Title Case"),
            ("tabs_to_spaces", "Tabs to Spaces"), ("spaces_to_tabs", "Leading Spaces to Tabs"),
            ("number", "Number Lines…"),
        ]:
            self.action(transforms, "transform_" + key, label,
                        lambda key=key: self.transform_text(key))
        for key, label in [
            ("wrap", "Word Wrap"),
            ("numbers", "Line Numbers"),
            ("whitespace", "Show Whitespace"),
            ("auto_indent", "Automatic Indentation"),
            ("auto_pairs", "Auto-close Brackets / Quotes"),
        ]:
            self.action(
                self._view_menu,
                key,
                label,
                lambda key=key: self.toggle_option(key),
                checkable=True,
            )
        self.action(self._view_menu, "font", "Choose Font…", self.choose_font)
        self.action(
            self._view_menu,
            "zoom_in",
            "Increase Font Size",
            lambda: self.zoom(1),
            qt.QKeySequence.StandardKey.ZoomIn,
        )
        self.action(
            self._view_menu,
            "zoom_out",
            "Decrease Font Size",
            lambda: self.zoom(-1),
            qt.QKeySequence.StandardKey.ZoomOut,
        )
        self.escape = qt.QShortcut(qt.QKeySequence("Escape"), self)
        self.escape.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape.activated.connect(self.search.close_panel)
        self.encoding_button = self._status_button("Encoding", self.choose_encoding)
        self.endings_button = self._status_button("Line endings", self.choose_endings)
        self.indent_button = self._status_button("Indentation", self.choose_indentation)
        self._active_changed()

    def _status_button(self, name, callback):
        button = qt.QToolButton()
        button.setAutoRaise(True)
        button.setAccessibleName(name)
        button.clicked.connect(callback)
        self.statusBar().addPermanentWidget(button)
        return button

    def _search_idle(self):
        if self._close_pending and not self.task.busy:
            self._close_pending = False
            self.close()

    def go_to(self):
        if not self.current:
            return
        value, ok = qt.QInputDialog.getText(
            self, "Go to Line / Column", "Line[:column], starting at 1:"
        )
        if not ok:
            return
        try:
            parts = value.split(":")
            line = int(parts[0])
            column = int(parts[1]) if len(parts) == 2 else 1
            if (
                len(parts) > 2
                or line < 1
                or line > self.current.editor.blockCount()
                or column < 1
            ):
                raise ValueError()
            block = self.current.editor.document().findBlockByNumber(line - 1)
            offset = len(block.text()[: column - 1].encode("utf-16-le")) // 2
            cursor = qt.QTextCursor(block)
            cursor.setPosition(block.position() + offset)
            self.current.editor.setTextCursor(cursor)
            self.current.editor.setFocus()
        except ValueError:
            self.show_error(
                "Enter an existing line and a positive column, such as 12:4."
            )

    def toggle_option(self, key):
        if not self.current:
            return
        editor = self.current.editor
        enabled = self.actions[key].isChecked()
        if key == "wrap":
            editor.setLineWrapMode(
                qt.QPlainTextEdit.LineWrapMode.WidgetWidth
                if enabled
                else qt.QPlainTextEdit.LineWrapMode.NoWrap
            )
        elif key == "numbers":
            editor.line_numbers = enabled
            editor.update_gutter()
        elif key == "whitespace":
            option = editor.document().defaultTextOption()
            flags = option.flags()
            flag = (
                qt.QTextOption.Flag.ShowTabsAndSpaces
                | qt.QTextOption.Flag.ShowLineAndParagraphSeparators
            )
            option.setFlags(flags | flag if enabled else flags & ~flag)
            editor.document().setDefaultTextOption(option)
        else:
            setattr(editor, key, enabled)
        self._preferences_changed()

    def choose_font(self):
        if not self.current:
            return
        accepted, font = qt.QFontDialog.getFont(
            self.current.editor.font(), self, "Editor font"
        )
        if accepted:
            self.current.editor.setFont(font)
            self.current.editor.update_tab_width()
            self._preferences_changed()

    def zoom(self, direction):
        if self.current:
            self.current.editor.set_font_size(
                self.current.editor.font().pointSizeF() + direction
            )

    def choose_encoding(self):
        if not self.current or self.task.busy:
            return
        value, ok = qt.QInputDialog.getItem(
            self,
            "Output Encoding",
            "Convert on the next save (unrepresentable characters cause an error):",
            ENCODINGS,
            0,
            False,
        )
        if ok:
            self.current.encoding = value
            self.current.bom_override = b"" if value == "utf-8" else None
            self.current.editor.document().setModified(True)
            self._active_changed()

    def choose_endings(self):
        if not self.current or self.task.busy:
            return
        names = ["LF", "CRLF", "CR"]
        value, ok = qt.QInputDialog.getItem(
            self,
            "Line Endings",
            "Convert every line ending on the next save:",
            names,
            0,
            False,
        )
        if ok:
            self.current.newline_override = dict(zip(names, ["\n", "\r\n", "\r"]))[
                value
            ]
            self.current.editor.document().setModified(True)
            self._active_changed()

    def choose_indentation(self):
        if not self.current:
            return
        width, ok = qt.QInputDialog.getInt(
            self,
            "Indentation Width",
            "Columns per tab / indentation:",
            self.current.editor.indent_width,
            1,
            16,
        )
        if not ok:
            return
        mode, ok = qt.QInputDialog.getItem(
            self,
            "Indentation Mode",
            "Insert:",
            ("Spaces", "Tabs"),
            int(self.current.editor.use_tabs),
            False,
        )
        if ok:
            self.current.editor.indent_width = width
            self.current.editor.use_tabs = mode == "Tabs"
            self.current.editor.update_tab_width()
            self._preferences_changed()
            self._active_changed()

    def _editing_status(self, document):
        editor = document.editor
        cursor = editor.textCursor()
        selection = len(cursor.selectedText())
        preceding = cursor.block().text().encode('utf-16-le')[:cursor.positionInBlock() * 2]
        column = len(preceding.decode('utf-16-le', errors='ignore')) + 1
        self.position.setText(
            f"Ln {cursor.blockNumber() + 1}, Col {column} · {editor.blockCount():,} lines"
            + (f" · {selection:,} selected" if selection else "")
            + (" · Simple mode" if document.simple else "")
        )
        self.encoding_button.setText(
            document.encoding.upper() + (" BOM" if document.snapshot.bom else "")
        )
        endings = document.newline_override or document.snapshot.newline
        self.endings_button.setText(
            {
                "\n": "LF",
                "\r\n": "CRLF",
                "\r": "CR",
                "\u2028": "Unicode LS",
                "\u2029": "Unicode PS",
            }[endings]
            + (
                " mixed"
                if document.snapshot.mixed_endings and document.newline_override is None
                else ""
            )
        )
        self.indent_button.setText(
            ("Tabs" if editor.use_tabs else "Spaces") + f": {editor.indent_width}"
        )
        for key, value in [
            ("wrap", editor.lineWrapMode() != qt.QPlainTextEdit.LineWrapMode.NoWrap),
            ("numbers", editor.line_numbers),
            (
                "whitespace",
                bool(
                    editor.document().defaultTextOption().flags()
                    & qt.QTextOption.Flag.ShowTabsAndSpaces
                ),
            ),
            ("auto_indent", editor.auto_indent),
            ("auto_pairs", editor.auto_pairs),
        ]:
            with qt.QSignalBlocker(self.actions[key]):
                self.actions[key].setChecked(value)

    def _preferences_changed(self):
        pass

    def transform_text(self, command):
        if not self.current:
            return
        start = 1
        if command == "number":
            start, accepted = qt.QInputDialog.getInt(self, "Number Lines", "Starting number:", 1)
            if not accepted:
                return
        self.current.editor.transform(command, start=start)

    def structured_text(self, language, operation):
        from commonUtils.ui.code_editor.formatting import format_text, validate_text
        if not self.current:
            return
        editor = self.current.editor
        if editor.isReadOnly() and operation == "format":
            return
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(qt.QTextCursor.SelectionType.Document)
        text = cursor.selectedText().replace("\u2029", "\n")
        try:
            if operation == "validate":
                validate_text(text, language)
                self.statusBar().showMessage(language.upper() + " is valid", 5000)
            else:
                result = format_text(text, language, editor.indent_width)
                if text != result:
                    cursor.beginEditBlock()
                    cursor.insertText(result)
                    cursor.endEditBlock()
                    editor.setTextCursor(cursor)
        except Exception as error:
            self.show_error(error)
