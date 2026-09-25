"""
Preview launcher for the replacement Logistics UI.

The normal ``launch.py`` continues to start the legacy UI until migration is
complete.
"""

from commonUtils.ui import pyside
from features import registry
from ui_new.main_window import MainWindow


def main() -> int:
    registry.initialize_features()

    app = pyside.initialize_q_app()
    window = MainWindow()
    window.display_ui()

    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
