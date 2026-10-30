package io.github.ispaure.logisticsmobile;

import android.app.Activity;
import android.view.KeyEvent;
import android.view.Window;
import androidx.appcompat.view.WindowCallbackWrapper;

/** Activity-window interception also works when a reader WebView has focus. */
public final class ReaderVolumeKeys extends WindowCallbackWrapper {
    public interface Listener {
        boolean onVolumeKey(int direction);
    }

    private final Activity activity;
    private Listener listener;
    private boolean upHeld, downHeld;

    public ReaderVolumeKeys(Activity activity, Listener listener) {
        super(activity.getWindow().getCallback());
        this.activity = activity;
        this.listener = listener;
        activity.getWindow().setCallback(this);
    }

    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        int code = event.getKeyCode();
        if (listener == null || (code != KeyEvent.KEYCODE_VOLUME_UP
                && code != KeyEvent.KEYCODE_VOLUME_DOWN)) return super.dispatchKeyEvent(event);
        boolean up = code == KeyEvent.KEYCODE_VOLUME_UP;
        boolean held = up ? upHeld : downHeld;
        if (event.getAction() == KeyEvent.ACTION_UP) {
            if (up) upHeld = false; else downHeld = false;
            if (held) return true;
        } else if (event.getAction() == KeyEvent.ACTION_DOWN) {
            // Consume repeats and the matching release, but turn only once.
            if (held && event.getRepeatCount() > 0) return true;
            if (event.getRepeatCount() == 0 && activity.hasWindowFocus()
                    && listener.onVolumeKey(up ? -1 : 1)) {
                if (up) upHeld = true; else downHeld = true;
                return true;
            }
        }
        return super.dispatchKeyEvent(event);
    }

    @Override public void onWindowFocusChanged(boolean focused) {
        if (!focused) upHeld = downHeld = false;
        super.onWindowFocusChanged(focused);
    }

    public void dispose() {
        listener = null;
        upHeld = downHeld = false;
        Window window = activity.getWindow();
        if (window.getCallback() == this) window.setCallback(getWrapped());
    }
}
