package io.github.ispaure.logisticsmobile;

import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.SystemClock;
import android.view.FrameMetrics;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Collections;

/** QA-only collector: no Python calls on every frame or touch event. */
public final class FileListBenchmark implements Window.OnFrameMetricsAvailableListener {
    private final Window window;
    private final HandlerThread thread = new HandlerThread("list-profile-frames");
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ArrayList<Long> durations = new ArrayList<>();
    private long layout, draw;
    private int dropped, late;
    private boolean recording;

    public FileListBenchmark(Window value) { window = value; thread.start(); }
    public synchronized void start() {
        durations.clear(); layout = draw = 0; dropped = late = 0; recording = true;
        window.addOnFrameMetricsAvailableListener(this, new Handler(thread.getLooper()));
    }
    public void stop() {
        window.removeOnFrameMetricsAvailableListener(this);
        synchronized(this) { recording = false; }
    }
    public void dispose() { thread.quitSafely(); }
    @Override public synchronized void onFrameMetricsAvailable(Window window, FrameMetrics metrics, int lost) {
        if (!recording) return;
        long total = metrics.getMetric(FrameMetrics.TOTAL_DURATION);
        long deadline = metrics.getMetric(FrameMetrics.DEADLINE);
        durations.add(total);
        if (deadline > 0 && total > deadline) late++;
        layout += metrics.getMetric(FrameMetrics.LAYOUT_MEASURE_DURATION);
        draw += metrics.getMetric(FrameMetrics.DRAW_DURATION);
        dropped += lost;
    }
    private double percentile(ArrayList<Long> sorted, double fraction) {
        if (sorted.isEmpty()) return 0;
        return sorted.get((int)Math.ceil(fraction * sorted.size()) - 1) / 1e6;
    }
    public synchronized String report() throws Exception {
        ArrayList<Long> sorted = new ArrayList<>(durations); Collections.sort(sorted);
        JSONObject data = new JSONObject();
        data.put("frames", sorted.size()); data.put("missed_deadline", late);
        data.put("collector_dropped", dropped);
        data.put("p50_ms", percentile(sorted, .5)); data.put("p90_ms", percentile(sorted, .9));
        data.put("p95_ms", percentile(sorted, .95)); data.put("max_ms", percentile(sorted, 1));
        data.put("layout_measure_total_ms", layout / 1e6); data.put("draw_total_ms", draw / 1e6);
        return data.toString();
    }
    public static int countViews(View view) {
        // Toga Box backgrounds and their contents can be native siblings.
        return countSubtree(view.getRootView());
    }
    private static int countSubtree(View view) {
        int count = 1;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup)view;
            for (int i=0; i<group.getChildCount(); i++) count += countSubtree(group.getChildAt(i));
        }
        return count;
    }
    public void swipes(View target, int count) {
        for (int swipe=0; swipe<count; swipe++) {
            final long offset = swipe * 850;
            main.postDelayed(() -> {
                final long down = SystemClock.uptimeMillis();
                final float x = target.getWidth() * .5f;
                final float start = target.getHeight() * .8f, end = target.getHeight() * .25f;
                send(target, down, MotionEvent.ACTION_DOWN, x, start);
                for (int step=1; step<=20; step++) {
                    final float fraction = step / 20f;
                    final int action = step == 20 ? MotionEvent.ACTION_UP : MotionEvent.ACTION_MOVE;
                    main.postDelayed(() -> send(target, down, action, x, start+(end-start)*fraction), step*20);
                }
            }, offset);
        }
    }
    private void send(View target, long down, int action, float x, float y) {
        MotionEvent event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, x, y, 0);
        target.dispatchTouchEvent(event); event.recycle();
    }
}
