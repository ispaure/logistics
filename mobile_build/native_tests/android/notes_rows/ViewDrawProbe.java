// TEST_STAGE = TestStage.EXTENDED
package io.github.ispaure.logisticsqa;

import android.view.View;
import android.view.ViewTreeObserver;

/** First frame after a complete source publication, without Python draw callbacks. */
public final class ViewDrawProbe implements ViewTreeObserver.OnDrawListener {
    private final View view;
    private ViewTreeObserver observer;
    private long started, drawn;
    private boolean armed;

    public ViewDrawProbe(View target) {
        view = target;
        observer = view.getViewTreeObserver();
        observer.addOnDrawListener(this);
    }
    public void start() {
        started = System.nanoTime();
        drawn = 0;
        armed = false;
    }
    public void arm() { armed = true; }
    @Override public void onDraw() {
        if (armed && drawn == 0 && view.isShown() && view.getWidth() > 0 && view.getHeight() > 0) {
            drawn = System.nanoTime();
            armed = false;
        }
    }
    public boolean hasDrawn() { return drawn != 0; }
    public double elapsedSeconds() { return drawn == 0 ? -1 : (drawn - started) / 1000000000.0; }
    public void dispose() {
        if (observer != null && observer.isAlive()) observer.removeOnDrawListener(this);
        observer = null;
        armed = false;
    }
}
