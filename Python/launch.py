from commonUtils.debugUtils import Severity, log
from commonUtils.ui import pyside
from features import registry
from ui_new.main_window import MainWindow


def main() -> int:
    log(Severity.INFO, 'Logistics', 'Executing launch.py')

    # Startup errors may show a dialog, so Qt must exist before feature hooks run.
    log(Severity.DEBUG, 'PySide6', 'Create QApplication')
    app = pyside.initialize_q_app()

    log(Severity.DEBUG, 'Logistics', 'Initialize Features')
    registry.initialize_features()

    # Display UI
    log(Severity.DEBUG, 'PySide6', 'Display Main UI Window')
    main_window = MainWindow()
    main_window.display_ui()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
