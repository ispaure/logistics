"""Open working files and carry merge review inputs through a Git save job."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path

from shiboken6 import isValid

from commonUtils.persistence.merge import merge_text
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor.merge import MergeDialog
from ...repository import Repository


class WorkingCopyCommands(qt.QObject):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self._editor_service = None

    def resolve_conflict(self, relative_path):
        view = self.view
        repository, snapshot = view.path, view.snapshot
        if view.busy or not repository or snapshot is None:
            return
        branch = snapshot.status.branch

        def read(runner):
            inputs = Repository(repository, runner).conflict_inputs(relative_path)
            return inputs, merge_text(inputs.base, inputs.left, inputs.right)

        def opened(payload):
            if view.path == repository and not view.closing:
                inputs, model = payload
                ConflictReview(view, repository, branch, inputs, model).show()

        view._job('Read merge inputs', read, opened)

    def edit_file(self, relative_path):
        view = self.view
        repository = view.path
        if view.busy or not repository:
            return
        root = repository.resolve()
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            view._message('The selected path is not a regular file within this repository.', error=True)
            return
        if view.working_file_opener and view.working_file_opener(path):
            return
        from features.application import registry
        if not registry.is_feature_enabled('text_editor'):
            view._message('Enable the Text Editor feature in Settings to edit files outside registered IDE projects.', error=True)
            return
        from features.text_editor.ui.service import editor_service
        service = editor_service()
        if self._editor_service is None:
            self._editor_service = service
            service.saved.connect(self._editor_saved)
        service.open(path)

    @qt.Slot(object)
    def _editor_saved(self, path):
        view = self.view
        repository = view.path
        if repository and Path(path).resolve().is_relative_to(repository.resolve()):
            view.refresh()


class ConflictReview(MergeDialog):
    def __init__(self, view, repository, branch, inputs, model):
        rebase = inputs.operation == 'rebase'
        super().__init__(
            model, view, apply=self._save, path=inputs.path,
            left_name='Index stage 2 — rebased onto' if rebase else 'Index stage 2 — current branch',
            right_name='Index stage 3 — commit being replayed' if rebase else 'Index stage 3 — incoming changes',
        )
        self.view = view
        self.repository = repository
        self.branch = branch
        self.inputs = inputs
        from services.editors.ui.fonts import bind_code_views
        bind_code_views(self)
        self.stage = qt.QCheckBox('Stage resolved file after saving', self)
        self.layout().insertWidget(1, self.stage)
        view.idle.connect(self._resume_after_save)

    def _save(self, text):
        view = self.view
        if not view.commands.dispatch('Save merge result', 'save_conflict', self.inputs, text,
                                      stage=self.stage.isChecked(), repository=self.repository,
                                      branch=self.branch, after=self._accept_saved):
            raise ValueError('Repository changed or is busy. Reopen the merge.')
        self.applying = True
        self.widget.setEnabled(False)
        self.stage.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.widget.status.setText('Saving merge result…')
        return False

    def _accept_saved(self, _result):
        if isValid(self):
            self.applying = False
            self.accept()

    @qt.Slot()
    def _resume_after_save(self):
        if self.applying:
            self.applying = False
            self.widget.setEnabled(True)
            self.stage.setEnabled(True)
            self._ready()
            self.widget.status.setText(self.view.status.text())
