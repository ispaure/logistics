package io.github.ispaure.logistics.notebooks;

import android.os.SystemClock;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.webkit.WebView;

/** Synthetic native event history, dispatched through the real WebView listener. */
public final class NotebookInputChecks {
    private NotebookInputChecks() {}
    private static long contactStart;
    public static float ballpointWidth(float pressure, float base) { return BooxBallpoint.width(pressure, base); }


    /** Exercise our raw callback/direct preview/save handoff without fabricating hardware latency. */
    public static void rawBallpoint(NotebookInput input, WebView view, float x, float y) throws Exception {
        rawStroke(input, view, x, y, 25, 8);
    }

    public static void rawStroke(NotebookInput input, WebView view, float x, float y, int count, int interval) throws Exception {
        java.lang.reflect.Field inkField = NotebookInput.class.getDeclaredField("ink");
        inkField.setAccessible(true);
        Object ink = inkField.get(input);
        java.lang.reflect.Field callbackField = BooxInk.class.getDeclaredField("callback");
        callbackField.setAccessible(true);
        com.onyx.android.sdk.pen.RawInputCallback callback =
            (com.onyx.android.sdk.pen.RawInputCallback) callbackField.get(ink);
        float maxPressure = com.onyx.android.sdk.api.device.epd.EpdController.getMaxTouchPressure();
        for (int i = 0; i < count; i++) {
            final int index = i;
            view.postDelayed(() -> {
                com.onyx.android.sdk.data.note.TouchPoint point =
                    new com.onyx.android.sdk.data.note.TouchPoint(x + index * 96f / (count - 1), y + (float) Math.sin(index / 4.) * 20);
                point.setPressure(maxPressure * (.1f + index * .9f / (count - 1)));
                if (index == 0) callback.onBeginRawDrawing(false, point);
                else callback.onRawDrawingTouchPointMoveReceived(point);
                if (index == count - 1) callback.onEndRawDrawing(false, point);
            }, i * (long) interval);
        }
    }

    /** Individual timed events, so Chromium paints between pen samples. */
    public static void contact(WebView view, int action, float x, float y, float pressure) {
        long now = SystemClock.uptimeMillis();
        if (action == MotionEvent.ACTION_DOWN) contactStart = now;
        MotionEvent.PointerProperties property = new MotionEvent.PointerProperties();
        property.id = 0;
        property.toolType = MotionEvent.TOOL_TYPE_STYLUS;
        MotionEvent.PointerCoords point = new MotionEvent.PointerCoords();
        point.x = x; point.y = y; point.pressure = pressure; point.size = 1;
        MotionEvent event = MotionEvent.obtain(contactStart, now, action, 1,
            new MotionEvent.PointerProperties[]{property}, new MotionEvent.PointerCoords[]{point},
            0, 0, 1, 1, 0, 0, InputDevice.SOURCE_STYLUS, 0);
        view.dispatchTouchEvent(event);
        event.recycle();
    }

    public static void stroke(WebView view, float x, float y) {
        historyStroke(view, x, y, 22);
    }

    public static void historyStroke(WebView view, float x, float y, int count) {
        long start = SystemClock.uptimeMillis();
        MotionEvent.PointerProperties property = new MotionEvent.PointerProperties();
        property.id = 0;
        property.toolType = MotionEvent.TOOL_TYPE_STYLUS;
        MotionEvent.PointerCoords point = new MotionEvent.PointerCoords();
        point.x = x; point.y = y; point.pressure = .2f; point.size = 1;
        MotionEvent down = MotionEvent.obtain(start, start, MotionEvent.ACTION_DOWN, 1,
            new MotionEvent.PointerProperties[]{property}, new MotionEvent.PointerCoords[]{point},
            0, 0, 1, 1, 0, 0, InputDevice.SOURCE_STYLUS, 0);
        view.dispatchTouchEvent(down);
        down.recycle();
        float step = count == 22 ? 4 : 160f / (count - 1);
        point.x = x + step;
        MotionEvent move = MotionEvent.obtain(start, start + 1, MotionEvent.ACTION_MOVE, 1,
            new MotionEvent.PointerProperties[]{property}, new MotionEvent.PointerCoords[]{point},
            0, 0, 1, 1, 0, 0, InputDevice.SOURCE_STYLUS, 0);
        for (int i = 1; i <= count - 2; i++) {
            point.x = x + step + i * step;
            point.y = y + (float) Math.sin(i / 5.0) * 30;
            point.pressure = .2f + i * .6f / (count - 2);
            move.addBatch(start + 1 + i, new MotionEvent.PointerCoords[]{point}, 0);
        }
        view.dispatchTouchEvent(move);
        move.recycle();
        point.pressure = 0;
        MotionEvent up = MotionEvent.obtain(start, start + count, MotionEvent.ACTION_UP, 1,
            new MotionEvent.PointerProperties[]{property}, new MotionEvent.PointerCoords[]{point},
            0, 0, 1, 1, 0, 0, InputDevice.SOURCE_STYLUS, 0);
        view.dispatchTouchEvent(up);
        up.recycle();
    }
}
