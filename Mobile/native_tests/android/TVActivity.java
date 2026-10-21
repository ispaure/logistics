package io.github.ispaure.logisticstvprobe;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.ImageReader;
import android.widget.ImageView;
import java.io.File;
import java.io.FileWriter;
import java.lang.reflect.Field;
import io.github.ispaure.logisticsmobile.ComicDisplay;

public class TVActivity extends Activity {
    ComicDisplay output;
    VirtualDisplay display;
    ImageReader reader;
    Drawable current;
    Handler handler = new Handler(Looper.getMainLooper());
    String cases = "";
    int callbacks;

    public void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(new ImageView(this));
        handler.postDelayed(() -> start(), 600);
    }

    void check(boolean value, String message) { if (!value) throw new AssertionError(message); }
    ImageView picture() throws Exception {
        Field field = ComicDisplay.class.getDeclaredField("picture");
        field.setAccessible(true);
        return (ImageView) field.get(output);
    }
    android.widget.TextView status() throws Exception {
        Field field = ComicDisplay.class.getDeclaredField("status");
        field.setAccessible(true);
        return (android.widget.TextView) field.get(output);
    }
    void createDisplay() {
        DisplayManager manager = (DisplayManager) getSystemService(DISPLAY_SERVICE);
        display = manager.createVirtualDisplay("Synthetic TV", 1280, 720, 160, reader.getSurface(),
            DisplayManager.VIRTUAL_DISPLAY_FLAG_PRESENTATION | DisplayManager.VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY);
    }
    void start() {
        try {
            reader = ImageReader.newInstance(1280, 720, PixelFormat.RGBA_8888, 3);
            reader.setOnImageAvailableListener(value -> {
                android.media.Image image = value.acquireLatestImage();
                if (image != null) image.close();
            }, handler);
            Bitmap bitmap = Bitmap.createBitmap(320, 480, Bitmap.Config.ARGB_8888);
            bitmap.eraseColor(Color.RED);
            current = new BitmapDrawable(getResources(), bitmap);
            current.setBounds(1, 2, 321, 482);
            output = new ComicDisplay(this, () -> { callbacks++; output.setImage(current); });
            createDisplay();
            handler.postDelayed(() -> first(), 1400);
        } catch (Throwable error) { finishResult(error); }
    }
    void first() {
        try {
            ImageView view = picture();
            check(view != null && view.getDrawable() != null, "No presentation image after display connection");
            check(view.getWidth() == 1280 && view.getHeight() == 720, "TV canvas not fullscreen: " + view.getWidth() + "x" + view.getHeight());
            check(view.getScaleType() == ImageView.ScaleType.FIT_CENTER, "Image is not fitted");
            check(view.getDrawable() != current, "Source Drawable shared");
            check(current.getBounds().left == 1 && current.getBounds().right == 321, "Phone Drawable bounds changed");
            cases += "native_fullscreen_aspect_fit,independent_drawable,";
            check(status() != null && status().getParent() != null, "Casting status missing on phone");
            check("Casting to TV".contentEquals(status().getText()), "Wrong status text");
            check(!status().isClickable(), "Status intercepts gestures");
            cases += "native_phone_casting_badge,";
            current = null;
            output.setImage(null);
            check(picture().getDrawable() == null, "Blank retained the picture");
            check(status() == null, "Blank output retained casting status");
            cases += "native_blank_clears_image_and_badge,";
            display.release();
            handler.postDelayed(() -> disconnected(), 600);
        } catch (Throwable error) { finishResult(error); }
    }
    void disconnected() {
        try {
            check(picture() == null, "Disconnected presentation retained");
            check(status() == null, "Disconnect retained casting status");
            cases += "disconnect_releases_picture,";
            createDisplay();
            handler.postDelayed(() -> reconnected(), 700);
        } catch (Throwable error) { finishResult(error); }
    }
    void reconnected() {
        try {
            check(picture() != null && picture().getDrawable() == null, "Reconnect exposed cached pixels");
            check(callbacks >= 2, "Display changes did not request fresh source state");
            cases += "reconnect_rechecks_source,";
            Bitmap fresh = Bitmap.createBitmap(10, 20, Bitmap.Config.ARGB_8888);
            output.setImage(new BitmapDrawable(getResources(), fresh));
            check(status() != null, "Reconnect did not restore fresh casting status");
            output.dispose();
            check(status() == null, "Dispose retained casting status");
            check(picture() == null, "Dispose retained image view");
            cases += "dispose_releases_picture";
            display.release();
            reader.close();
            finishResult(null);
        } catch (Throwable error) { finishResult(error); }
    }
    void finishResult(Throwable error) {
        try (FileWriter writer = new FileWriter(new File(getFilesDir(), "tv-result.json"))) {
            String failure = error == null ? "" : error.toString().replace("\"", "'");
            writer.write("{\"success\":" + (error == null) + ",\"cases\":\"" + cases
                + "\",\"error\":\"" + failure + "\",\"scope\":\"Android 36 native Presentation on a synthetic 1280x720 virtual display, no physical TV\"}");
        } catch (Throwable ignored) {}
    }
}
