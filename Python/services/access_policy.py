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


def display_allowed(*, inactive, captured, locked):
    return not (inactive or captured or locked)


def external_allowed(*, protected, inactive=False, captured=False):
    return not (protected or inactive or captured)


def speech_allowed(*, protected, inactive, captured, locked, continue_locked):
    if not protected:
        return True
    return not captured and (continue_locked or not (inactive or locked))
