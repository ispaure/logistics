package io.github.ispaure.logistics.notebooks;

import com.onyx.android.sdk.pen.TouchHelper;

/** Drive the plain native pen with canonical, pressure-shaped Ballpoint widths. */
final class BooxBallpoint {
    private float previous = Float.NaN;
    private int submissions;

    static float width(float pressure, float base) {
        double value = base * (.35 + .65 * Math.pow(Math.max(0, Math.min(1, pressure)), 1.2));
        return Math.max(.25f, (float) (Math.floor(value * 4 + .5) / 4));
    }

    int submissions() { return submissions; }

    void point(TouchHelper helper, float pressure, float base, float pageScale) {
        float diameter = width(pressure, base) * pageScale;
        // The driver still draws positions directly from the digitizer. Only
        // change the width when the canonical quarter-unit width changes.
        if (diameter != previous) {
            helper.setStrokeWidth(diameter);
            previous = diameter;
            submissions++;
        }
    }

    void reset() { previous = Float.NaN; }
    void close() { reset(); }
}
