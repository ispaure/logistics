"""Application permission questions. Pure policy; no widgets or native queries."""
from services.documents.storage import document_sources


def session_only(provider):
    """Wrappers cannot relax an explicit source restriction.

    Providers declare credential retention at their boundary. Unknown private
    providers remain conservative; storage encryption alone is not a declaration.
    """
    for source in document_sources(provider):
        declared = getattr(source, 'session_only', None)
        if declared is True or (declared is None and getattr(source, 'private', False)):
            return True
    return False

