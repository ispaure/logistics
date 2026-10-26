package io.github.ispaure.logistics.notebooks;

import android.graphics.Rect;
import android.webkit.JavascriptInterface;
import android.view.MotionEvent;
import android.util.Log;
import android.view.View;
import android.view.ViewTreeObserver;
import android.webkit.WebView;
import com.onyx.android.sdk.api.device.epd.EpdController;
import com.onyx.android.sdk.data.note.TouchPoint;
import com.onyx.android.sdk.pen.RawInputCallback;
import com.onyx.android.sdk.pen.TouchHelper;
import com.onyx.android.sdk.pen.data.TouchPointList;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONObject;
import org.json.JSONArray;

/** Optional direct Boox preview; canonical brush geometry and saving stay in the WebView. */
public final class BooxInk implements ViewTreeObserver.OnWindowFocusChangeListener,
        View.OnAttachStateChangeListener {
    private final WebView view;
    private TouchHelper helper;
    private float maxPressure;
    private final ArrayList<TouchPoint> live = new ArrayList<>();
    private List<TouchPoint> completed;
    private int begins, ends, moves, savedSamples, rejected;
    private float minimum = Float.POSITIVE_INFINITY, maximum;
    private boolean active, closed, enabled;
    private String error = "";

    private Rect bounds = new Rect();
    private final ArrayList<Rect> exclusions = new ArrayList<>();
    private String configuration = "";
    private boolean reconciling, failed;
    private int previewTool = -1, previewColor, previewStyle = -1;
    private final BooxBallpoint ballpoint = new BooxBallpoint();
    private float pageScale, baseWidth;
    private boolean widthUnavailable;

    private static int styleFor(int tool) {
        // Ballpoint uses the plain native path with our pressure-derived widths;
        // automatic Fountain rendering would use a different pressure curve.
        if (tool == 17 || tool == 15) return TouchHelper.STROKE_STYLE_PENCIL;
        return -1;
    }

    private static boolean opaquePenColor(int color) {
        return color == 0 || color == 1 || color == 2 || color == 6 || color == 7
            || color == 10 || color == 11 || color == 12 || color == 13;
    }
    public int begins() { return begins; }
    public boolean drawing() { return active; }
    public void unavailable() { fail(new IllegalStateException("No raw callbacks; replaying Android pen input")); }
    private float scaleX = 1, scaleY = 1;

    public static BooxInk attach(WebView view, BooxRefresh refresh) {
        if (refresh == null || !refresh.isSupported()) return null;
        BooxInk ink = null;
        try {
            ink = new BooxInk(view);
            ink.initialize();
            return ink;
        } catch (RuntimeException | LinkageError failure) {
            if (ink != null) ink.close();
            Log.w("LogisticsBooxInk", "Native handwriting unavailable; using ordinary ink", failure);
            return null;
        }
    }

    private BooxInk(WebView view) { this.view = view; }

    private void initialize() {
        maxPressure = EpdController.getMaxTouchPressure();
        if (!Float.isFinite(maxPressure) || maxPressure <= 0) throw new IllegalStateException("No native pressure range");
        // SF draws directly to the display. It must not replace NotebookInput's
        // Android listener, which remains available for the baseline/fallback.
        helper = TouchHelper.create(view, TouchHelper.FEATURE_SF_TOUCH_RENDER, callback, false);
        helper.setPostInputEvent(false);
        helper.setPenUpRefreshTimeMs(30);
        helper.openRawDrawing();
        helper.setRawDrawingEnabled(false);
        view.getViewTreeObserver().addOnWindowFocusChangeListener(this);
        view.addOnAttachStateChangeListener(this);
        view.addJavascriptInterface(this, "LogisticsBooxInk");
    }

    // Only numeric preview configuration is accepted. This interface has no
    // file access and exists only on the local, navigation-blocked notebook view.
    @JavascriptInterface public void configure(String json) {
        if (json == null || json.length() > 16000) return;
        view.post(() -> {
            if (closed || failed || json.equals(configuration)) return;
            try {
                JSONObject config = new JSONObject(json);
                cancel();
                helper.setRawDrawingEnabled(false);
                configuration = json;
                previewTool = config.optInt("tool", -1);
                previewStyle = styleFor(previewTool);
                long argb = config.optLong("argb", 0);
                previewColor = (int) argb;
                enabled = config.optBoolean("enabled") && previewStyle >= 0
                    && !(previewTool == 15 && widthUnavailable)
                    && opaquePenColor(config.optInt("color", -1))
                    && argb >= 0xff000000L && argb <= 0xffffffffL;
                double cssWidth = config.getDouble("viewportWidth"), cssHeight = config.getDouble("viewportHeight");
                if (!Double.isFinite(cssWidth) || !Double.isFinite(cssHeight) || cssWidth <= 0 || cssHeight <= 0)
                    throw new IllegalArgumentException("Invalid viewport");
                scaleX = (float) (view.getWidth() / cssWidth);
                scaleY = (float) (view.getHeight() / cssHeight);
                bounds = rect(config.getJSONArray("rect"));
                exclusions.clear();
                JSONArray blocked = config.getJSONArray("exclude");
                if (blocked.length() > 32) throw new IllegalArgumentException("Too many exclusions");
                for (int i = 0; i < blocked.length(); i++) exclusions.add(rect(blocked.getJSONArray(i)));
                double width = config.optDouble("width");
                baseWidth = (float) config.optDouble("baseWidth");
                pageScale = (float) width * scaleX / baseWidth;
                if (previewTool == 15 && (!Float.isFinite(pageScale) || pageScale <= 0
                        || (baseWidth != 1 && baseWidth != 2 && baseWidth != 4))) enabled = false;
                if (!Double.isFinite(width) || width <= 0 || width > 500 || bounds.isEmpty()) enabled = false;
                helper.setLimitRect(bounds, exclusions);
                if (enabled) helper.setStrokeStyle(previewStyle)
                    .setStrokeColor(previewColor).setStrokeWidth(previewTool == 15
                        ? BooxBallpoint.width(0, baseWidth) * pageScale : (float) width * scaleX);
                apply();
            } catch (Exception | LinkageError failure) { fail(failure); }
        });
    }

    private Rect rect(JSONArray value) throws Exception {
        if (value.length() != 4) throw new IllegalArgumentException("Invalid ink rectangle");
        int[] v = new int[4];
        for (int i = 0; i < 4; i++) {
            double number = value.getDouble(i);
            if (!Double.isFinite(number) || Math.abs(number) > 100000) throw new IllegalArgumentException("Invalid coordinate");
            v[i] = (int) (number * (i % 2 == 0 ? scaleX : scaleY));
        }
        Rect result = new Rect(v[0], v[1], v[2], v[3]);
        if (!result.intersect(0, 0, view.getWidth(), view.getHeight())) result.setEmpty();
        return result;
    }

    private boolean contains(float x, float y) {
        if (!bounds.contains((int) x, (int) y)) return false;
        for (Rect r : exclusions) if (r.contains((int) x, (int) y)) return false;
        return true;
    }

    /** Called by the single Android listener before forwarding ordinary pen ink. */
    public boolean owns(MotionEvent event) {
        if (closed || failed || !enabled || (previewTool == 15 && widthUnavailable && !active)
                || reconciling || !view.hasWindowFocus()) return false;
        int tool = event.getToolType(event.getActionIndex());
        if (tool == MotionEvent.TOOL_TYPE_ERASER) {
            suspend(); // Hardware eraser stays on the canonical eraser/input path.
            return false;
        }
        return tool == MotionEvent.TOOL_TYPE_STYLUS && (active || contains(event.getX(), event.getY()));
    }

    public void suspend() {
        cancel();
        enabled = false;
        configuration = "";
        try { if (helper != null) helper.setRawDrawingEnabled(false); }
        catch (RuntimeException | LinkageError failure) { fail(failure); }
    }

    private void apply() {
        if (!closed && helper != null) {
            helper.setRawDrawingEnabled(enabled && !(previewTool == 15 && widthUnavailable)
                && !reconciling && view.hasWindowFocus() && view.isAttachedToWindow());
            if (enabled && previewTool == 15 && !active) {
                ballpoint.reset();
                helper.setStrokeWidth(BooxBallpoint.width(0, baseWidth) * pageScale);
            }
        }
    }

    private void cancel() {
        if (active) view.evaluateJavascript("window.logisticsNativePen&&window.logisticsNativePen('cancel',999,[[0,0,0]]," + view.getWidth() + "," + view.getHeight() + ")", null);
        active = false; live.clear(); completed = null; ballpoint.reset();
    }

    private void fail(Throwable failure) {
        failed = true;
        error = failure.toString();
        Log.w("LogisticsBooxInk", "Disabling native preview; ordinary ink remains available", failure);
        close();
    }

    private final RawInputCallback callback = new RawInputCallback() {
        @Override public void onBeginRawDrawing(boolean shortcut, TouchPoint point) {
            if (!enabled || closed || reconciling || !contains(point.getX(), point.getY())) return;
            begins++; active = true; live.clear(); completed = null;
            live.add(point);
            preview(point);
            view.evaluateJavascript("window.logisticsNativePen('down',999,[[" + point.getX() + "," + point.getY() + "," + Math.max(0, Math.min(1, point.getPressure() / maxPressure)) + "]]," + view.getWidth() + "," + view.getHeight() + ")", null);
        }
        @Override public void onRawDrawingTouchPointMoveReceived(TouchPoint point) {
            if (!active || closed) return;
            moves++;
            if (live.size() < 100000) live.add(point);
            else { rejected++; suspend(); }
            preview(point);
        }
        @Override public void onRawDrawingTouchPointListReceived(TouchPointList points) {
            if (active && !closed) {
                if (points.getPoints().size() > 100000) { rejected++; suspend(); }
                else completed = new ArrayList<>(points.getPoints());
            }
        }
        @Override public void onEndRawDrawing(boolean outOfBounds, TouchPoint point) {
            try { finishRaw(); }
            catch (RuntimeException | LinkageError failure) { fail(failure); }
        }
        private void finishRaw() {
            if (!active || closed) return;
            ends++;
            ballpoint.reset();
            List<TouchPoint> points = completed != null && !completed.isEmpty() ? completed : new ArrayList<>(live);
            if (points.isEmpty() || points.size() > 100000) { rejected++; suspend(); return; }
            StringBuilder data = new StringBuilder();
            for (TouchPoint p : points) {
                float x = p.getX(), y = p.getY(), pressure = p.getPressure() / maxPressure;
                if (!Float.isFinite(x) || !Float.isFinite(y) || !Float.isFinite(pressure)) { rejected++; suspend(); return; }
                pressure = Math.max(0, Math.min(1, pressure));
                minimum = Math.min(minimum, pressure); maximum = Math.max(maximum, pressure);
                if (data.length() > 0) data.append(',');
                data.append('[').append(x).append(',').append(y).append(',').append(pressure).append(']');
            }
            savedSamples += points.size();
            // The exact existing JS brush/preview/ordered-save path receives
            // the complete native stroke once. SDK-generated Android events
            // are disabled, preventing two competing stroke owners.
            String js = "(()=>{const p=[" + data + "],w=" + view.getWidth() + ",h=" + view.getHeight()
                + ";"
                + "if(p.length>1)window.logisticsNativePen('move',999,p.slice(1),w,h);"
                + "window.logisticsNativePen('up',999,[p[p.length-1]],w,h)})()";
            active = false;
            reconciling = true;
            // Stop raw input while Chromium catches up. Leave its preview visible
            // until the canonical canvas has a frame, then retire the overlay.
            helper.setRawInputReaderEnable(false);
            view.evaluateJavascript(js, ignored -> view.postVisualStateCallback(ends,
                new WebView.VisualStateCallback() {
                    @Override public void onComplete(long id) {
                        if (closed) return;
                        try {
                            helper.setRawDrawingRenderEnabled(false);
                            view.invalidate();
                            reconciling = false;
                            apply();
                        } catch (RuntimeException | LinkageError failure) { fail(failure); }
                    }
                }));
            completed = null; live.clear();
        }
        @Override public void onBeginRawErasing(boolean shortcut, TouchPoint point) { rejected++; }
        @Override public void onEndRawErasing(boolean outside, TouchPoint point) {}
        @Override public void onRawErasingTouchPointMoveReceived(TouchPoint point) {}
        @Override public void onRawErasingTouchPointListReceived(TouchPointList points) {}
    };

    private void preview(TouchPoint point) {
        if (previewTool != 15 || !active || widthUnavailable) return;
        try {
            if (!Float.isFinite(point.getX()) || !Float.isFinite(point.getY()) || !Float.isFinite(point.getPressure()))
                throw new IllegalArgumentException("Invalid raw pen sample");
            ballpoint.point(helper, point.getPressure() / maxPressure,
                baseWidth, pageScale);
        } catch (RuntimeException | LinkageError failure) {
            // Finish this contact through the existing save path even if a
            // firmware cannot update native widths. Future contacts fall back.
            widthUnavailable = true;
            error = failure.toString();
            Log.w("LogisticsBooxInk", "Ballpoint pressure width preview unavailable", failure);
        }
    }

    public String status() {
        JSONObject out = new JSONObject();
        try {
            out.put("created", helper != null && helper.isRawDrawingCreated());
            out.put("input", helper != null && helper.isRawDrawingInputEnabled());
            out.put("render", helper != null && helper.isRawDrawingRenderEnabled());
            out.put("max_pressure", maxPressure); out.put("begins", begins); out.put("ends", ends);
            out.put("moves", moves); out.put("samples", savedSamples); out.put("rejected", rejected);
            out.put("pressure_min", Float.isFinite(minimum) ? minimum : 0); out.put("pressure_max", maximum);
            out.put("active", active); out.put("error", error); out.put("closed", closed);
            out.put("preview_tool", previewTool); out.put("preview_style", previewStyle);
            out.put("preview_argb", Integer.toUnsignedLong(previewColor));
            out.put("width_updates", ballpoint.submissions());
        } catch (Exception failure) { throw new IllegalStateException(failure); }
        return out.toString();
    }

    @Override public void onWindowFocusChanged(boolean focus) {
        if (closed) return;
        try { if (!focus) cancel(); apply(); }
        catch (RuntimeException | LinkageError failure) { fail(failure); }
    }
    @Override public void onViewAttachedToWindow(View ignored) {}
    @Override public void onViewDetachedFromWindow(View ignored) { suspend(); }

    public void close() {
        if (closed) return;
        cancel(); enabled = false; closed = true;
        ballpoint.close();
        view.removeJavascriptInterface("LogisticsBooxInk");
        try { if (helper != null) { helper.setRawDrawingEnabled(false); helper.closeRawDrawing(); } }
        catch (RuntimeException | LinkageError failure) { Log.w("LogisticsBooxInk", "Raw handwriting cleanup failed", failure); }
        finally {
            view.removeOnAttachStateChangeListener(this);
            if (view.getViewTreeObserver().isAlive()) view.getViewTreeObserver().removeOnWindowFocusChangeListener(this);
            Log.i("LogisticsBooxInk", "Raw handwriting released");
        }
    }
}
