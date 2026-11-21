"""Portable provider document preparation; dialogs and windows stay in ui/."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.runtime.resources.selection import ResourceTextSession


def prepare_editor(choice, *, markdown=False, cancelled=lambda: False):
    session = ResourceTextSession.open(choice.provider, choice.path, max_bytes=(8 if markdown else 16) * 1024 * 1024, cancelled=cancelled)
    if markdown:
        from services.documents.markdown import prepare_markdown
        _, session.resources = prepare_markdown(choice.provider, choice.provider.root / choice.path,
                                                data=session.text.data, cancelled=cancelled)
    return session
