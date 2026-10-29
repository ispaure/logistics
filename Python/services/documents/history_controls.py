"""Application-wide clearing of owned reader history; no credential access needed."""

from pathlib import Path
import json
from weakref import WeakSet

from commonUtils.persistence import atomic_write_json
from .credential_state import clear_positions, _io_lock

_libraries = WeakSet()
_recent = WeakSet()
_workspaces = WeakSet()


def clear_recent_files(root, *, mobile=False):
    root = Path(root)
    if mobile:
        from features.rclone.mobile.document_lists import clear_recent_cache

        clear_recent_cache(root / "CredentialDocumentLists")
        # Include unloaded scenes, not only the current window's models.
        paths = [
            root / "recent-documents.json",
            *root.glob("Scenes/*/recent-documents.json"),
            *root.glob("Workspaces/*/recent-documents.json"),
            *root.glob("Windows/*/recent-documents.json"),
        ]
        for recent in tuple(_recent):
            if recent.path.is_relative_to(root):
                recent.clear()
                paths.append(recent.path)
    else:
        paths = [
            root / owner / "recent.json"
            for owner in ("Readers", "TextEditor", "Books", "Comics")
        ]
    for path in set(paths):
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("Linked recent-file history was preserved.")
        if path.exists():
            atomic_write_json(path, [])


def clear_saved_positions(root, *, mobile=False):
    root = Path(root)
    with _io_lock:
        clear_positions(root)
        owners = ("Video",) if mobile else ("Video", "Books", "Comics")
        for owner in owners:
            directory = root / owner
            if directory.is_symlink():
                raise ValueError("Linked reading history was preserved.")
            for path in directory.glob("*.json"):
                if path.name in ("playback-settings.json", "recent.json"):
                    continue
                if len(path.stem) == 64 and all(
                    c in "0123456789abcdef" for c in path.stem
                ):
                    if path.is_symlink():
                        raise ValueError("Linked reading history was preserved.")
                    if owner == "Books":
                        data = json.loads(path.read_text())
                        for key in (
                            "path",
                            "position",
                            "location",
                            "chapter",
                            "chapters",
                        ):
                            data.pop(key, None)
                        atomic_write_json(path, data, max_bytes=128 * 1024)
                    else:
                        path.unlink()
        # Old remote-video checkpoint storage. Records contain positions only.
        directory = root / "Video" / "Remote"
        if directory.is_symlink():
            raise ValueError("Linked reading history was preserved.")
        for path in directory.glob("*.bin"):
            if path.is_symlink():
                raise ValueError("Linked reading history was preserved.")
            if len(path.stem) == 64 and all(c in "0123456789abcdef" for c in path.stem):
                path.unlink()
        if mobile:
            from mobile.workspace import VIEW_NUMBERS, MAX_MANIFEST

            for workspace in tuple(_workspaces):
                if workspace.path.is_relative_to(root):
                    for session in workspace.sessions.values():
                        session.view = {
                            key: value
                            for key, value in session.view.items()
                            if key not in VIEW_NUMBERS
                        }
                        session._discard_positions = True
                    workspace.save()
            paths = [root / "workspace.json", *root.glob("Windows/*/workspace.json")]
            for path in paths:
                if not path.exists():
                    continue
                if path.is_symlink() or path.parent.is_symlink():
                    raise ValueError("Linked workspace was preserved.")
                with path.open("rb") as stream:
                    raw = stream.read(MAX_MANIFEST + 1)
                if len(raw) > MAX_MANIFEST:
                    raise ValueError("Workspace is too large; it was preserved.")
                state = json.loads(raw)
                if (
                    not isinstance(state, dict)
                    or state.get("schema") != 1
                    or not isinstance(state.get("sessions"), list)
                ):
                    raise ValueError("Invalid workspace was preserved.")
                for entry in state["sessions"]:
                    if not isinstance(entry, dict) or not isinstance(
                        entry.get("view", {}), dict
                    ):
                        raise ValueError("Invalid workspace view state was preserved.")
                    entry["view"] = {
                        key: value
                        for key, value in entry.get("view", {}).items()
                        if key not in VIEW_NUMBERS
                    }
                atomic_write_json(path, state, max_bytes=MAX_MANIFEST)
            loaded = [
                library
                for library in tuple(_libraries)
                if library.root.is_relative_to(root)
            ]
            libraries = {library.root: library for library in loaded}
            directory = root / "Library"
            if directory.is_symlink():
                raise ValueError("Linked library metadata was preserved.")
            if directory.is_dir() and directory not in libraries:
                from mobile.library import LibraryStore

                libraries[directory] = LibraryStore(directory)
            for library in libraries.values():
                library.clear_positions()
            for library in loaded:
                with library._record_lock:
                    library._record_cache.clear()
                    library._record_cache_bytes = 0


class PositionLease:
    """A pre-clear open reader cannot republish its old checkpoint on close."""

    def __init__(self, root=None):
        if root is None:
            from commonUtils.filesystem.storage import cache_directory

            root = cache_directory(create=False)
        self.root = Path(root)
        self.generation = self.current()

    def current(self):
        try:
            return (self.root / "ReaderPositions/generation").read_text()[:64]
        except FileNotFoundError:
            return ""

    def valid(self):
        return self.current() == self.generation

    def publish(self, action):
        with _io_lock:
            if self.valid():
                return action()
