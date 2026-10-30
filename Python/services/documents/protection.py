"""Storage-neutral document protection capabilities, supplied by providers."""
from collections.abc import Callable, Iterable
from typing import Protocol
from services.session_auth import ResumePassword
from .storage import document_sources


class ResumeAuthorization(Protocol):
    password_gate: ResumePassword | None

    def verify(self, secret: str) -> bool: ...


class DocumentProtection(Protocol):
    """on_revoke returns an idempotent release; failed release must be retryable."""
    def check(self) -> None: ...
    def on_revoke(self, callback: Callable[[], None]) -> Callable[[], None]: ...
    def affected_by(self, credentials: Iterable[object]) -> bool: ...
    def resume_authorization(self) -> ResumeAuthorization: ...


def document_protections(provider):
    """Retain every wrapper's declared protection; an outer wrapper cannot relax it."""
    seen = set()
    for source in document_sources(provider):
        protection = getattr(source, 'document_protection', None)
        if protection is not None and id(protection) not in seen:
            seen.add(id(protection))
            yield protection


class TemporaryResumeAuthorization:
    """Documents without a credential proof require their own session password."""
    def __init__(self):
        self.password_gate = ResumePassword()

    def verify(self, secret):
        gate = self.password_gate
        return gate.configure(secret) if gate.proof is None else gate.verify(secret)
