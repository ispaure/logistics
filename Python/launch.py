from commonUtils.debugUtils import Severity, log
from commonUtils import ui
from commonUtils.ui import pyside
from commonUtils.ui.theme import apply_theme
from features import registry
from ui_new.main_window import MainWindow
from services.application_instance import instance_lock


def main() -> int:
    log(Severity.INFO, 'Logistics', 'Executing launch.py')

    # Startup errors may show a dialog, so Qt must exist before feature hooks run.
    log(Severity.DEBUG, 'PySide6', 'Create QApplication')
    app = pyside.initialize_q_app()
    lock = instance_lock()
    if not lock.tryLock(0):
        if lock.error() != pyside.QLockFile.LockError.LockFailedError:
            raise RuntimeError('Could not acquire the Logistics instance lock. Check access to the commonUtils Temp folder.')
        ui.display_msg_box_ok('Logistics is already open',
                             'Logistics is already open. Please use the existing window.')
        return 0
    try:
        apply_theme(app)
        log(Severity.DEBUG, 'Logistics', 'Initialize Features')
        registry.initialize_features()

        log(Severity.DEBUG, 'PySide6', 'Display Main UI Window')
        main_window = MainWindow()
        main_window.display_ui()
        return app.exec()
    finally:
        lock.unlock()



if __name__ == "__main__":
    raise SystemExit(main())
