package io.github.ispaure.logisticsmobile;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.text.TextUtils;
import android.util.SparseArray;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

/** A viewport-sized pool of rows. No Python callbacks are needed to bind text. */
public final class FileListView extends ListView {
    // Native dp/sp, matching logisticsmobile.ui_metrics (no Toga font conversion).
    private static final int ROW_HEIGHT = 48;
    private static final int BODY_TEXT = 17, CAPTION_TEXT = 13;
    public interface Listener {
        void onActivate(int index, int generation);
        void onVisible(int index, int generation);
        void onContext(int index, int generation);
    }

    private Listener listener;
    private String[] titles = new String[0], subtitles = new String[0];
    private boolean[] folders = new boolean[0];
    private int generation;
    private Bitmap folderIcon, fileIcon;
    private final SparseArray<Bitmap> thumbnails = new SparseArray<>();
    private final Rows rows = new Rows();
    private int createdRows;
    private boolean observeRows;
    private boolean contextActions;
    private String rowKind = "File";
    private int textColor, mutedColor, surfaceColor, selectedTextColor, selectedColor, accentColor;
    private final Paint outline = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint rowDivider = new Paint();
    private boolean outlined;
    private final Path groupClip = new Path();
    private final RectF groupBounds = new RectF();

    public FileListView(Context context) {
        super(context);
        // Reserve the scrollbar width plus a small gap outside the row outlines.
        setScrollBarStyle(View.SCROLLBARS_OUTSIDE_INSET);
        setPadding(0, 0, dp(4), 0);
        setAdapter(rows);
        setChoiceMode(CHOICE_MODE_SINGLE);
        setHeaderDividersEnabled(false);
        setFooterDividersEnabled(false);
        setDivider(null);
        setDividerHeight(dp(1));
        setRecyclerListener(view -> scrub(view));
        setOnItemClickListener((parent, view, position, id) -> {
            selectRow(position);
            if (listener != null) listener.onActivate(position, generation);
        });
        setOnItemLongClickListener((parent, view, position, id) -> {
            if (!contextActions || !isEnabled()) return false;
            selectRow(position);
            if (listener != null) listener.onContext(position, generation);
            return true;
        });
    }

    public void setListener(Listener value) { listener = value; }
    public void setObserveRows(boolean enabled) { observeRows = enabled; }
    public void setContextActions(boolean enabled) {
        contextActions = enabled;
        invalidateViews();
    }
    public void setRowKind(String kind) { rowKind = kind; }
    public void setPalette(int text, int muted, int surface, int selectedText, int selected, int accent, int border, boolean highContrast) {
        textColor = text;
        mutedColor = muted;
        surfaceColor = surface;
        selectedTextColor = selectedText;
        selectedColor = selected;
        accentColor = accent;
        // Empty space below a short group belongs to the surrounding page.
        setBackgroundColor(android.graphics.Color.TRANSPARENT);
        rowDivider.setColor(border);
        outlined = highContrast;
        outline.setColor(border);
        outline.setStrokeWidth(dp(1));
        outline.setStyle(Paint.Style.STROKE);
        invalidateViews();
        invalidate();
    }

    private boolean clipGroup(Canvas canvas) {
        if (getChildCount() == 0) return false;
        float bottom = Math.min(getHeight(), getChildAt(getChildCount() - 1).getBottom());
        groupBounds.set(getListPaddingLeft(), 0, getWidth() - getListPaddingRight(), bottom);
        groupClip.reset();
        float radius = dp(16);
        groupClip.addRoundRect(groupBounds, radius, radius, Path.Direction.CW);
        canvas.clipPath(groupClip);
        return true;
    }

    @Override protected void onDraw(Canvas canvas) {
        int saved = canvas.save();
        if (clipGroup(canvas)) {
            canvas.drawColor(surfaceColor);
            super.onDraw(canvas);
        }
        canvas.restoreToCount(saved);
    }

