package io.github.ispaure.logistics.notebooks;

import android.os.SystemClock;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.webkit.WebView;
import com.onyx.android.sdk.api.device.epd.UpdateMode;

/** Real Android events/timers with a fake display driver; no Boox hardware claim. */
public final class BooxRefreshChecks {
    private static final class FakeDriver implements BooxRefresh.Driver {
        UpdateMode mode = UpdateMode.REGAL;
        int repaints;
        int resets;
        public UpdateMode get(WebView view) { return mode; }
        public boolean set(WebView view, UpdateMode value) { mode = value; return true; }
        public boolean reset(WebView view) { mode = UpdateMode.None; resets++; return true; }
        public void repaint(WebView view) { repaints++; }
    }
    private final WebView view;
    private final FakeDriver driver = new FakeDriver();
    private final BooxRefresh refresh;

    public BooxRefreshChecks(WebView view) {
        this.view = view;
        refresh = new BooxRefresh(view, driver);
        touch(MotionEvent.ACTION_DOWN, MotionEvent.TOOL_TYPE_FINGER);
        require(driver.mode == UpdateMode.REGAL, "Finger changed refresh mode");
        touch(MotionEvent.ACTION_DOWN, MotionEvent.TOOL_TYPE_STYLUS);
        require(driver.mode == UpdateMode.DU && refresh.isFastModeActive(), "Pen did not enter DU");
        touch(MotionEvent.ACTION_UP, MotionEvent.TOOL_TYPE_STYLUS);
        require(refresh.isFastModeActive(), "Pen-up restored before final frame");
    }

    private static void require(boolean valid, String message) {
        if (!valid) throw new AssertionError(message);
    }

    private void touch(int action, int tool) {
        MotionEvent.PointerProperties properties = new MotionEvent.PointerProperties();
        properties.id = 0;
        properties.toolType = tool;
        MotionEvent.PointerCoords coords = new MotionEvent.PointerCoords();
        coords.x = 20; coords.y = 20; coords.pressure = .5f; coords.size = 1;
        long now = SystemClock.uptimeMillis();
        MotionEvent event = MotionEvent.obtain(now, now, action, 1,
            new MotionEvent.PointerProperties[]{properties}, new MotionEvent.PointerCoords[]{coords},
            0, 0, 1, 1, 0, 0, InputDevice.SOURCE_STYLUS, 0);
        try {
            require(!refresh.onTouch(view, event), "Refresh controller consumed pen input");
        } finally { event.recycle(); }
    }

    public boolean checkAndClose() {
        try {
            require(driver.mode == UpdateMode.REGAL && driver.repaints == 1 && !refresh.isFastModeActive(),
                "Delayed quality refresh did not restore the previous mode");
            touch(MotionEvent.ACTION_DOWN, MotionEvent.TOOL_TYPE_STYLUS);
            touch(MotionEvent.ACTION_UP, MotionEvent.TOOL_TYPE_STYLUS);
            touch(MotionEvent.ACTION_DOWN, MotionEvent.TOOL_TYPE_STYLUS);
            require(driver.mode == UpdateMode.DU, "New pen contact lost fast mode");
            touch(MotionEvent.ACTION_CANCEL, MotionEvent.TOOL_TYPE_STYLUS);
            require(driver.mode == UpdateMode.REGAL, "Cancellation did not restore mode");
            touch(MotionEvent.ACTION_DOWN, MotionEvent.TOOL_TYPE_STYLUS);
            refresh.onWindowFocusChanged(false);
            require(driver.mode == UpdateMode.REGAL, "Backgrounding did not restore mode");
            touch(MotionEvent.ACTION_DOWN, MotionEvent.TOOL_TYPE_STYLUS);
            refresh.onViewDetachedFromWindow(view);
            require(driver.mode == UpdateMode.REGAL, "Detachment did not restore mode");
            driver.mode = UpdateMode.None;
            touch(MotionEvent.ACTION_DOWN, MotionEvent.TOOL_TYPE_STYLUS);
            touch(MotionEvent.ACTION_CANCEL, MotionEvent.TOOL_TYPE_STYLUS);
            require(driver.resets == 1 && driver.mode == UpdateMode.None, "Inherited mode was not reset");
            driver.mode = null;
            touch(MotionEvent.ACTION_DOWN, MotionEvent.TOOL_TYPE_STYLUS);
            require(!refresh.isSupported() && !refresh.isFastModeActive(), "Unsupported firmware changed mode");
            return true;
        } finally { refresh.close(); }
    }

    public void close() { refresh.close(); }
}
