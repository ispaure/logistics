package io.github.ispaure.logisticsmobile;

import android.view.View;
import android.view.ViewTreeObserver;

/** One draw traversal, followed by a posted callback. No timer or content state. */
public final class DrawReady {
    public interface Listener { void onDrawn(); }
    public static final class Watch implements ViewTreeObserver.OnDrawListener, Runnable {
        private final View view;
        private final ViewTreeObserver observer;
        private Listener listener;
        private boolean posted;
        Watch(View view, Listener listener) {
            this.view = view;
            this.listener = listener;
            observer = view.getViewTreeObserver();
            observer.addOnDrawListener(this);
            view.invalidate();
        }
        @Override public void onDraw() {
            if (!posted && listener != null && view.isShown() && view.getWidth() > 0 && view.getHeight() > 0) {
                posted = true;
                view.post(this);
            }
        }
        @Override public void run() {
            Listener ready = listener;
            cancel();
            if (ready != null) ready.onDrawn();
        }
        public void cancel() {
            listener = null;
            view.removeCallbacks(this);
            if (observer.isAlive()) observer.removeOnDrawListener(this);
        }
    }
    public static Watch watch(View view, Listener listener) { return new Watch(view, listener); }
    private DrawReady() {}
}
