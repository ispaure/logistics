"""Adapt desktop credential generations to the host document protection port."""
from pathlib import Path
from . import session
from .desktop_credentials import SessionResumeProof, session_package


class DesktopDocumentProtection:
    def __init__(self, provider):
        self.provider = provider
        self._revoked = session.revocation_check(provider.context)

    def check(self):
        if self._revoked():
            raise ValueError('The credential session is locked. Reopen the document.')
        validate = getattr(self.provider, '_check_active', None)
        if validate is not None:
            validate()

    def on_revoke(self, callback):
        return session.on_forget(self.provider.context, callback)

    def affected_by(self, credentials):
        context = self.provider.context
        config = getattr(self.provider, 'config_path', None)
        return any(session.registry.depends_on(context, key)
                   or (config is not None and config == Path(key).with_suffix('.conf'))
                   for key in credentials)

    def resume_authorization(self):
        connection = getattr(self.provider, 'connection', None)
        package = getattr(connection, 'package', None)
        if package is None:
            package = session_package(getattr(self.provider, 'config_path', self.provider.context))
        return SessionResumeProof(Path(package) if package is not None else None)
