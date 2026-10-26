"""Presentation and lifecycle services injected into feature reader workflows."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class DocumentReadCapabilities:
    """Host session policy, independent of encryption and format presentation."""
    private: bool
    writable: bool
    credential_bound: bool
    offline: bool
    remote: bool = False
    required_feature: str | None = None


def reading_capabilities(copies):
    """Resolve adapter policy without letting wrappers grant remote writes."""
    from services.documents.storage import DocumentPolicy, document_sources, document_writable
    declared = getattr(copies, 'document_capabilities', None)
    sources = tuple(document_sources(copies))
    remote = any(getattr(source, 'remote_storage', False) for source in sources)
    policy = DocumentPolicy.for_provider(copies)
    if declared is None:
        # Compatibility for external/older adapters: unknown sessions remain
        # private and credential-bound until they declare their lifetime.
        provider = getattr(copies, 'provider', None)
        private = provider is None or not DocumentPolicy.for_provider(provider).persistent
        declared = DocumentReadCapabilities(private, True, private,
                                             getattr(copies, 'offline', False))
    remote = remote or declared.remote
    return DocumentReadCapabilities(
        private=declared.private or remote or not policy.persistent,
        writable=declared.writable and document_writable(copies) and not declared.remote,
        credential_bound=declared.credential_bound or remote,
        offline=declared.offline,
        remote=remote, required_feature=declared.required_feature)


def close_document_reader(reader):
    """Retire a reader acquired by an opening or retained by one session."""
    if reader is None:
        return
    try:
        pdf = getattr(reader, 'pdf', None)
        if pdf is not None:
            pdf.close()
    finally:
        try:
            source = getattr(reader, 'source', None)
            if hasattr(source, 'close'):
                source.close()
        finally:
            if hasattr(reader, 'password'):
                reader.password = ''


@dataclass(frozen=True)
class ReadingPresentation:
    seam: Callable[[Any], float | None]
    mode: Callable[[Any], str]
    layout_changed: Callable
    content_width: Callable[[str], int]
    private_label: Callable[[Any], str]
    speech_valid: Callable[[], bool]
    speech_presentation: object
    highlight_allowed: Callable[[], bool]
    comic_path: Callable
    notify_layout: Callable[[], None]
    themed_chapter: Callable

    seam_gap: Callable[[Any], float] = lambda view: 0
    page_region: Callable[[Any], tuple | None] = lambda view: None
    comic_boundary: Callable | None = None
    clear_comic_boundary: Callable = lambda: None
    comic_sharing: Callable[[], bool] = lambda: False
