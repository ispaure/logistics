"""Process-wide native credential publication and per-package privacy state.

Every mobile scene shares one instance. This feature policy is independent of
ctypes transport and widgets, so publication and identity resolution can be tested
without loading the native library.
"""
import weakref
from threading import RLock, local
from contextlib import contextmanager


class NativeCredentialState:
    def __init__(self):
        self.generation = 0
        self.observers = weakref.WeakSet()
        self.document_observers = weakref.WeakSet()
        self.session_privacy = None
        self.package_records = ()
        self.package_privacy = {}
        self.epoch = -1
        self.lock = RLock()
        self._publication_local = local()
        # Application composition subscribes its scope; credentials own no process policy.
        self.protection_observers = weakref.WeakSet()

    @contextmanager
    def publication(self, *, blocking=True):
        """Defer callbacks until the outermost credential/storage transaction ends."""
        from features.rclone.credential_loading import CredentialBusyError
        if not self.lock.acquire(blocking=blocking):
            raise CredentialBusyError()
        previous = getattr(self._publication_local, 'observers', None)
        observers = [] if previous is None else previous
        self._publication_local.observers = observers
        try:
            yield observers
        finally:
            self.lock.release()
            if previous is None:
                del self._publication_local.observers
                self.notify(observers)

    def privacy_gates(self):
        with self.lock:
            return tuple(dict.fromkeys(gate for gate in
                (*self.package_privacy.values(), self.session_privacy) if gate is not None))

    def package_remotes(self, label, fallback=()):
        return next((list(item['remotes']) for item in self.package_records
                     if item['package_name'] == label), list(fallback))

    def resolve_remote(self, name, identity, *, cipher=False):
        field = 'crypt_identities' if cipher else 'identities'
        candidates = []
        for item in self.package_records:
            aliases = item.get('aliases', {})
            hashes = item.get(field, {})
            for original, alias in aliases.items():
                if (identity is None or hashes.get(alias) == identity) and (name in (original, alias) or name.startswith(original + ' @ ')):
                    if alias == name:
                        return alias
                    candidates.append(alias)
        # Name-only history references share one remote across packages.
        if candidates and identity is None:
            return candidates[0]
        if len(set(candidates)) == 1:
            return candidates[0]
        return name  # Native identity checks refuse unavailable/ambiguous accounts.

    def publish(self, action, values, info):
        self.notify(self.commit(action, values, info))

    def commit(self, action, values, info):
        """Commit under the native publication lock; return observers for after unlock."""
        records = tuple(info.get('packages', ())) if isinstance(info, dict) else ()
        label = values.get('package_name') or ('Session network shares' if values.get('session_only') else 'Network shares')
        gate = None
        if action in {'import', 'add_smb'} and values.get('session_only'):
            from services.session_auth import ResumePassword
            gate = ResumePassword(values.get('password', ''), credential_name=label)
        with self.lock:
            epoch = info.get('epoch') if isinstance(info, dict) else None
            if epoch is not None and epoch <= self.epoch:
                return ()
            if epoch is not None:
                self.epoch = epoch
            if action == 'clear':
                self.package_privacy = {}
                self.package_records = ()
            else:
                self.package_records = records
                if action in {'import', 'add_smb'}:
                    if gate is not None:
                        self.package_privacy[label] = gate
                    else:
                        self.package_privacy.pop(label, None)
                if records or action == 'forget_package':
                    labels = {item['package_name'] for item in records if not item['saved']}
                    self.package_privacy = {name: gate for name, gate in self.package_privacy.items() if name in labels}
            self.session_privacy = next(iter(self.package_privacy.values()), None)
            self.generation += 1
            return (*tuple(self.protection_observers), *tuple(self.observers), *tuple(self.document_observers))

    def notify(self, observers):
        """Queue within a transaction, otherwise fan out after its outer lock exits."""
        pending = getattr(self._publication_local, 'observers', None)
        if pending is not None:
            pending.extend(observers)
            return
        failure = None
        for observer in observers:
            try:
                observer.credentials_changed()
            except Exception as error:
                if failure is None:
                    failure = error
        if failure is not None:
            raise failure
