// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package io.github.ispaure.logisticsmobile;

import android.view.View;
import android.view.ViewGroup;
import java.util.Collections;
import java.util.function.Consumer;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.Insets;
import androidx.core.view.DisplayCutoutCompat;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

/** Keep Briefcase's edge-to-edge content below the visible toolbar and system bars. */
public final class SystemChrome {
    private static final String STATUS_TAG = "logistics.status.background";
    private SystemChrome() {}

    public static void install(AppCompatActivity activity, View content) {
        View status = new View(activity);
        status.setTag(STATUS_TAG);
        activity.addContentView(status, new ViewGroup.LayoutParams(-1, 0));
        int[] location = new int[2];
        Consumer<WindowInsetsCompat> layout = root -> {
            if (root == null || !(content.getParent() instanceof View)) return;
            Insets bars = root.getInsets(WindowInsetsCompat.Type.systemBars());
            Insets safe = Insets.max(bars, root.getInsets(WindowInsetsCompat.Type.displayCutout()));
            View parent = (View) content.getParent();
            parent.getLocationInWindow(location);
            int parentTop = location[1];
            int top = Math.max(0, safe.top - parentTop);
            View bar = activity.findViewById(androidx.appcompat.R.id.action_bar_container);
            if (bar != null && bar.isShown()) {
                bar.getLocationInWindow(location);
                top = Math.max(top, location[1] + bar.getHeight() - parentTop);
            }
            ViewGroup.MarginLayoutParams lp = (ViewGroup.MarginLayoutParams) content.getLayoutParams();
            int left = safe.left;
            DestinationRailView rail = content.findViewWithTag(DestinationRailView.WINDOW_TAG);
            if (rail != null) {
                DisplayCutoutCompat cutout = root.getDisplayCutout();
                boolean safeCandidate = cutout != null && bars.left == 0
                    && cutout.getWaterfallInsets().left == 0 && cutout.getSafeInsetLeft() == left;
                if (rail.useCameraStrip(safeCandidate ? left : 0,
                        safeCandidate ? cutout.getBoundingRects() : Collections.emptyList())) {
                    left = 0;
                }
            }
            if (lp.leftMargin != left || lp.topMargin != top
                    || lp.rightMargin != safe.right || lp.bottomMargin != safe.bottom) {
                lp.setMargins(left, top, safe.right, safe.bottom);
                content.setLayoutParams(lp);
            }
            ViewGroup.MarginLayoutParams strip = (ViewGroup.MarginLayoutParams) status.getLayoutParams();
            int stripHeight = Math.max(0, safe.top - parentTop);
            if (strip.height != stripHeight) {
                strip.height = stripHeight;
                status.setLayoutParams(strip);
            }
        };
        // AppCompat can show or hide a toolbar without redispatching window insets.
        content.getViewTreeObserver().addOnGlobalLayoutListener(
            () -> layout.accept(ViewCompat.getRootWindowInsets(content)));
        ViewCompat.setOnApplyWindowInsetsListener(content, (view, insets) -> {
            layout.accept(insets);
            return insets;
        });
    }

    public static void paint(AppCompatActivity activity, int statusColor, int navigationColor, boolean light) {
        android.view.Window window = activity.getWindow();
        View decor = window.getDecorView();
        View status = decor.findViewWithTag(STATUS_TAG);
        if (status != null) status.setBackgroundColor(statusColor);
        window.setStatusBarColor(statusColor);
        window.setNavigationBarColor(navigationColor);
        WindowInsetsControllerCompat controller = WindowCompat.getInsetsController(window, decor);
        controller.setAppearanceLightStatusBars(light);
        controller.setAppearanceLightNavigationBars(light);
    }
}