    @Override protected void dispatchDraw(Canvas canvas) {
        int saved = canvas.save();
        if (clipGroup(canvas)) {
            super.dispatchDraw(canvas);
            for (int i = 0; i < getChildCount(); i++) {
                // Dataset position, not viewport position: never underline the
                // last item, including short, single-row and scrolled lists.
                if (getFirstVisiblePosition() + i >= titles.length - 1) break;
                int bottom = getChildAt(i).getBottom();
                canvas.drawRect(getListPaddingLeft() + dp(8), bottom,
                        getWidth() - getListPaddingRight() - dp(8),
                        bottom + getDividerHeight(), rowDivider);
            }
        }
        canvas.restoreToCount(saved);
        if (outlined && getChildCount() > 0) {
            // Enclose short lists at their last row; long lists frame the viewport.
            float halfStroke = outline.getStrokeWidth() / 2f;
            float bottom = Math.min(getHeight(), getChildAt(getChildCount() - 1).getBottom());
            canvas.drawRoundRect(getListPaddingLeft() + halfStroke, halfStroke,
                    getWidth() - getListPaddingRight() - halfStroke,
                    bottom - halfStroke, dp(16) - halfStroke, dp(16) - halfStroke, outline);
        }
    }
    public void setRows(String[] names, String[] descriptions, boolean[] directories, int revision) {
        // Invalidate both attached and scrapped cells so private names/icons
        // cannot survive a lock, close, or provider change in the recycler.
        for (int i = 0; i < getChildCount(); i++) scrub(getChildAt(i));
        titles = names;
        subtitles = descriptions;
        folders = directories;
        generation = revision;
        thumbnails.clear();
        clearChoices();
        rows.notifyDataSetChanged();
        setSelection(0);
        invalidateViews();
    }

    public void setIcons(Bitmap folder, Bitmap file) {
        folderIcon = folder;
        fileIcon = file;
    }

    public void setRowIcon(int index, Bitmap image, int revision) {
        if (revision != generation || index < 0 || index >= titles.length) return;
        if (image == null) thumbnails.remove(index);
        else thumbnails.put(index, image);
        // Keep decoded previews bounded; ordinary rows share two bitmaps.
        while (thumbnails.size() > 64) thumbnails.removeAt(0);
        int visible = index - getFirstVisiblePosition();
        if (visible >= 0 && visible < getChildCount()) {
            Holder holder = (Holder) getChildAt(visible).getTag();
            holder.preview = image != null;
            holder.icon.setImageBitmap(image != null ? image : (folders[index] ? folderIcon : fileIcon));
            paint(getChildAt(visible), isItemChecked(index));
        }
    }

    public void selectRow(int position) {
        clearChoices();
        if (position >= 0 && position < titles.length) setItemChecked(position, true);
        for (int i = 0; i < getChildCount(); i++) {
            View view = getChildAt(i);
            boolean selected = getFirstVisiblePosition() + i == position;
            view.setActivated(selected);
            paint(view, selected);
        }
    }

    public int getCreatedRowCount() { return createdRows; }

    public int getVerticalPosition() {
        View first = getChildAt(0);
        return first == null ? 0 : Math.max(0,
                getFirstVisiblePosition() * rowStride() - first.getTop() + getPaddingTop());
    }

    public int getMaxVerticalPosition() {
        return Math.max(0, titles.length * dp(ROW_HEIGHT)
                + Math.max(0, titles.length - 1) * getDividerHeight() - getHeight()
                + getPaddingTop() + getPaddingBottom());
    }

