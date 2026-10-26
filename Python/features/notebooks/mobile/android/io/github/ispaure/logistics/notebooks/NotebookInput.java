package io.github.ispaure.logistics.notebooks;

import android.view.MotionEvent;
import android.view.View;
import android.view.ViewTreeObserver;
import android.webkit.WebView;

/** Deliver the digitizer's complete pen history without Chromium resampling it. */
public final class NotebookInput implements View.OnTouchListener,
        View.OnAttachStateChangeListener, ViewTreeObserver.OnWindowFocusChangeListener {
    private final WebView view;
    private final BooxRefresh refresh;
    private int pointer = -1;
    private float x, y;
    private boolean closed;
    private final BooxInk ink;
    private final java.util.ArrayList<MotionEvent> backup = new java.util.ArrayList<>();
    private int rawBegins;
    private boolean rawObserved;
    private boolean rawContact;
    public String nativeStatus() { return ink == null ? "{\"available\":false}" : ink.status(); }
    public void disableNativePreview() { if (ink != null) ink.close(); }
    private final Runnable verifyRaw = this::verifyRaw;
    private void verifyRaw() {
        if (backup.isEmpty()) return;
        if (ink != null && !rawObserved && ink.begins() == rawBegins) {
            ink.unavailable();
            // Unsupported firmware can report an enabled reader without any
            // callbacks. Replay this contact once, then retain ordinary input.
            for (MotionEvent event : backup) ordinary(event);
        }
        clearBackup();
    }

    public static NotebookInput attach(WebView view, BooxRefresh refresh) {
        return new NotebookInput(view, refresh);
    }

    private NotebookInput(WebView view, BooxRefresh refresh) {
        this.view = view;
        this.refresh = refresh;
        ink = BooxInk.attach(view, refresh);
        view.setOnTouchListener(this);
        view.addOnAttachStateChangeListener(this);
        view.getViewTreeObserver().addOnWindowFocusChangeListener(this);
    }

    @Override public boolean onTouch(View ignored, MotionEvent event) {
        if (closed) return false;
        int action = event.getActionMasked();
        if (action == MotionEvent.ACTION_DOWN && !backup.isEmpty()) {
            view.removeCallbacks(verifyRaw);
            verifyRaw.run();
        }
        if (action == MotionEvent.ACTION_DOWN) {
            // Choose once for the whole contact. Reconciliation can finish
            // between down and up; switching then would back up only the tail
            // and falsely diagnose a reader which never received this down.
            rawContact = ink != null && ink.owns(event);
            if (ink != null) ink.ordinaryContact(!rawContact
                && event.getToolType(event.getActionIndex()) == MotionEvent.TOOL_TYPE_STYLUS);
        }
        if (rawContact) {
            if (backup.isEmpty()) { rawBegins = ink.begins(); rawObserved = ink.drawing(); }
            rawObserved |= ink.drawing();
            if (backup.size() < 10000) backup.add(MotionEvent.obtain(event));
            if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
                view.postDelayed(verifyRaw, 100);
                rawContact = false;
            }
            return false;
        }
        if (!backup.isEmpty() && (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL))
            view.postDelayed(verifyRaw, 100);
        ordinary(event);
        if (ink != null && (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL))
            ink.ordinaryContact(false);
        return false;
    }

    private void clearBackup() {
        for (MotionEvent event : backup) event.recycle();
        backup.clear();
    }

    private void ordinary(MotionEvent event) {
        if (refresh != null) refresh.onTouch(view, event);
        int action = event.getActionMasked(), index = event.getActionIndex();
        if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_POINTER_DOWN) {
            int tool = event.getToolType(index);
            if (tool != MotionEvent.TOOL_TYPE_STYLUS && tool != MotionEvent.TOOL_TYPE_ERASER) return;
            cancel();
            pointer = event.getPointerId(index);
            view.requestUnbufferedDispatch(event);
            deliver("down", event, index);
        } else if (pointer >= 0) {
            index = event.findPointerIndex(pointer);
            if (action == MotionEvent.ACTION_CANCEL || index < 0) cancel();
            else if (action == MotionEvent.ACTION_MOVE) deliver("move", event, index);
            else if ((action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_POINTER_UP)
                    && event.getPointerId(event.getActionIndex()) == pointer) {
                deliver((event.getFlags() & 0x20) != 0 ? "cancel" : "up", event, index); // FLAG_CANCELED
                pointer = -1;
            }
        }
        // Preserve ordinary WebView input for buttons, selects and finger paging.
        // The canvas ignores duplicate trusted Chromium pen events only.
    }

    private static void point(StringBuilder data, float x, float y, float pressure) {
        if (!Float.isFinite(x) || !Float.isFinite(y) || !Float.isFinite(pressure)) return;
        if (data.length() > 0) data.append(',');
        data.append('[').append(x).append(',').append(y).append(',')
            .append(Math.max(0, Math.min(1, pressure))).append(']');
    }

    private void deliver(String action, MotionEvent event, int index) {
        StringBuilder data = new StringBuilder();
        for (int h = 0; h < event.getHistorySize(); h++) {
            point(data, event.getHistoricalX(index, h), event.getHistoricalY(index, h),
                event.getHistoricalPressure(index, h));
        }
        x = event.getX(index);
        y = event.getY(index);
        point(data, x, y, event.getPressure(index));
        evaluate(action, data.toString());
    }

    private void evaluate(String action, String samples) {
        // Only finite native numbers cross this boundary. No JS interface or
        // document content is exposed to other origins or to Android storage.
        view.evaluateJavascript("window.logisticsNativePen&&window.logisticsNativePen('" + action
            + "'," + pointer + ",[" + samples + "]," + view.getWidth() + "," + view.getHeight() + ")", null);
    }

    private void cancel() {
        if (pointer < 0) return;
        StringBuilder data = new StringBuilder();
        point(data, x, y, 0);
        evaluate("cancel", data.toString());
        pointer = -1;
    }

    @Override public void onWindowFocusChanged(boolean focused) {
        if (!focused) {
            cancel(); rawContact = false;
            if (ink != null) ink.ordinaryContact(false);
            view.removeCallbacks(verifyRaw); clearBackup();
        }
    }
    @Override public void onViewAttachedToWindow(View ignored) {
        view.getViewTreeObserver().removeOnWindowFocusChangeListener(this);
        view.getViewTreeObserver().addOnWindowFocusChangeListener(this);
    }
    @Override public void onViewDetachedFromWindow(View ignored) {
        cancel(); rawContact = false;
        if (ink != null) ink.ordinaryContact(false);
        view.removeCallbacks(verifyRaw); clearBackup();
    }

    public void close() {
        cancel();
        closed = true;
        view.removeCallbacks(verifyRaw);
        clearBackup();
        if (ink != null) ink.close();
        view.setOnTouchListener(null);
        view.removeOnAttachStateChangeListener(this);
        if (view.getViewTreeObserver().isAlive()) view.getViewTreeObserver().removeOnWindowFocusChangeListener(this);
    }
}
