"""Memory-only resume authentication; never persist passwords or verifiers."""
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from secrets import token_bytes
from threading import Lock


class ResumePassword:
    def __init__(self, password='', *, credential_name=''):
        self.credential_name = credential_name
        self.salt = token_bytes(16)
        self.proof = self.derive(password) if password else None
        self.locked = self.proof is None
        self.revision = 0
        self._configuration_lock = Lock()

    def derive(self, password):
        return pbkdf2_hmac('sha256', password.encode('utf-8'), self.salt, 200_000)

    def lock(self):
        self.locked = True
        self.revision += 1

    def verify(self, password):
        return bool(password and self.proof is not None
                    and compare_digest(self.proof, self.derive(password)))

    def configure(self, password):
        with self._configuration_lock:
            if not password or self.proof is not None:
                return False
            self.proof = self.derive(password)
            return True


def remote_privacy_gate(client, remote, identity=None, *, cipher=False):
    """Bind private views to their owning package, never the first loaded account.

    The caller retains this gate for the view's lifetime, including unsaved drafts
    after credential revocation. Older isolated test clients have only one gate.
    """
    state = getattr(client, 'credential_state', None)
    if state is None:
        return getattr(client, 'session_privacy', None)
    with state.lock:
        remote = state.resolve_remote(remote, identity, cipher=cipher)
        field = 'crypt_identities' if cipher else 'identities'
        for record in state.package_records:
            if (remote in record.get('remotes', ())
                    and (identity is None or record.get(field, {}).get(remote) == identity)):
                if record.get('saved'):
                    return None
                gate = state.package_privacy.get(record['package_name'])
                if gate is None:
                    raise ValueError('This credential session has no password gate. Lock and reload its package.')
                return gate
    raise ValueError('The credential package is no longer available. Unlock it again.')
