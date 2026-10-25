"""Portable provider document preparation; dialogs and windows stay in ui/."""
from commonUtils.runtime.resources.selection import ResourceTextSession


def prepare_editor(choice, *, markdown=False, cancelled=lambda: False):
    session = ResourceTextSession.open(choice.provider, choice.path, max_bytes=(8 if markdown else 16) * 1024 * 1024, cancelled=cancelled)
    if markdown:
        from services.documents.markdown import prepare_markdown
        _, session.resources = prepare_markdown(choice.provider, choice.provider.root / choice.path,
                                                data=session.text.data, cancelled=cancelled)
    return session
