"""Editor command discovery and globally shared shortcut preferences."""
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
from commonUtils.ui import pyside as qt
from commonUtils.ui.command_palette import CommandPalette, ShortcutDialog, validate_shortcut, shortcut_text


class CommandControls:
    def _build_command_controls(self):
        self.action(self._view_menu, "command_palette", "Find Command…", self.command_palette, "Ctrl+Shift+P")
        self.action(self._view_menu, "shortcuts", "Configure Shortcuts…", self.configure_shortcuts)
        self.shortcut_defaults = {key: shortcut_text(action) for key, action in self.actions.items()}
        self.shortcut_path = self.preferences.path.with_name("shortcuts.json")
        try:
            overrides = json.loads(self.shortcut_path.read_text())
            self._apply_shortcuts(overrides)
        except (OSError, ValueError, TypeError):
            pass

    def _apply_shortcuts(self, overrides):
        if not isinstance(overrides, dict):
            raise ValueError("Invalid shortcut preferences.")
        proposed = {key: overrides.get(key, value) for key, value in self.shortcut_defaults.items()}
        # Validate the complete mapping, including swaps, before changing live actions.
        temporary = {}
        for key, value in proposed.items():
            if not isinstance(value, str):
                raise ValueError("Invalid shortcut preferences.")
            action = qt.QAction(self)
            action.setShortcut(qt.QKeySequence(value))
            temporary[key] = action
        try:
            for key, value in proposed.items():
                validate_shortcut(temporary, key, value)
        finally:
            for action in temporary.values():
                action.deleteLater()
        for key, value in proposed.items():
            self.actions[key].setShortcut(qt.QKeySequence(value))

    def _save_shortcuts(self, overrides):
        # Validate first; persistence failure leaves current bindings intact.
        before = {key: shortcut_text(action) for key, action in self.actions.items()}
        self._apply_shortcuts(overrides)
        staging = None
        try:
            self.shortcut_path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile("w", encoding="utf-8", dir=self.shortcut_path.parent, delete=False) as stream:
                staging = Path(stream.name)
                json.dump(overrides, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staging, self.shortcut_path)
        except OSError:
            self._apply_shortcuts(before)
            raise
        finally:
            if staging and staging.exists():
                staging.unlink()
        for window in tuple(self.service.windows):
            if window is not self and hasattr(window, "shortcut_defaults"):
                window._apply_shortcuts(overrides)

    def command_palette(self):
        CommandPalette(self.actions, self).exec()

    def configure_shortcuts(self):
        ShortcutDialog(self.actions, self.shortcut_defaults, self._save_shortcuts, self).exec()
