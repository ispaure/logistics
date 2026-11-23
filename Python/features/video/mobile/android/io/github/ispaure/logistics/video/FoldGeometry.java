// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package io.github.ispaure.logistics.video;

import android.app.Activity;
import android.graphics.Rect;
import android.view.View;
import androidx.core.util.Consumer;
import androidx.window.java.layout.WindowInfoTrackerCallbackAdapter;
import androidx.window.layout.DisplayFeature;
import androidx.window.layout.FoldingFeature;
import androidx.window.layout.WindowInfoTracker;
import androidx.window.layout.WindowLayoutInfo;

/** A separating fold in the coordinate space of a mounted view. */
public final class FoldGeometry implements View.OnAttachStateChangeListener {
    private final Activity activity;
    private final View view;
    private final Runnable changed;
    private final WindowInfoTrackerCallbackAdapter tracker;
    private final Consumer<WindowLayoutInfo> consumer = this::update;
    private Rect fold;

    public FoldGeometry(Activity activity, View view, Runnable changed) {
        this.activity = activity;
        this.view = view;
        this.changed = changed;
        tracker = new WindowInfoTrackerCallbackAdapter(WindowInfoTracker.getOrCreate(activity));
        view.addOnAttachStateChangeListener(this);
        if (view.isAttachedToWindow()) onViewAttachedToWindow(view);
    }

    @Override public void onViewAttachedToWindow(View view) {
        tracker.addWindowLayoutInfoListener(activity, command -> view.post(command), consumer);
    }

    @Override public void onViewDetachedFromWindow(View view) {
        tracker.removeWindowLayoutInfoListener(consumer);
        fold = null;
    }

    private void update(WindowLayoutInfo info) {
        if (!view.isAttachedToWindow()) return;
        Rect next = null;
        for (DisplayFeature feature : info.getDisplayFeatures()) {
            if (feature instanceof FoldingFeature && ((FoldingFeature) feature).isSeparating()) {
                next = new Rect(feature.getBounds());
                break;
            }
        }
        if (java.util.Objects.equals(fold, next)) return;
        fold = next;
        changed.run();
    }

    public Rect boundsIn(View target) {
        if (fold == null || !target.isAttachedToWindow()
                || !java.util.Objects.equals(target.getWindowToken(), view.getWindowToken())) return null;
        int[] origin = new int[2];
        target.getLocationInWindow(origin);
        Rect local = new Rect(fold);
        local.offset(-origin[0], -origin[1]);
        return local;
    }
}
