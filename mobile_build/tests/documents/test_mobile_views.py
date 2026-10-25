"""Document retirement is a shared policy without feature or GUI import coupling."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from services.documents.mobile_views import retire_webview


class MobileViewRetirementTests(unittest.TestCase):
    def test_service_import_has_no_feature_or_native_ui_side_effects(self):
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run([sys.executable, '-c',
            'import sys; import services.documents.mobile_views; '
            'assert not any(k.startswith(("features.", "toga", "PySide6")) for k in sys.modules)'],
            env=dict(os.environ, PYTHONPATH=str(root / 'Python')), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_private_view_detaches_and_clears_without_loading_a_replacement_document(self):
        events = []
        view = SimpleNamespace(_font_binding=SimpleNamespace(dispose=lambda: events.append('font')),
            parent=SimpleNamespace(remove=lambda value: events.append('detach')),
            clear_private_content=lambda: events.append('clear'), set_content=Mock())
        retire_webview(view)
        self.assertEqual(events, ['font', 'detach', 'clear'])
        view.set_content.assert_not_called()
