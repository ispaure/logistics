"""Memory-only resume challenges. Authentication never revives a provider grant."""
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
        self.reason = 'setup' if self.locked else None
        self.wifi_eligible = False
        self.revision = 0
        self._configuration_lock = Lock()

    def derive(self, password):
        return pbkdf2_hmac('sha256', password.encode('utf-8'), self.salt, 200_000)

    def lock(self, *, reason='explicit'):
        # Duplicate app/scene lifecycle callbacks describe the same challenge.
        # They must neither override a manual lock nor revive a rejected waiver.
        if reason == 'lifecycle' and self.locked:
            return
        self.locked = True
        self.reason = reason
        self.wifi_eligible = reason == 'lifecycle' and self.proof is not None
        self.revision += 1

    def authorize(self, revision):
        if self.revision != revision or self.proof is None:
            return False
        self.locked = False
        self.reason = None
        self.wifi_eligible = False
        return True

    def waive_lifecycle(self, revision):
        if self.reason != 'lifecycle' or not self.wifi_eligible:
            return False
        return self.authorize(revision)

    def deny_wifi(self, revision):
        if self.revision == revision:
            self.wifi_eligible = False

    def verify(self, password):
        return bool(password and self.proof is not None
                    and compare_digest(self.proof, self.derive(password)))

    def configure(self, password):
        with self._configuration_lock:
            if not password or self.proof is not None:
                return False
            self.proof = self.derive(password)
            return True

