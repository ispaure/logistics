package io.github.ispaure.logisticsmobile;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import com.google.android.material.navigationrail.NavigationRailView;
import com.google.android.material.shape.ShapeAppearanceModel;

/** Desktop-style placement while retaining Material selection and accessibility. */
public final class DestinationRailView extends NavigationRailView {
    private int footerItemId;
    private final Paint dividerPaint = new Paint();

    public DestinationRailView(Context context, int footerItemId) {
        super(context);
        this.footerItemId = footerItemId;
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
            int itemTop = item.getId() == footerItemId ? height - inset - itemHeight : y;
            item.measure(MeasureSpec.makeMeasureSpec(width, MeasureSpec.EXACTLY),
                         MeasureSpec.makeMeasureSpec(itemHeight, MeasureSpec.EXACTLY));
            item.layout(0, itemTop, width, itemTop + itemHeight);
            if (item.getId() != footerItemId) y += itemHeight;
        }
    }
}