    public void setVerticalPosition(int value) {
        int position = Math.max(0, Math.min(value, getMaxVerticalPosition()));
        int height = rowStride();
        setSelectionFromTop(position / height, -(position % height));
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private int rowStride() {
        return dp(ROW_HEIGHT) + getDividerHeight();
    }

    private void scrub(View view) {
        Holder holder = (Holder) view.getTag();
        if (holder == null) return;
        holder.title.setText("");
        holder.subtitle.setText("");
        holder.icon.setImageDrawable(null);
        holder.actions.setOnClickListener(null);
        holder.actions.setContentDescription("");
        view.setContentDescription("");
    }

    private void paint(View view, boolean selected) {
        Holder holder = (Holder) view.getTag();
        int foreground = selected ? selectedTextColor : textColor;
        view.setBackgroundColor(selected ? selectedColor : surfaceColor);
        holder.title.setTextColor(foreground);
        holder.subtitle.setTextColor(selected ? foreground : mutedColor);
        holder.actions.setTextColor(selected ? foreground : accentColor);
        if (holder.preview) holder.icon.clearColorFilter();
        else holder.icon.setColorFilter(selected ? foreground : accentColor);
    }

    private static final class Holder {
        ImageView icon;
        TextView title, subtitle, actions;
        boolean preview;
    }

    private final class Rows extends BaseAdapter {
        @Override public int getCount() { return titles.length; }
        @Override public Object getItem(int position) { return titles[position]; }
        @Override public long getItemId(int position) { return position; }

        @Override public View getView(int position, View recycled, ViewGroup parent) {
            Holder holder;
            if (recycled == null) {
                createdRows++;
                LinearLayout row = new LinearLayout(getContext());
                row.setGravity(Gravity.CENTER_VERTICAL);
                row.setPadding(dp(8), 0, dp(8), 0);
                row.setLayoutParams(new ListView.LayoutParams(-1, dp(ROW_HEIGHT)));
                android.util.TypedValue background = new android.util.TypedValue();
                getContext().getTheme().resolveAttribute(android.R.attr.activatedBackgroundIndicator,
                        background, true);
                if (background.resourceId != 0) row.setBackgroundResource(background.resourceId);
                holder = new Holder();
                holder.icon = new ImageView(getContext());
                holder.icon.setScaleType(ImageView.ScaleType.FIT_CENTER);
                holder.icon.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
                row.addView(holder.icon, new LinearLayout.LayoutParams(dp(28), dp(28)));
                LinearLayout text = new LinearLayout(getContext());
                text.setOrientation(LinearLayout.VERTICAL);
                text.setPadding(dp(12), 0, dp(8), 0);
                holder.title = new TextView(getContext());
                holder.title.setSingleLine(true);
                holder.title.setEllipsize(TextUtils.TruncateAt.MIDDLE);
                holder.title.setTextSize(BODY_TEXT);
                holder.subtitle = new TextView(getContext());
                holder.subtitle.setSingleLine(true);
                holder.subtitle.setTextSize(CAPTION_TEXT);
                text.addView(holder.title);
                text.addView(holder.subtitle);
                row.addView(text, new LinearLayout.LayoutParams(0, -2, 1));
                holder.actions = new Button(getContext(), null, android.R.attr.borderlessButtonStyle);
                holder.actions.setText("⋯");
                holder.actions.setTextSize(24);
                holder.actions.setGravity(Gravity.CENTER);
                holder.actions.setFocusable(false);
                holder.actions.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
                row.addView(holder.actions, new LinearLayout.LayoutParams(dp(ROW_HEIGHT), -1));
                row.setTag(holder);
                recycled = row;
            } else holder = (Holder) recycled.getTag();
            holder.title.setText(titles[position]);
            holder.subtitle.setText(subtitles[position]);
            holder.subtitle.setVisibility(subtitles[position].isEmpty() ? View.GONE : View.VISIBLE);
            holder.icon.setImageBitmap(thumbnails.get(position,
                    folders[position] ? folderIcon : fileIcon));
            holder.preview = thumbnails.get(position) != null;
            holder.actions.setVisibility(contextActions ? View.VISIBLE : View.GONE);
            holder.actions.setContentDescription("Select " + titles[position]);
            final int revision = generation;
            holder.actions.setOnClickListener(view -> {
                if (contextActions && FileListView.this.isEnabled() && generation == revision && listener != null) {
                    selectRow(position);
                    listener.onContext(position, revision);
                }
            });
            recycled.setActivated(isItemChecked(position));
            paint(recycled, isItemChecked(position));
            recycled.setContentDescription(titles[position] + (folders[position] ? ". Folder" : ". " + rowKind));
            if (listener != null && observeRows) listener.onVisible(position, generation);
            return recycled;
        }
    }
}
