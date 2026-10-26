package io.github.ispaure.logistics.notebooks;

import android.graphics.Rect;
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

/** QA-only raw display/canonical-save experiment. Never installed in the main app. */
public final class BooxRawInk implements ViewTreeObserver.OnWindowFocusChangeListener,
        View.OnAttachStateChangeListener {
    private final WebView view;
    private TouchHelper helper;
    private final float maxPressure;
    private final ArrayList<TouchPoint> live = new ArrayList<>();
    private List<TouchPoint> completed;
    private int begins, ends, moves, savedSamples, rejected;
    private float minimum = Float.POSITIVE_INFINITY, maximum;
    private boolean active, closed, enabled;
    private String error = "";

    public BooxRawInk(WebView view) {
        this.view = view;
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
    }

    public void configure(int tool, int color, float width, int left, int top, int right, int bottom) {
        if (closed || active) throw new IllegalStateException("Raw renderer unavailable during a stroke");
        helper.setRawDrawingEnabled(false);
        helper.setLimitRect(new Rect(left, top, right, bottom), new ArrayList<Rect>());
        // These are temporary vendor approximations. The canonical notebook
        // renderer, selected brush and normalized pressure still own saved ink.
        int style = tool == 14 || tool == 13 ? TouchHelper.STROKE_STYLE_PENCIL
            : tool == 17 ? TouchHelper.STROKE_STYLE_PENCIL : TouchHelper.STROKE_STYLE_FOUNTAIN;
        helper.setStrokeStyle(style).setStrokeColor(color).setStrokeWidth(width);
    }

    public void enable(boolean value) {
        enabled = value;
        active = false;
        live.clear(); completed = null;
        if (helper != null && !closed) helper.setRawDrawingEnabled(value && view.hasWindowFocus());
    }

    private final RawInputCallback callback = new RawInputCallback() {
        @Override public void onBeginRawDrawing(boolean shortcut, TouchPoint point) {
            if (!enabled || closed) return;
            begins++; active = true; live.clear(); completed = null;
            live.add(point);
        }
        @Override public void onRawDrawingTouchPointMoveReceived(TouchPoint point) {
            if (!active || closed) return;
            moves++;
            if (live.size() < 100000) live.add(point);
            else { error = "Stroke sample limit exceeded"; active = false; rejected++; }
        }
        @Override public void onRawDrawingTouchPointListReceived(TouchPointList points) {
            if (active && !closed) completed = new ArrayList<>(points.getPoints());
        }
        @Override public void onEndRawDrawing(boolean outOfBounds, TouchPoint point) {
            if (!active || closed) return;
            active = false; ends++;
            List<TouchPoint> points = completed != null && !completed.isEmpty() ? completed : new ArrayList<>(live);
            if (points.isEmpty() || points.size() > 100000) { rejected++; return; }
            StringBuilder data = new StringBuilder();
            for (TouchPoint p : points) {
                float x = p.getX(), y = p.getY(), pressure = p.getPressure() / maxPressure;
                if (!Float.isFinite(x) || !Float.isFinite(y) || !Float.isFinite(pressure)) { rejected++; return; }
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
                + ";window.logisticsNativePen('down',999,[p[0]],w,h);"
                + "if(p.length>1)window.logisticsNativePen('move',999,p.slice(1),w,h);"
                + "window.logisticsNativePen('up',999,[p[p.length-1]],w,h)})()";
            view.evaluateJavascript(js, ignored -> view.postVisualStateCallback(ends,
                new WebView.VisualStateCallback() {
                    @Override public void onComplete(long id) { if (!closed) view.invalidate(); }
                }));
            completed = null; live.clear();
        }
        @Override public void onBeginRawErasing(boolean shortcut, TouchPoint point) { rejected++; }
        @Override public void onEndRawErasing(boolean outside, TouchPoint point) {}
        @Override public void onRawErasingTouchPointMoveReceived(TouchPoint point) {}
        @Override public void onRawErasingTouchPointListReceived(TouchPointList points) {}
    };

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
        } catch (Exception failure) { throw new IllegalStateException(failure); }
        return out.toString();
    }

    @Override public void onWindowFocusChanged(boolean focus) {
        active = false; live.clear(); completed = null;
        if (!closed) helper.setRawDrawingEnabled(focus && enabled);
    }
    @Override public void onViewAttachedToWindow(View ignored) {}
    @Override public void onViewDetachedFromWindow(View ignored) { enable(false); }

    public void close() {
        if (closed) return;
        enable(false); closed = true;
        try { helper.closeRawDrawing(); }
        finally {
            view.removeOnAttachStateChangeListener(this);
            if (view.getViewTreeObserver().isAlive()) view.getViewTreeObserver().removeOnWindowFocusChangeListener(this);
            Log.i("LogisticsRawInkQA", "Raw handwriting released");
        }
    }
}
