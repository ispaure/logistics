"""Desktop feature catalog, launcher dispatch and retired-canvas event isolation."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from features import notebooks
from features.feature_runtime import FeatureRegistry


class NotebookDesktopTests(unittest.TestCase):
    def test_feature_contributes_page_launcher_and_browser_activation(self):
        runtime = FeatureRegistry(feature_loader=lambda: [notebooks])
        page, = runtime.get_pages()
        self.assertEqual((page.feature_name, page.contribution.page_id), ('notebooks', 'notebooks'))
        launcher, = runtime.get_document_launchers()
        self.assertEqual(launcher.contribution.editor_id, 'rmdoc')
        self.assertIs(launcher.contribution.new_document, notebooks.new_document)
        self.assertEqual(len(runtime.get_browser_extensions()), 1)
        self.assertEqual(notebooks.register().file_types[0].extensions, ('rmdoc',))

    def test_new_document_creates_a_notebook_and_open_launcher_keeps_library(self):
        from desktop.navigation.catalog import document_launchers, launch_document
        runtime = FeatureRegistry(feature_loader=lambda: [notebooks])
        launchers = document_launchers(runtime)
        window = Mock()
        with patch('features.notebooks.ui.workspace.open_workspace', return_value=window) as open_workspace:
            self.assertIs(launch_document(launchers, 'rmdoc', None), window)
            window.centralWidget.assert_not_called()
            self.assertIs(launch_document(launchers, 'rmdoc', None, new=True), window)
            window.centralWidget.return_value.new.assert_called_once_with()
            self.assertEqual(open_workspace.call_count, 2)

    def test_retired_canvas_cannot_edit_replacement_notebook_or_library(self):
        from features.notebooks.ui.workspace import NotebookWorkspace
        old, current = object(), object()
        owner = NS(web=NS(page=lambda: current), perform=Mock())
        NotebookWorkspace.deliver(owner, old, dict(op='delete-page'))
        owner.perform.assert_not_called()
        NotebookWorkspace.deliver(owner, current, dict(op='undo'))
        owner.perform.assert_called_once_with(dict(op='undo'))
        owner.perform.reset_mock()
        owner.web = None
        NotebookWorkspace.deliver(owner, current, dict(op='delete-page'))
        owner.perform.assert_not_called()
