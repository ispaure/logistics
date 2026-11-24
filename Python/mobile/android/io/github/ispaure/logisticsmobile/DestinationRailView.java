// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package io.github.ispaure.logisticsmobile;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import androidx.core.view.ViewCompat;
import com.google.android.material.navigationrail.NavigationRailView;
import com.google.android.material.shape.ShapeAppearanceModel;
import java.util.List;

/** Desktop-style placement while retaining Material selection and accessibility. */
public final class DestinationRailView extends NavigationRailView {
    static final String WINDOW_TAG = "logistics.destination.rail";
    private int footerItemId;
    private final Paint dividerPaint = new Paint();
    private int cameraTop;
    private int cameraBottom;

    public DestinationRailView(Context context, int footerItemId) {
        super(context);
        this.footerItemId = footerItemId;
        setTag(WINDOW_TAG);
        // The native window host already reserves system bars and cutouts.
        // An explicit pass-through also prevents framework inset padding when
        // an existing tablet rail rotates; removing the listener falls back to
        // that dispatch and can add a cutout wider than the whole 56 dp rail.
        ViewCompat.setOnApplyWindowInsetsListener(this, (view, insets) -> insets);
        setMenuGravity(Gravity.TOP);
        setLabelVisibilityMode(2); // LABEL_VISIBILITY_UNLABELED
        setItemIconSize(dp(26));
        setItemMinimumHeight(dp(48));
        // Material applies this margin above AND below the centered icon
        // container. The default rail spacing can exceed our whole 48 dp row.
        // Keep one rounded 40 dp selection shape in both colour modes.
        setItemActiveIndicatorWidth(dp(40));
        setItemActiveIndicatorHeight(dp(40));
        setItemActiveIndicatorShapeAppearance(ShapeAppearanceModel.builder()
                .setAllCornerSizes(dp(20)).build());
        setItemPaddingTop(dp(4));
        setItemPaddingBottom(dp(4));
        setMinimumWidth(dp(56));
        dividerPaint.setColor(Color.TRANSPARENT);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    public void setRailDividerColor(int color) {
        if (dividerPaint.getColor() != color) {
            dividerPaint.setColor(color);
            invalidate();
        }
    }

    @Override
    protected void dispatchDraw(Canvas canvas) {
        super.dispatchDraw(canvas);
        if (Color.alpha(dividerPaint.getColor()) == 0) return;
        int thickness = Math.max(1, dp(1));
        int x = getLayoutDirection() == View.LAYOUT_DIRECTION_RTL ? 0 : getWidth() - thickness;
        canvas.drawRect(x, 0, x + thickness, getHeight(), dividerPaint);
    }

    @Override
    protected void onMeasure(int widthSpec, int heightSpec) {
        int width = resolveSize(dp(56), widthSpec);
        super.onMeasure(MeasureSpec.makeMeasureSpec(width, MeasureSpec.EXACTLY), heightSpec);
    }

    /** Use the left cutout strip only when every real tab target fits beside the camera. */
    boolean useCameraStrip(int inset, List<Rect> rects) {
        int top = 0;
        int bottom = 0;
        boolean fits = false;
        if (inset > 0 && inset <= getWidth() && isShown() && getLayoutDirection() == View.LAYOUT_DIRECTION_LTR) {
            int[] location = new int[2];
            getLocationInWindow(location);
            top = getHeight();
            for (Rect rect : rects) {
                if (rect.left < inset && rect.right > 0) {
                    top = Math.min(top, rect.top - location[1] - getPaddingTop() - dp(4));
                    bottom = Math.max(bottom, rect.bottom - location[1] - getPaddingTop() + dp(4));
                }
            }
            fits = bottom > top && targetsFit(top, bottom);
        }
        if (!fits) top = bottom = 0;
        if (top != cameraTop || bottom != cameraBottom) {
            cameraTop = top;
            cameraBottom = bottom;
            requestLayout();
        }
        return fits;
    }

    private int skipCamera(int y, int itemHeight, int top, int bottom) {
        return bottom > top && y < bottom && y + itemHeight > top ? bottom : y;
    }

    private int footerTop(int height, int inset, int itemHeight, int top, int bottom) {
        int y = height - inset - itemHeight;
        return skipCamera(y, itemHeight, top, bottom) != y ? top - itemHeight : y;
    }

    private boolean targetsFit(int top, int bottom) {
        ViewGroup menu = (ViewGroup) getMenuView();
        int inset = dp(8);
        int itemHeight = dp(48);
        int height = getHeight() - getPaddingTop() - getPaddingBottom();
        int y = inset;
        int end = height - inset;
        for (int i = 0; i < menu.getChildCount(); i++) {
            View item = menu.getChildAt(i);
            if (item.getVisibility() == View.GONE) continue;
            if (item.getId() == footerItemId) {
                end = footerTop(height, inset, itemHeight, top, bottom);
            } else {
                y = skipCamera(y, itemHeight, top, bottom) + itemHeight;
            }
        }
        return y <= end;
    }

    @Override
    protected void onLayout(boolean changed, int left, int top, int right, int bottom) {
        super.onLayout(changed, left, top, right, bottom);
        ViewGroup menu = (ViewGroup) getMenuView();
        int count = 0;
        for (int i = 0; i < menu.getChildCount(); i++) {
            if (menu.getChildAt(i).getVisibility() != View.GONE) count++;
        }
        int inset = dp(8);
        int itemHeight = dp(48);
        int height = getHeight() - getPaddingTop() - getPaddingBottom();
        // In a short window retain Material's compact fallback rather than overlap.
        if (height < count * itemHeight + inset * 2) return;
        int width = getWidth() - getPaddingLeft() - getPaddingRight();
        // Expand the real hit-test/accessibility parent, not just icon translations.
        menu.layout(getPaddingLeft(), getPaddingTop(),
                    getPaddingLeft() + width, getPaddingTop() + height);
        int y = inset;
        for (int i = 0; i < menu.getChildCount(); i++) {
            View item = menu.getChildAt(i);
            if (item.getVisibility() == View.GONE) continue;
            boolean footer = item.getId() == footerItemId;
            int itemTop = footer ? footerTop(height, inset, itemHeight, cameraTop, cameraBottom)
                                 : skipCamera(y, itemHeight, cameraTop, cameraBottom);
            item.measure(MeasureSpec.makeMeasureSpec(width, MeasureSpec.EXACTLY),
                         MeasureSpec.makeMeasureSpec(itemHeight, MeasureSpec.EXACTLY));
            item.layout(0, itemTop, width, itemTop + itemHeight);
            if (!footer) y = itemTop + itemHeight;
        }
    }
}
