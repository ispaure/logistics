"""Explicit New/Open launch choices must not open an editor on cancellation."""
import unittest
from unittest.mock import Mock, patch
from features.text_editor import contributions
from commonUtils.ui import pyside as qt


class TextLauncherTests(unittest.TestCase):
    def test_open_passes_selected_path_and_cancel_creates_no_service(self):
        parent = Mock()
        service = Mock()
        from pathlib import Path
        choice = Mock(path='notes.txt', provider=Mock(root=Path('/work'), private=False))
        with patch('services.editor_resources.choose_editor_resource', return_value=choice), patch.object(contributions, '_service', return_value=service):
            self.assertIs(contributions.launch(parent), service.open.return_value)
            service.open.assert_called_once_with(Path('/work/notes.txt'))
            choice.close.assert_called_once_with()
        with patch('services.editor_resources.choose_editor_resource', return_value=None), patch.object(contributions, '_service') as create:
            self.assertIsNone(contributions.launch(parent))
            create.assert_not_called()

    def test_new_constructs_a_blank_window_without_restoring_session(self):
        service = Mock()
        with patch.object(contributions, '_service', return_value=service), patch('features.text_editor.window.EditorWindow') as editor, patch('commonUtils.ui.document_host.show_document') as show:
            self.assertIs(contributions.new_document(Mock()), editor.return_value)
            editor.assert_called_once_with(service=service)
            show.assert_called_once_with(editor.return_value)
            service.open.assert_not_called()
