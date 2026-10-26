package io.github.ispaure.logisticsmobile;

import android.app.Activity;
import android.os.Build;
import android.view.Window;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import java.util.Locale;

/** Reclaim Boox's reserved but unpainted status strip using real window insets. */
public final class BooxWindow {
    private BooxWindow() {}

    public static void configure(Activity activity) {
        String maker = (Build.MANUFACTURER + " " + Build.BRAND).toLowerCase(Locale.ROOT);
        if (!maker.contains("onyx") && !maker.contains("boox")) return;
        Window window = activity.getWindow();
        // Some Boox modes suppress the clock without removing its inset. Mark
        // it hidden explicitly; the activity still reserves display cutouts,
        // navigation bars and the IME through its existing inset listener.
        WindowCompat.getInsetsController(window, window.getDecorView()).hide(WindowInsetsCompat.Type.statusBars());
        ViewCompat.requestApplyInsets(window.getDecorView());
    }
}
