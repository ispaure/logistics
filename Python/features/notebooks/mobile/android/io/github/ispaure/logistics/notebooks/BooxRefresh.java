package io.github.ispaure.logistics.notebooks;

import android.os.Build;
import android.util.Log;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewTreeObserver;
import android.webkit.WebView;
import com.onyx.android.sdk.api.device.epd.EpdController;
import com.onyx.android.sdk.api.device.epd.UpdateMode;
import java.util.Locale;
import org.lsposed.hiddenapibypass.HiddenApiBypass;

/** View-scoped fast partial updates; never changes the user's app/system mode. */
public final class BooxRefresh implements View.OnTouchListener,
        View.OnAttachStateChangeListener, ViewTreeObserver.OnWindowFocusChangeListener {
    interface Driver {
        UpdateMode get(WebView view);
        boolean set(WebView view, UpdateMode mode);
        boolean reset(WebView view);
        void repaint(WebView view);
    }
    private final WebView view;
    private final Driver driver;
    private static boolean firmwareReady;
    private UpdateMode previous;
    private boolean changed;
    private boolean closed;
    private boolean supported = true;
    private final Runnable settle = () -> restore(true);

    BooxRefresh(WebView view, Driver driver) {
        this.view = view;
        this.driver = driver;
        view.setOnTouchListener(this);
        view.addOnAttachStateChangeListener(this);
        view.getViewTreeObserver().addOnWindowFocusChangeListener(this);
    }

    public static BooxRefresh attach(WebView view) {
        String maker = (Build.MANUFACTURER + " " + Build.BRAND).toLowerCase(Locale.ROOT);
        if (!maker.contains("onyx") && !maker.contains("boox")) return null;
        if (!prepareFirmware()) return null;
        return new BooxRefresh(view, new Driver() {
            public UpdateMode get(WebView target) { return EpdController.getViewDefaultUpdateMode(target); }
            public boolean set(WebView target, UpdateMode mode) {
                // This SDK returns true even when its internal reflection fails.
                EpdController.setViewDefaultUpdateMode(target, mode);
                return EpdController.getViewDefaultUpdateMode(target) == mode;
            }
            public boolean reset(WebView target) { return EpdController.resetViewUpdateMode(target); }
            public void repaint(WebView target) { EpdController.invalidate(target, UpdateMode.GU); }
        });
    }

    private static synchronized boolean prepareFirmware() {
        if (firmwareReady) return true;
        try {
            // Process-local, vendor display symbols only. Do this before the SDK
            // initializes its reflected constants (blocked fields become zero).
            if (Build.VERSION.SDK_INT >= 30 && !HiddenApiBypass.addHiddenApiExemptions(
                    "Landroid/onyx/ViewUpdateHelper;",
                    "Landroid/view/View;->getDefaultUpdateMode(",
                    "Landroid/view/View;->setDefaultUpdateMode(",
                    "Landroid/view/View;->resetUpdateMode(",
                    "Landroid/view/View;->invalidate(")) return false;
            Class<?> helper = Class.forName("android.onyx.ViewUpdateHelper");
            java.lang.reflect.Field du = helper.getDeclaredField("UI_DU_MODE");
            java.lang.reflect.Field gc = helper.getDeclaredField("UI_GC_MODE");
            du.setAccessible(true);
            gc.setAccessible(true);
            firmwareReady = du.getInt(null) != gc.getInt(null);
        } catch (ReflectiveOperationException | RuntimeException | LinkageError failure) {
            Log.w("LogisticsBoox", "Vendor display API unavailable", failure);
        }
        return firmwareReady;
    }

    public boolean isFastModeActive() { return changed; }
    public boolean isSupported() { return supported; }

    @Override public boolean onTouch(View ignored, MotionEvent event) {
        int action = event.getActionMasked();
        if (action == MotionEvent.ACTION_CANCEL) {
            restore(false);
        } else if (action == MotionEvent.ACTION_DOWN && !closed && supported
                && event.getToolType(0) == MotionEvent.TOOL_TYPE_STYLUS) {
            view.removeCallbacks(settle);
            if (!changed) {
                try {
                    previous = driver.get(view);
                    // Without a readable prior mode we cannot guarantee restoration.
                    if (previous == null) {
                        supported = false;
                    } else {
                        changed = driver.set(view, UpdateMode.DU);
                        supported = changed;
                    }
                } catch (RuntimeException | LinkageError failure) {
                    supported = false;
                    Log.w("LogisticsBoox", "Fast partial updates unavailable", failure);
                }
            }
        } else if (action == MotionEvent.ACTION_UP && changed) {
            // Let WebView submit the final ink frame before returning to quality mode.
            view.postDelayed(settle, 180);
        }
        // The WebView still receives every sample, including pressure and history.
        return false;
    }

    private void restore(boolean repaint) {
        view.removeCallbacks(settle);
        if (!changed) return;
        try {
            boolean restored = previous == UpdateMode.None
                ? driver.reset(view)
                : driver.set(view, previous);
            if (restored) {
                changed = false;
                if (repaint) driver.repaint(view);
            } else {
                Log.w("LogisticsBoox", "Could not restore notebook refresh mode");
            }
        } catch (RuntimeException | LinkageError failure) {
            Log.w("LogisticsBoox", "Could not restore notebook refresh mode", failure);
        }
    }

    @Override public void onWindowFocusChanged(boolean focused) {
        if (!focused) restore(false);
    }
    @Override public void onViewAttachedToWindow(View ignored) {
        view.getViewTreeObserver().removeOnWindowFocusChangeListener(this);
        view.getViewTreeObserver().addOnWindowFocusChangeListener(this);
    }
    @Override public void onViewDetachedFromWindow(View ignored) { restore(false); }

    public void close() {
        closed = true;
        restore(false);
        view.setOnTouchListener(null);
        view.removeOnAttachStateChangeListener(this);
        if (view.getViewTreeObserver().isAlive()) {
            view.getViewTreeObserver().removeOnWindowFocusChangeListener(this);
        }
    }
}
