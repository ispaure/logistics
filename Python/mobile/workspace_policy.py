"""Toolkit-independent selection of retained workspace documents."""
from dataclasses import dataclass
from collections.abc import Callable, Mapping
from typing import Any


def session_view(app, key):
    """Resolve an existing editable session; never create or mount a widget."""
    if key not in app.workspace.sessions:
        return None
    owner = app.text_views.get(key)
    if owner is not None:
        if owner.session.view.get('markdown_mode') == 'preview' and owner.preview_box is not None:
            return owner.preview_box
        return owner.document_view
    private = getattr(app, 'private_sessions', None)
    owner = private.controllers.get(key) if private else None
    if owner is not None and owner.crypt_reader is not None and owner.crypt_reader.editable:
        return owner.crypt_view
    return None


@dataclass
class WorkspaceSelection:
    pinned: str | None = None

    def focus(self, key: str, current: str | None, view_of: Callable[[str], Any]):
        if self.pinned == key and current != key and view_of(current) is not None:
            self.pinned = current

    def retire_unavailable(self, view_of: Callable[[str], Any]):
        if self.pinned is not None and view_of(self.pinned) is None:
            self.pinned = None

    def candidates(self, sessions: Mapping, current: str, view_of: Callable[[str], Any]):
        return tuple(key for key, session in sessions.items() if key != current
                     and (session.provider == 'managed-text' or view_of(key) is not None))
