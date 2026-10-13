"""Shared code size across feature views and isolated preference stores."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from features.code_font import code_font
from features.text_editor.preferences import Preferences


class CodeFontTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_size_propagates_and_preserves_other_preferences(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'preferences.ini'
            Preferences(path).save({'indent_width_int': 2})
            shared = code_font(path)
            editors = [CodeEdit() for _ in range(3)]
            for editor in editors:
                self.addCleanup(editor.deleteLater)
                shared.bind(editor)
                self.assertEqual(editor.font().pointSize(), 8)
            editors[0].set_font_size(18)
            self.assertEqual([editor.font().pointSize() for editor in editors], [18] * 3)
            self.assertEqual(Preferences(path).load()['font_size_int'], 18)
            self.assertEqual(Preferences(path).load()['indent_width_int'], 2)
            late = CodeEdit()
            self.addCleanup(late.deleteLater)
            shared.bind(late)
            self.assertEqual(late.font().pointSize(), 18)
            separate = CodeEdit()
            self.addCleanup(separate.deleteLater)
            code_font(Path(directory) / 'other.ini').bind(separate)
            self.assertEqual(separate.font().pointSize(), 8)

    def test_feature_views_and_review_panes_share_size(self):
        from commonUtils.persistence.text import read_text_file
        from commonUtils.ui.code_editor.diff import DiffDialog, compare_text
        from features.ide.documents import EditorDocument
        from features.git.ui.preview import Preview
        from features.text_editor.window import EditorWindow
        from features.code_font import bind_code_views
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'preferences.ini'
            with patch('features.code_font.Preferences', side_effect=lambda value=None: Preferences(value or path)):
                source = root / 'example.py'
                source.write_text('print(1)\n')
                ide = EditorDocument(read_text_file(source))
                preview = Preview()
                window = EditorWindow(history_path=root / 'recent.json', preferences_path=path)
                review = DiffDialog(compare_text('old', 'new'))
                bind_code_views(review)
                for widget in (ide, preview, window, review):
                    self.addCleanup(widget.deleteLater)
                text = window.current.editor
                self.assertEqual([e.font().pointSize() for e in (ide, text, preview.editor)], [8] * 3)
                ide.set_font_size(17)
                self.assertEqual([e.font().pointSize() for e in (ide, text, preview.editor)], [17] * 3)
                self.assertTrue(all(e.font().pointSize() == 17 for e in review.findChildren(qt.QPlainTextEdit)))
                window.reset_preferences()
                self.assertEqual([e.font().pointSize() for e in (ide, text, preview.editor)], [8] * 3)
                window._preference_timer.stop()
                window.close()

    def test_production_split_views_bind_shared_styling_controller(self):
        from features.text_editor.window import EditorWindow
        from commonUtils.ui.appearance.styling import styling
        with TemporaryDirectory() as directory:
            root = Path(directory)
            window = EditorWindow(history_path=root / 'recent.json', preferences_path=root / 'preferences.ini')
            self.addCleanup(window.deleteLater)
            preferences = window.preferences
            preferences.custom = False
            controller = styling().code_font
            original = controller.size
            try:
                with patch('features.code_font.Preferences', return_value=preferences):
                    controller.set_size(17, save=False)
                    window._configure_document(window.current)
                    window.split_document(qt.Qt.Orientation.Horizontal)
                views = window.current.views
                self.assertIn(views.primary, controller.views)
                self.assertIn(views.secondary, controller.views)
                self.assertEqual([editor.font().pointSize() for editor in (views.primary, views.secondary)], [17, 17])
                controller.set_size(14, save=False)
                self.assertEqual([editor.font().pointSize() for editor in (views.primary, views.secondary)], [14, 14])
            finally:
                controller.set_size(original, save=False)
                preferences.custom = True
                window._preference_timer.stop()
                window.close()
