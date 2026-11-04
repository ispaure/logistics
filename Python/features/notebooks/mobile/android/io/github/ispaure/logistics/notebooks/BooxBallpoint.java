package io.github.ispaure.logistics.notebooks;

import com.onyx.android.sdk.pen.TouchHelper;

/** Drive the plain native pen with canonical, pressure-shaped Ballpoint widths. */
final class BooxBallpoint {
    private float previous = Float.NaN;
    private int submissions;

    static float width(float pressure, float base) {
        return width(pressure, base, .34f, 3.875f);
    }

    static float width(float pressure, float base, float factor, float exponent) {
        double value = base * (1 - factor + factor * Math.pow(Math.max(0, Math.min(1, pressure)), exponent));
        return Math.max(.25f, (float) (Math.floor(value * 4 + .5) / 4));
    }

    int submissions() { return submissions; }

    void point(TouchHelper helper, float pressure, float base, float pageScale, float factor, float exponent) {
        float diameter = width(pressure, base, factor, exponent) * pageScale;
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
