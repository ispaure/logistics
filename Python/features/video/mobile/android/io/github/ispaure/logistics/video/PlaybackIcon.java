package io.github.ispaure.logistics.video;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;

/** Vector transport icons sized independently of their touch targets. */
final class PlaybackIcon extends Drawable {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final String name;
    private final int size;

    PlaybackIcon(String name, int size, int color) {
        this.name = name;
        this.size = size;
        paint.setColor(color);
        paint.setStrokeWidth(1.8f);
        paint.setStrokeCap(Paint.Cap.ROUND);
        paint.setStrokeJoin(Paint.Join.ROUND);
    }

    @Override public void draw(Canvas canvas) {
        Rect bounds = getBounds();
        canvas.save();
        canvas.translate(bounds.left, bounds.top);
        canvas.scale(bounds.width() / 24f, bounds.height() / 24f);
        paint.setStyle(Paint.Style.STROKE);
        switch (name) {
            case "play":
                paint.setStyle(Paint.Style.FILL);
                path(canvas, 8, 4, 20, 12, 8, 20, 8, 4);
                break;
            case "pause":
                paint.setStyle(Paint.Style.FILL);
                canvas.drawRoundRect(6, 4, 10, 20, 1, 1, paint);
                canvas.drawRoundRect(14, 4, 18, 20, 1, 1, paint);
                break;
            case "back":
            case "forward":
                canvas.save();
                if (name.equals("back")) canvas.scale(-1, 1, 12, 12);
                canvas.drawArc(3.5f, 4.5f, 20.5f, 21.5f, -33, 305, false, paint);
                path(canvas, 19, 3, 19, 9, 13, 9);
                canvas.restore();
                text(canvas, "10", 9, 16.5f);
                break;
            case "audio":
                path(canvas, 3, 9, 7, 9, 12, 5, 12, 19, 7, 15, 3, 15, 3, 9);
                canvas.drawArc(10, 7, 19, 17, -55, 110, false, paint);
                canvas.drawArc(8, 4, 22, 20, -55, 110, false, paint);
                break;
            case "captions":
                canvas.drawRoundRect(2, 5, 22, 19, 3, 3, paint);
                text(canvas, "CC", 9, 15);
                break;
            case "chapters":
                for (int y = 6; y <= 18; y += 6) {
                    canvas.drawPoint(4, y, paint);
                    canvas.drawLine(8, y, 21, y, paint);
                }
                break;
            case "fullscreen":
            case "exit":
                for (int side = 0; side < 4; side++) {
                    if (name.equals("exit")) path(canvas, 4, 9, 9, 9, 9, 4);
                    else path(canvas, 4, 9, 4, 4, 9, 4);
                    canvas.rotate(90, 12, 12);
                }
                break;
            case "options":
                paint.setStyle(Paint.Style.FILL);
                for (int x = 5; x <= 19; x += 7) canvas.drawCircle(x, 12, 1.6f, paint);
                break;
            case "close":
                canvas.drawLine(6, 6, 18, 18, paint);
                canvas.drawLine(6, 18, 18, 6, paint);
                break;
        }
        canvas.restore();
    }

    private void path(Canvas canvas, float... points) {
        Path path = new Path();
        path.moveTo(points[0], points[1]);
        for (int i = 2; i < points.length; i += 2) path.lineTo(points[i], points[i + 1]);
        canvas.drawPath(path, paint);
    }

    private void text(Canvas canvas, String value, float size, float baseline) {
        paint.setStyle(Paint.Style.FILL);
        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTextSize(size);
        canvas.drawText(value, 12, baseline, paint);
    }

    @Override public int getIntrinsicWidth() { return size; }
    @Override public int getIntrinsicHeight() { return size; }
    @Override public void setAlpha(int alpha) { paint.setAlpha(alpha); invalidateSelf(); }
    @Override public void setColorFilter(ColorFilter filter) { paint.setColorFilter(filter); invalidateSelf(); }
    @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
}
