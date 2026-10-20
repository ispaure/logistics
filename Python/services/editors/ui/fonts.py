"""One code point size for Logistics editor views; other appearance stays local."""

from commonUtils.ui.appearance.typography import point_size, setting_size
import logging
from configparser import Error as ConfigError
from weakref import WeakSet, ref

from shiboken6 import isValid
from features.text_editor.preferences import Preferences


class CodeFont:
    def __init__(self, preferences):
        self.preferences = preferences
        self.size = preferences.load()["font_size_int"]
        self.views = WeakSet()
        self.updating = False

    def bind(self, editor):
        if editor not in self.views:
            self.views.add(editor)
            weak_editor = ref(editor)
            if hasattr(editor, "zoom_changed"):
                editor.zoom_changed.connect(lambda: self.changed(weak_editor()))
        font = editor.font()
        font.setPointSizeF(point_size(self.size))
        editor.setFont(font)

    def changed(self, editor):
        if editor is not None and isValid(editor) and not self.updating:
            self.set_size(setting_size(editor.font()))

    def set_size(self, size, *, save=True, notify=True):
        size = max(7, min(24, round(size)))
        self.size = size
        self.updating = True
        try:
            for editor in tuple(self.views):
                if isValid(editor):
                    font = editor.font()
                    font.setPointSizeF(point_size(size))
                    editor.setFont(font)
                    # Refresh each Text Editor window's pending preference snapshot.
                    if notify and hasattr(editor, "zoom_changed"):
                        editor.zoom_changed.emit()
            if save:
                self.preferences.save({"font_size_int": size})
        except (OSError, ValueError, ConfigError) as error:
            logging.warning("Code font size could not be saved: %s", error)
        finally:
            self.updating = False


def code_font(path=None):
    from commonUtils.ui import pyside as qt

    app = qt.QApplication.instance()
    preferences = Preferences(path)
    if not preferences.custom:
        from commonUtils.ui.appearance.styling import styling

        return styling(app).code_font
    key = str(preferences.path.resolve())
    if not hasattr(app, "_logistics_code_fonts"):
        app._logistics_code_fonts = {}
    if key not in app._logistics_code_fonts:
        app._logistics_code_fonts[key] = CodeFont(preferences)
    return app._logistics_code_fonts[key]


def bind_code_views(widget, path=None):
    """Include code and unified text panes in consumer-owned review dialogs."""
    from commonUtils.ui import pyside as qt
    from commonUtils.ui.code_editor.widget import monospace_font

    shared = code_font(path)
    for editor in widget.findChildren(qt.QPlainTextEdit):
        if not hasattr(editor, "zoom_changed"):
            editor.setFont(monospace_font())
        shared.bind(editor)
