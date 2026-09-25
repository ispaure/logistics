import ui.uiMain as uiMain

from commonUtils.debugUtils import Severity, log
from commonUtils.ui import pyside
from features import registry


def main() -> int:
    log(Severity.INFO, 'Logistics', 'Executing launch.py')

    # Initialize Features
    log(Severity.DEBUG, 'Logistics', 'Initialize Features')
    registry.initialize_features()

    # Create QApplication
    log(Severity.DEBUG, 'PySide6', 'Create QApplication')
    app = pyside.initialize_q_app()

    # Display UI
    log(Severity.DEBUG, 'PySide6', 'Display Main UI Window')
    uiMain.display_main_menu()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
