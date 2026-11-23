// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package io.github.ispaure.logistics.video;

import android.app.Activity;
import android.app.Presentation;
import android.content.Context;
import android.graphics.Color;
import android.hardware.display.DisplayManager;
import android.view.Display;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import org.videolan.libvlc.util.VLCVideoLayout;

final class ExternalVideoDisplay extends Presentation {
    final VLCVideoLayout video;

    static Display[] available(Activity activity) {
        DisplayManager displays = (DisplayManager) activity.getSystemService(Context.DISPLAY_SERVICE);
        return displays.getDisplays(DisplayManager.DISPLAY_CATEGORY_PRESENTATION);
    }

    ExternalVideoDisplay(Activity activity, Display display) {
        super(activity, display);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        video = new VLCVideoLayout(getContext());
        video.setBackgroundColor(Color.BLACK);
        setContentView(video);
        Window window = getWindow();
        window.setBackgroundDrawableResource(android.R.color.black);
        window.addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
    }

    void showVideo() {
        show();
        getWindow().setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT);
    }
}
