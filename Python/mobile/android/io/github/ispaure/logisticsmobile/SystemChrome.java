package io.github.ispaure.logisticsmobile;

import android.view.View;
import android.view.ViewGroup;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.Insets;
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
        Runnable layout = () -> {
            WindowInsetsCompat root = ViewCompat.getRootWindowInsets(content);
            if (root == null || !(content.getParent() instanceof View)) return;
            Insets safe = root.getInsets(WindowInsetsCompat.Type.systemBars()
                | WindowInsetsCompat.Type.displayCutout());
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
            if (lp.topMargin != top) {
                lp.topMargin = top;
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
        content.getViewTreeObserver().addOnGlobalLayoutListener(layout::run);
        ViewCompat.setOnApplyWindowInsetsListener(content, (view, insets) -> {
            Insets sides = insets.getInsets(WindowInsetsCompat.Type.systemBars()
                | WindowInsetsCompat.Type.displayCutout());
            ViewGroup.MarginLayoutParams lp = (ViewGroup.MarginLayoutParams) view.getLayoutParams();
            if (lp.leftMargin != sides.left || lp.rightMargin != sides.right || lp.bottomMargin != sides.bottom) {
                lp.setMargins(sides.left, lp.topMargin, sides.right, sides.bottom);
                view.setLayoutParams(lp);
            }
            layout.run();
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
