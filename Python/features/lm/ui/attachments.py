"""Project attachment selection and bounded draft publication for desktop LM."""
from pathlib import Path
from typing import Protocol, Any

from commonUtils.ui import pyside as qt
from ..project_tools import ProjectTools


class AttachmentHost(Protocol):
    client: Any
    mode: Any
    project_picker: Any
    composer: Any
    status: Any

    def context_projects(self) -> dict: ...
    def context_buffers(self, project) -> tuple: ...


class AttachmentController:
    def __init__(self, page: AttachmentHost):
        self.page = page

    def attachment_context(self):
        page = self.page
        if page.client.busy or page.mode.currentData() != 'code':
            raise ValueError('Select Code mode to attach project context.')
        project = page.context_projects().get(page.project_picker.currentData())
        if project is None:
            raise ValueError('Choose a registered IDE project first.')
        buffers, selections = page.context_buffers(project)
        return ProjectTools(project, buffers), selections

    def append_attachment(self, text):
        page = self.page
        draft = page.composer.toPlainText()
        combined = draft + ('\n\n' if draft else '') + text
        if len(combined.encode('utf-8')) > 65536:
            raise ValueError('Attached context and draft are limited to 64 KiB. Attach a smaller selection or let the model read relevant lines.')
        page.composer.setPlainText(combined)
        page.composer.moveCursor(qt.QTextCursor.MoveOperation.End)

    def attach_files(self):
        page = self.page
        try:
            tools, _ = self.attachment_context()
            paths, _ = qt.QFileDialog.getOpenFileNames(page, 'Attach project text files', str(tools.root))
            attachments = []
            for path in paths:
                supplied = Path(path).absolute()
                # Accept OS aliases for the project root (e.g. /var on macOS),
                # preserving every component below it for link/exclusion checks.
                anchor = next((parent for parent in reversed(supplied.parents)
                               if parent.resolve() == tools.root), None)
                if anchor is None:
                    raise ValueError('Attachments must stay inside the selected project.')
                relative = supplied.relative_to(anchor).as_posix()
                text, source = tools.text(relative)
                attachments.append(f'Project file: {relative} ({source})\n```\n{text}\n```')
            if attachments:
                self.append_attachment('\n\n'.join(attachments))
        except (ValueError, OSError, UnicodeError) as error:
            page.status.setText(str(error))

    def attach_selection(self):
        page = self.page
        try:
            tools, selections = self.attachment_context()
            selections = [entry for entry in selections if self.selection_allowed(tools, entry[0])]
            if not selections:
                raise ValueError('Select code in an open editor in this IDE project first.')
            if len(selections) == 1:
                selected = selections[0]
            else:
                labels = [f'{path}:{line}' for path, line, _ in selections]
                label, accepted = qt.QInputDialog.getItem(page, 'Attach IDE selection', 'Selection', labels, 0, False)
                if not accepted:
                    return
                selected = selections[labels.index(label)]
            path, line, text = selected
            self.append_attachment(f'IDE selection: {path}, starting at line {line}\n```\n{text}\n```')
        except (ValueError, OSError) as error:
            page.status.setText(str(error))

    @staticmethod
    def selection_allowed(tools, path):
        try:
            tools.path(path)
            return True
        except (ValueError, OSError):
            return False

