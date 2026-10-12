"""Logistics-owned document launch catalog, shared by all chooser surfaces."""
from features import registry
from features.contributions import DocumentLauncherContribution


def _open_markdown(parent):
    from commonUtils.ui import pyside as qt
    from commonUtils.ui.markdown.window import open_markdown
    path, _ = qt.QFileDialog.getOpenFileName(parent, 'Open Markdown', '',
                                            'Markdown (*.md *.markdown);;All files (*)')
    return open_markdown(path, allow_edit=True) if path else None


def _new_markdown(parent):
    from commonUtils.ui.markdown.window import open_markdown
    return open_markdown(None, allow_edit=True)


def document_launchers():
    """Core Markdown plus enabled feature registrations, in declared order."""
    entries = [DocumentLauncherContribution('markdown', 'Markdown Editor', _open_markdown,
               'markdown', 20, _new_markdown, 'Write and preview formatted notes.')]
    entries.extend(entry.contribution for entry in registry.get_document_launchers())
    return {entry.editor_id: entry for entry in sorted(entries, key=lambda entry: entry.order)}
