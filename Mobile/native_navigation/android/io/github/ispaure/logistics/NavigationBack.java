package io.github.ispaure.logistics;

import androidx.activity.ComponentActivity;
import androidx.activity.OnBackPressedCallback;

/** Lifecycle-scoped bridge to AndroidX Back, including the platform dispatcher. */
public final class NavigationBack extends OnBackPressedCallback {
    public interface Listener {
        boolean onBackRequested();
    }

    private final ComponentActivity activity;
    private final Listener listener;

    private NavigationBack(ComponentActivity activity, Listener listener) {
        super(false);
        this.activity = activity;
        this.listener = listener;
    }

    public static NavigationBack install(ComponentActivity activity, Listener listener) {
        NavigationBack callback = new NavigationBack(activity, listener);
        activity.getOnBackPressedDispatcher().addCallback(activity, callback);
        return callback;
    }

    @Override public void handleOnBackPressed() {
        if (!listener.onBackRequested()) {
            setEnabled(false);
            activity.getOnBackPressedDispatcher().onBackPressed();
        }
    }
}
