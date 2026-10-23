"""Isolated in-memory ownership for desktop rclone credential generations."""
import os
from pathlib import Path
import threading
import weakref
from uuid import uuid4


class CredentialSessions:
    """Own credential sets, child revocation and remembered package associations."""

    def __init__(self):
        self._lock = threading.RLock()
        self._sets = {}
        self._private = set()
        self._known_packages = {}
        self._parents = {}
        self._revocations = {}

    def on_forget(self, config_path, callback):
        """Observe one credential generation without keeping its owner alive."""
        path, token = Path(config_path), uuid4().hex
        reference = weakref.WeakMethod(callback)
        with self._lock:
            active = path in self._sets
            if active:
                self._revocations.setdefault(path, {})[token] = reference
        if not active:
            callback()
        def unsubscribe(*_):
            with self._lock:
                self._revocations.get(path, {}).pop(token, None)
        return unsubscribe

    def _forget_locked(self, path):
        callbacks = []
        for child, parent in tuple(self._parents.items()):
            if parent == path:
                callbacks.extend(self._forget_locked(child)[1])
        self._parents.pop(path, None)
        self._private.discard(path)
        removed = self._sets.pop(path, None) is not None
        callbacks.extend(self._revocations.pop(path, {}).values())
        return removed, callbacks

    def remember(self, config_path, values, *, package_path=None, private=False, parent=None):
        with self._lock:
            config_path = Path(config_path)
            if parent is not None:
                ancestor = Path(parent)
                if ancestor not in self._sets:
                    raise ValueError('The credential session is locked.')
                while ancestor is not None:
                    if ancestor == config_path:
                        raise ValueError('Credential sessions cannot depend on themselves or their descendants.')
                    ancestor = self._parents.get(ancestor)
            _, callbacks = self._forget_locked(config_path)
            if parent is not None:
                self._parents[config_path] = Path(parent)
            self._sets[Path(config_path)] = (uuid4().hex, values, Path(package_path) if package_path else None)
            if package_path:
                self._known_packages[Path(config_path)] = Path(package_path)
            if private:
                self._private.add(Path(config_path))
        _notify(callbacks)

    def names(self, config_path):
        with self._lock:
            entry = self._sets.get(Path(config_path))
            return sorted(entry[1]) if entry else None

    def paths(self):
        with self._lock:
            return [path for path in self._sets if path not in self._private]

    def forget(self, config_path):
        with self._lock:
            removed, callbacks = self._forget_locked(Path(config_path))
        _notify(callbacks)
        return removed

    def revocation_check(self, config_path):
        """Capture a generation; forgetting/reloading it permanently cancels its work."""
        path = Path(config_path)
        with self._lock:
            entry = self._sets.get(path)
            identity = entry[0] if entry else None
        def revoked():
            with self._lock:
                current = self._sets.get(path)
                return identity is None or current is None or current[0] != identity
        return revoked

    def depends_on(self, context, parent):
        """Whether locking parent would retire this context, including itself."""
        context, parent = Path(context), Path(parent)
        with self._lock:
            while context is not None:
                if context == parent:
                    return True
                context = self._parents.get(context)
        return False

    def launch(self, config_path, source, destination):
        """Return process-private env and alias paths. Human names remain in UI."""
        with self._lock:
            item = self._sets.get(Path(config_path))
            if item is None:
                return None
            identity, values, _package = item
            aliases = {name: f'logistics_{identity}_{index}' for index, name in enumerate(values)}
            environment = {key: value for key, value in os.environ.items()
                           if not key.upper().startswith('RCLONE_CONFIG')}
            for name, options in values.items():
                for key, value in options.items():
                    if key == 'remote':
                        remote, colon, suffix = value.partition(':')
                        if colon and remote in aliases:
                            value = aliases[remote] + ':' + suffix
                    environment[f'RCLONE_CONFIG_{aliases[name].upper()}_{key.upper()}'] = value
            def translate(value):
                text = str(value)
                name, colon, suffix = text.partition(':')
                return aliases[name] + ':' + suffix if colon and name in aliases else value
            return environment, translate(source), translate(destination)

    def credentials(self, config_path):
        from copy import deepcopy
        with self._lock:
            item = self._sets.get(Path(config_path))
            return deepcopy(item[1]) if item else None

    def package_path(self, config_path):
        with self._lock:
            item = self._sets.get(Path(config_path))
            return item[2] if item else self._known_packages.get(Path(config_path))


def _notify(callbacks):
    failure = None
    for reference in callbacks:
        callback = reference()
        if callback is not None:
            try:
                callback()
            except Exception as error:
                if failure is None:
                    failure = error
    if failure is not None:
        raise failure
