"""Process-wide native credential publication and per-package privacy state.

Every mobile scene shares one instance. This feature policy is independent of
ctypes transport and widgets, so publication and identity resolution can be tested
without loading the native library.
"""
import weakref
from threading import RLock


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
        self._protection = None

    @property
    def protection(self):
        # The feature-only Qt proof does not compose application services.
        with self.lock:
            if self._protection is None:
                from services.protection import ProtectionScope
                self._protection = ProtectionScope(self.privacy_gates)
            return self._protection

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
        records = tuple(info.get('packages', ())) if isinstance(info, dict) else ()
        label = values.get('package_name') or ('Session network shares' if values.get('session_only') else 'Network shares')
        gate = None
        if action in {'import', 'add_smb'} and values.get('session_only'):
            from .session_privacy import ResumePassword
            gate = ResumePassword(values.get('password', ''), credential_name=label)
        with self.lock:
            epoch = info.get('epoch') if isinstance(info, dict) else None
            if epoch is not None and epoch <= self.epoch:
                return
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
            failure = None
            for observer in (*tuple(self.observers), *tuple(self.document_observers)):
                try:
                    observer.credentials_changed()
                except Exception as error:
                    if failure is None:
                        failure = error
            if failure is not None:
                raise failure
