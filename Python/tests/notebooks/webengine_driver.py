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


def composited_image(view, rectangle):
    """Fence a native screenshot on a new displayed frame, outside its crop.

    JavaScript completion and animation callbacks can precede Qt's compositor.
    A black/white corner marker changes on each capture and is color-profile
    independent. The crop must exclude the marker's first eight CSS pixels.
    """
    color = javascript(view, """(()=>{
        let marker=document.getElementById('qaCompositorFence');
        if(!marker){marker=document.createElement('div');marker.id='qaCompositorFence';
            marker.style.cssText='position:fixed;left:0;top:0;width:8px;height:8px;z-index:2147483647;pointer-events:none';
            document.body.append(marker)}
        marker.dataset.phase=marker.dataset.phase==='black'?'white':'black';
        marker.style.backgroundColor=marker.dataset.phase;
        return marker.dataset.phase;
    })()""")
    expected = qt.QColor(color)

    def displayed():
        frame = view.grab(qt.QRect(0, 0, 8, 8)).toImage()
        return not frame.isNull() and frame.pixelColor(frame.width() // 2, frame.height() // 2) == expected

    wait_until(displayed, 'native compositor frame')
    # Keep the established raster settling interval, after the displayed fence.
    QTest.qWait(100)
    return view.grab(rectangle).toImage()
