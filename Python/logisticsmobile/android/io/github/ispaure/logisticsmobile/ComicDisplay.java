package io.github.ispaure.logisticsmobile;

import android.app.Activity;
import android.app.Presentation;
import android.graphics.Color;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.hardware.display.DisplayManager;
import android.os.Handler;
import android.os.Looper;
import android.view.Display;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.FrameLayout;
import android.widget.TextView;

/** Picture-only output on Android system presentation/cast displays. */
public final class ComicDisplay implements DisplayManager.DisplayListener {
    private final Activity activity;
    private final DisplayManager displays;
    private Presentation presentation;
    private ImageView picture;
    private TextView status;
    private Runnable refresh;
    private int displayId = -1;

    public ComicDisplay(Activity activity, Runnable refresh) {
        this.activity = activity;
        this.refresh = refresh;
        displays = (DisplayManager) activity.getSystemService(Activity.DISPLAY_SERVICE);
        displays.registerDisplayListener(this, new Handler(Looper.getMainLooper()));
        update();
    }

    public void setImage(Drawable image) {
        update();
        // Separate Drawable bounds/callbacks; share only the decoded bitmap.
        if (picture != null) picture.setImageDrawable(image == null || image.getConstantState() == null ? null
            : image.getConstantState().newDrawable(presentation.getContext().getResources()).mutate());
        showStatus(picture != null && picture.getDrawable() != null && presentation.isShowing());
    }

    public boolean isShowing() {
        return presentation != null && presentation.isShowing();
    }

    private int dp(int value) {
        return Math.round(value * activity.getResources().getDisplayMetrics().density);
    }

    private void showStatus(boolean casting) {
        if (!casting) {
            if (status != null) ((android.view.ViewGroup) status.getParent()).removeView(status);
            status = null;
            return;
        }
        FrameLayout root = (FrameLayout) activity.getWindow().getDecorView();
        if (status == null) {
            status = new TextView(activity);
            status.setText("Casting to TV");
            status.setContentDescription("Casting comic to TV");
            status.setTextColor(Color.WHITE);
            status.setTextSize(13);
            status.setGravity(Gravity.CENTER);
            status.setPadding(dp(12), dp(6), dp(12), dp(6));
            status.setClickable(false);
            status.setFocusable(false);
            GradientDrawable background = new GradientDrawable();
            background.setColor(Color.argb(210, 0, 0, 0));
            background.setCornerRadius(dp(14));
            status.setBackground(background);
            FrameLayout.LayoutParams layout = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.END);
            layout.setMargins(dp(12), dp(12), dp(12), dp(40));
            root.addView(status, layout);
        }
        status.bringToFront();
    }

    private void close() {
        showStatus(false);
        if (picture != null) picture.setImageDrawable(null);
        if (presentation != null) presentation.dismiss();
        picture = null;
        presentation = null;
        displayId = -1;
    }

    private void update() {
        Display[] available = displays.getDisplays(DisplayManager.DISPLAY_CATEGORY_PRESENTATION);
        Display selected = null;
        for (Display display : available) {
            if (display.getDisplayId() != activity.getWindowManager().getDefaultDisplay().getDisplayId()) {
                selected = display;
                break;
            }
        }
        if (selected == null) { close(); return; }
        if (presentation != null && displayId == selected.getDisplayId() && presentation.isShowing()) return;
        close();
        presentation = new Presentation(activity, selected);
        presentation.requestWindowFeature(Window.FEATURE_NO_TITLE);
        picture = new ImageView(presentation.getContext());
        picture.setBackgroundColor(Color.BLACK);
        picture.setScaleType(ImageView.ScaleType.FIT_CENTER);
        presentation.setContentView(picture);
        Window window = presentation.getWindow();
        window.setBackgroundDrawableResource(android.R.color.black);
        window.setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN, WindowManager.LayoutParams.FLAG_FULLSCREEN);
        window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        try {
            presentation.show();
            window.setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT);
            displayId = selected.getDisplayId();
        } catch (WindowManager.InvalidDisplayException e) {
            close();
        }
    }

    private void changed() {
        update();
        if (refresh != null) refresh.run();
    }

    @Override public void onDisplayAdded(int id) { changed(); }
    @Override public void onDisplayRemoved(int id) { changed(); }
    @Override public void onDisplayChanged(int id) { changed(); }

    public void dispose() {
        refresh = null;
        close();
        displays.unregisterDisplayListener(this);
    }
}
