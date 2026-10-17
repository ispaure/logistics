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
