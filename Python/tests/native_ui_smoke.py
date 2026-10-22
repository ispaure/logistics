"""Exercise the public application UI on the native Qt backend with private fixtures."""
import faulthandler
from contextlib import ExitStack
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


def phase(text):
    print('Native UI: ' + text, flush=True)


def main():
    faulthandler.enable()
    # Reuse cooperative Qt cleanup before removing fixture folders, especially
    # QFileSystemModel/watchers holding native directory handles on Windows.
    with ExitStack() as cleanup:
        directory = cleanup.enter_context(TemporaryDirectory(prefix='logistics-native-ui-'))
        root = Path(directory)
        browsing = root / 'files'
        browsing.mkdir()
        (browsing / 'example.txt').write_text('Native Qt startup fixture\n', encoding='utf-8')
        os.environ['COMMONUTILS_STORAGE_ROOT'] = str(root / 'commonutils')
        # Set the storage root before Qt/shared imports create their index owner.
        from commonUtils.tests.qt_test_case import QtTestCase
        cleanup.callback(QtTestCase()._release_windows, set())
        from features import preferences
        with patch.object(preferences, 'preferences_path', return_value=root / 'app' / 'preferences.ini'):
            from commonUtils.ui import pyside as qt
            from commonUtils.ui.appearance.theme import apply_theme
            from commonUtils.ui.appearance.styling import apply_styling
            from features.settings import initialize_settings
            from features import registry
            from desktop import main_window
            phase('create QApplication')
            app = qt.initialize_q_app()
            phase('initialize isolated settings and styling')
            initialize_settings()
            apply_theme(app)
            styling = apply_styling(app)
            registry.load_feature_preferences()
            pages = registry.get_pages()
            # Optional external plugins and their initialization hooks belong to
            # their own validation. Exercise the public application's real UI here.
            pages = [entry for entry in pages if entry.feature_name != 'emulation']
            core = tuple((order, name, (lambda parent=None: main_window.FileBrowserPage(
                parent, root_path=browsing)) if factory is main_window.FileBrowserPage else factory)
                for order, name, factory in main_window.CORE_TABS)
            with patch.object(main_window, 'CORE_TABS', core), patch.object(registry, 'get_pages', return_value=pages):
                phase('construct full main window')
                window = main_window.MainWindow()
                phase('show main window')
                window.display_ui()
                screen = window.dlg.screen()
                ui_pixels = qt.QFontInfo(app.font()).pixelSize()
                expected_pixels = styling.values['ui_font_size_int'] * 96 / 72
                if abs(ui_pixels - expected_pixels) > 1:
                    raise AssertionError(f'Unexpected native UI font size: {ui_pixels}, expected {expected_pixels}')
                # Record native list metrics independently of window geometry.
                # This distinguishes font/style density from display scaling.
                from features.git.ui.history import HistoryPanel
                from features.git.ui.chrome import WORKSPACE_STYLE
                from features.git.models import Commit
                history = HistoryPanel(window.dlg)
                history.details.setParent(history)
                history.setObjectName('gitWorkspace')
                history.setStyleSheet(WORKSPACE_STYLE)
                history.uncommitted_count = 1
                history.head_oid = 'a' * 40
                history.set_commits([Commit('a' * 40, (), 'Fixture', '2026-10-12', 'Example commit')])
                history.ensurePolished()
                typo_font = qt.QFont(history.table.font())
                typo_font.setStyleStrategy(typo_font.styleStrategy() | qt.QFont.StyleStrategy.PreferTypoLineMetrics)
                sample_button = qt.QPushButton('Apply settings', history)
                sample_combo = qt.QComboBox(history)
                sample_combo.addItem('Automatic')
                print(json.dumps({'platform': app.platformName(), 'logical_dpi': screen.logicalDotsPerInch(),
                    'device_ratio': screen.devicePixelRatio(), 'window_size': [window.dlg.width(), window.dlg.height()],
                    'ui_font_pixels': ui_pixels, 'ui_font_setting': styling.values['ui_font_size_int'],
                    'ui_font_family': qt.QFontInfo(app.font()).family(),
                    'git_history_row_height': history.table.sizeHintForRow(0),
                    'git_history_clean_row_height': history.table.sizeHintForRow(1),
                    'git_history_text_height': history.table.fontMetrics().height(),
                    'git_history_header_height': history.table.header().sizeHint().height(),
                    'git_history_typo_text_height': qt.QFontMetrics(typo_font).height(),
                    'preferences_button_height': sample_button.sizeHint().height(),
                    'preferences_combo_height': sample_combo.sizeHint().height(),
                    'dpi_helper': getattr(app, '_commonutils_window_dpi_fixer', None) is not None}), flush=True)
                timed_out = []
                def timeout():
                    timed_out.append(True)
                    phase('shutdown timed out')
                    app.quit()
                qt.QTimer.singleShot(1500, window.dlg, window.dlg.close)
                qt.QTimer.singleShot(15000, app, timeout)
                phase('run native event loop')
                code = app.exec()
                if timed_out or window.dlg.isVisible():
                    return 1
                phase('clean shutdown')
                return code


if __name__ == '__main__':
    raise SystemExit(main())
