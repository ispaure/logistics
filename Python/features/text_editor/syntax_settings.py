"""Application syntax choices and persistence around shared editor infrastructure."""

from commonUtils.ui import pyside as qt
from configparser import Error as ConfigError
from commonUtils.ui.code_editor.widget import monospace_font
from commonUtils.ui.code_editor.syntax import (
    SyntaxHighlighter,
    LANGUAGES,
    detect_language,
)
from .preferences import Preferences


class SyntaxSettings:
    def _initialize_preferences(self, path=None):
        self.preferences = Preferences(path)
        self.options = self.preferences.load()
        self._preference_timer = qt.QTimer(self)
        self._preference_timer.setSingleShot(True)
        self._preference_timer.setInterval(300)
        self._preference_timer.timeout.connect(self._save_preferences)
        geometry = self.options.get("geometry_str", "")
        if geometry:
            try:
                self.restoreGeometry(qt.QByteArray.fromHex(geometry.encode("ascii")))
            except (ValueError, UnicodeError):
                pass

    def _build_syntax_controls(self):
        self.language_button = self._status_button(
            "Syntax language", self.choose_language
        )
        self.action(
            self._view_menu,
            "syntax",
            "Syntax Highlighting",
            self.toggle_syntax,
            checkable=True,
        )
        self.actions["syntax"].setChecked(self.options["syntax_highlighting_bool"])
        self.action(
            self._view_menu,
            "reset_preferences",
            "Reset Editor Preferences",
            self.reset_preferences,
        )

    def _configure_document(self, document):
        editor = document.editor
        editor.highlight_occurrences = not document.simple
        options = self.options
        font = (
            qt.QFont(options["font_family_str"])
            if options["font_family_str"]
            else monospace_font()
        )
        font.setPointSize(options["font_size_int"])
        editor.setFont(font)
        editor.indent_width = options["indent_width_int"]
        editor.use_tabs = options["use_tabs_bool"]
        editor.update_tab_width()
        editor.line_numbers = options["line_numbers_bool"]
        editor.update_gutter()
        editor.auto_indent = options["auto_indent_bool"]
        editor.auto_pairs = options["auto_pairs_bool"]
        editor.setLineWrapMode(
            qt.QPlainTextEdit.LineWrapMode.WidgetWidth
            if options["word_wrap_bool"] and not document.simple
            else qt.QPlainTextEdit.LineWrapMode.NoWrap
        )
        if options["whitespace_bool"]:
            option = editor.document().defaultTextOption()
            option.setFlags(
                option.flags()
                | qt.QTextOption.Flag.ShowTabsAndSpaces
                | qt.QTextOption.Flag.ShowLineAndParagraphSeparators
            )
            editor.document().setDefaultTextOption(option)
        document.language = detect_language(document.path, editor.toPlainText()[:256])
        if not hasattr(document, "highlighter"):
            document.highlighter = SyntaxHighlighter(editor)
            editor.zoom_changed.connect(self._preferences_changed)
        editor.folding.configure(document.language)
        editor.folding.rebuild()
        document.highlighter.configure(
            document.language
            if options["syntax_highlighting_bool"] and not document.simple
            else "text"
        )

    def choose_language(self):
        if not self.current:
            return
        from pygments.lexers import get_all_lexers

        choices = {label: alias for label, alias in LANGUAGES}
        for name, aliases, _, _ in get_all_lexers():
            if aliases:
                choices.setdefault(name, aliases[0])
        names = ["Plain Text"] + sorted(
            name for name in choices if name != "Plain Text"
        )
        value, ok = qt.QInputDialog.getItem(
            self,
            "Syntax Language",
            "Highlighting does not modify the file:",
            names,
            0,
            False,
        )
        if ok:
            self.current.language = choices[value]
            self.current.editor.folding.configure(self.current.language)
            self.current.editor.folding.rebuild()
            self.current.highlighter.configure(
                self.current.language
                if self.options["syntax_highlighting_bool"] and not self.current.simple
                else "text"
            )
            self._active_changed()

    def toggle_syntax(self):
        self.options["syntax_highlighting_bool"] = self.actions["syntax"].isChecked()
        for doc in self.documents:
            doc.highlighter.configure(
                doc.language
                if self.options["syntax_highlighting_bool"] and not doc.simple
                else "text"
            )
        self._preference_timer.start()

    def _preferences_changed(self):
        if not self.current:
            return
        editor = self.current.editor
        self.options.update(
            font_family_str=editor.font().family(),
            font_size_int=round(editor.font().pointSizeF()),
            indent_width_int=editor.indent_width,
            use_tabs_bool=editor.use_tabs,
            word_wrap_bool=editor.lineWrapMode()
            != qt.QPlainTextEdit.LineWrapMode.NoWrap,
            line_numbers_bool=editor.line_numbers,
            whitespace_bool=bool(
                editor.document().defaultTextOption().flags()
                & qt.QTextOption.Flag.ShowTabsAndSpaces
            ),
            auto_indent_bool=editor.auto_indent,
            auto_pairs_bool=editor.auto_pairs,
        )
        self._preference_timer.start()

    def _save_preferences(self):
        try:
            self.preferences.save(self.options)
        except (OSError, ValueError, ConfigError) as error:
            self.statusBar().showMessage(
                f"Preferences could not be saved: {error}", 7000
            )

    def reset_preferences(self):
        try:
            self.preferences.path.unlink(missing_ok=True)
        except OSError as error:
            self.show_error(error)
            return
        self._preference_timer.stop()
        self.options = self.preferences.load()
        for doc in self.documents:
            self._configure_document(doc)
        self.actions["syntax"].setChecked(self.options["syntax_highlighting_bool"])
        self._active_changed()
