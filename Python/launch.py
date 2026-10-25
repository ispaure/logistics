# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2020-2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

# ----------------------------------------------------------------------------------------------------------------------

from commonUtils.runtime.diagnostics import Severity, log
from commonUtils.runtime.platform import OS, get_os
from commonUtils.integrations.wrappers.cmdShellWrapper import minimize_console_window
from commonUtils.ui import pyside
from commonUtils.ui.appearance.theme import apply_theme
from commonUtils.ui.appearance.styling import apply_styling
from features.settings import initialize_settings
from features.application import registry
from commonUtils.runtime.diagnostics import configure
from commonUtils.ui.diagnostics import present_diagnostic

from desktop.main_window import MainWindow
from services.folders.ui.indexing import IndexService


def main() -> int:
    log(Severity.INFO, 'Logistics', 'Executing launch.py')

    # Startup errors may show a dialog, so Qt must exist before feature hooks run.
    log(Severity.DEBUG, 'PySide6', 'Create QApplication')
    app = pyside.initialize_q_app()
    configure(presenter=present_diagnostic)
    initialize_settings()
    indexing = IndexService()
    try:
        indexing.start()
        apply_theme(app)
        apply_styling(app)
        from desktop.settings.window import open_settings
        app._commonutils_open_settings = open_settings
        log(Severity.DEBUG, 'Logistics', 'Initialize Features')
        registry.load_feature_preferences()
        registry.initialize_features()

        log(Severity.DEBUG, 'PySide6', 'Display Main UI Window')
        main_window = MainWindow()
        main_window.display_ui()
        main_window.start_updates()
        if get_os() == OS.WIN:
            # Let Qt display the landing page before minimizing its console.
            pyside.QTimer.singleShot(0, main_window.dlg, minimize_console_window)
        exit_code = app.exec()
    finally:
        indexing.stop()
    if main_window.pending_update is not None:
        from services.updates import launch_helper
        launch_helper(main_window.pending_update)
    return exit_code



if __name__ == "__main__":
    raise SystemExit(main())
