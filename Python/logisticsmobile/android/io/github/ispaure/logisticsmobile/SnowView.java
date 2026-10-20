package io.github.ispaure.logisticsmobile;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;
import java.util.Random;

/** Decorative only: never takes focus, accessibility focus or touch events. */
public final class SnowView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final float[][] flakes = new float[28][4];
    private final long started = SystemClock.uptimeMillis();

    public SnowView(Context context) {
        super(context);
        setClickable(false);
        setFocusable(false);
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
        paint.setColor(0x99B4CCE4);
        Random random = new Random(15);
        for (float[] flake : flakes) {
            flake[0] = random.nextFloat();
            flake[1] = random.nextFloat();
            flake[2] = 12 + random.nextFloat() * 16;
            flake[3] = 1.5f + random.nextFloat() * 1.5f;
        }
    }

    @Override public boolean onTouchEvent(MotionEvent event) { return false; }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (!isShown() || !hasWindowFocus() || getWidth() == 0 || getHeight() == 0) return;
        float density = getResources().getDisplayMetrics().density;
        float elapsed = (SystemClock.uptimeMillis() - started) / 1000f;
        for (float[] flake : flakes) {
            float x = (flake[0] * getWidth() + elapsed * 4 * density) % getWidth();
            float y = (flake[1] * getHeight() + elapsed * flake[2] * density) % getHeight();
            canvas.drawCircle(x, y, flake[3] * density, paint);
        }
        postInvalidateDelayed(33);
    }

    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (focused) invalidate();
    }
}
