"""Event-aware waits shared by the optional notebook browser probes."""
import time

from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest


def wait_until(predicate, label='browser state', timeout=15, interval=5):
    deadline = time.monotonic() + timeout
    while True:
        qt.QApplication.processEvents()
        if predicate():
            return
        if time.monotonic() >= deadline:
            raise AssertionError('Timed out: ' + label)
        QTest.qWait(interval)


def javascript(view, script, timeout=15):
    values = []
    view.page().runJavaScript(script, values.append)
    wait_until(lambda: bool(values), 'JavaScript callback', timeout)
    return values[0]
