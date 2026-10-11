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
        if not self.preferences.custom:
            self._settings_timer = qt.QTimer(self)
            self._settings_timer.setInterval(500)
            self._settings_timer.timeout.connect(self._reload_system_options)
            self._settings_timer.start()
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
        self.actions['syntax'].setVisible(False)
        self.action(
            self._view_menu,
            "reset_preferences",
            "Reset Editor Preferences",
            self.reset_preferences,
        )
        self.actions['reset_preferences'].setVisible(False)

    def _reload_system_options(self):
        options = self.preferences.load()
        if any(options[key] != self.options[key] for key in options if key != 'geometry_str'):
            self.options = options
            for document in self.documents:
                self._configure_document(document, preserve_language=True)
            self.actions['syntax'].setChecked(options['syntax_highlighting_bool'])
            self._active_changed()

    def _configure_editor(self, editor, simple):
        editor.highlight_occurrences = not simple
        options = self.options
        font = (
            qt.QFont(options["font_family_str"])
            if options["font_family_str"]
            else monospace_font()
        )
        font.setPointSize(options["font_size_int"])
        editor.setFont(font)
        from features.code_font import code_font
        code_font(self.preferences.font_path).bind(editor)
        editor.indent_width = options["indent_width_int"]
        editor.use_tabs = options["use_tabs_bool"]
        editor.update_tab_width()
        editor.line_numbers = options["line_numbers_bool"]
        editor.update_gutter()
        editor.auto_indent = options["auto_indent_bool"]
        editor.auto_pairs = options["auto_pairs_bool"]
        editor.setLineWrapMode(
            qt.QPlainTextEdit.LineWrapMode.WidgetWidth
            if options["word_wrap_bool"] and not simple
            else qt.QPlainTextEdit.LineWrapMode.NoWrap
        )
        option = editor.document().defaultTextOption()
        whitespace = (qt.QTextOption.Flag.ShowTabsAndSpaces |
                      qt.QTextOption.Flag.ShowLineAndParagraphSeparators)
        flags = option.flags() & ~whitespace
        option.setFlags(flags | whitespace if options["whitespace_bool"] else flags)
        editor.document().setDefaultTextOption(option)

    def _configure_document(self, document, *, preserve_language=False):
        if not preserve_language:
            document.language = detect_language(document.path, document.editor.toPlainText()[:256])
        if not hasattr(document, "highlighter"):
            document.highlighter = SyntaxHighlighter(document.editor)
            document.editor.zoom_changed.connect(self._preferences_changed)
        for editor in (document.views.primary, document.views.secondary):
            if editor is not None:
                self._configure_editor(editor, document.simple)
                editor.folding.configure(document.language)
                editor.folding.rebuild()
        document.highlighter.configure(
            document.language
            if self.options["syntax_highlighting_bool"] and not document.simple
            else "text"
        )
        self._sync_comment_prefix(document)

    def _sync_comment_prefix(self, document):
        prefix = document.views.primary.comment_prefix
        if document.views.secondary is not None:
            document.views.secondary.comment_prefix = prefix

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
            self._sync_comment_prefix(self.current)
            self.current.changed.emit()
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
        from features.code_font import code_font
        shared_font = code_font(self.preferences.font_path)
        if not shared_font.updating and shared_font.size != round(editor.font().pointSizeF()):
            shared_font.changed(editor)
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
            self.preferences.save(self.options if self.preferences.custom else {'geometry_str': self.options.get('geometry_str', '')})
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
        from features.code_font import code_font
        code_font(self.preferences.font_path).set_size(self.options['font_size_int'], save=False, notify=False)
        for doc in self.documents:
            self._configure_document(doc)
        code_font(self.preferences.font_path).set_size(self.options['font_size_int'], save=False)
        self.actions["syntax"].setChecked(self.options["syntax_highlighting_bool"])
        self._active_changed()
