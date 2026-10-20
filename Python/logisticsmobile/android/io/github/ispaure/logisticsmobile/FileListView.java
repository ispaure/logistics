package io.github.ispaure.logisticsmobile;

import android.content.Context;
import android.graphics.Bitmap;
import android.text.TextUtils;
import android.util.SparseArray;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

/** A viewport-sized pool of rows. No Python callbacks are needed to bind text. */
public final class FileListView extends ListView {
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
    private int textColor, mutedColor, surfaceColor, selectedTextColor, selectedColor, accentColor;

    public FileListView(Context context) {
        super(context);
        setAdapter(rows);
        setChoiceMode(CHOICE_MODE_SINGLE);
        setDividerHeight(0);
        setRecyclerListener(view -> scrub(view));
        setOnItemClickListener((parent, view, position, id) -> {
            selectRow(position);
            if (listener != null) listener.onActivate(position, generation);
        });
        setOnItemLongClickListener((parent, view, position, id) -> {
            selectRow(position);
            if (listener != null) listener.onContext(position, generation);
            return true;
        });
    }

    public void setListener(Listener value) { listener = value; }
    public void setObserveRows(boolean enabled) { observeRows = enabled; }
    public void setPalette(int text, int muted, int surface, int selectedText, int selected, int accent) {
        textColor = text;
        mutedColor = muted;
        surfaceColor = surface;
        selectedTextColor = selectedText;
        selectedColor = selected;
        accentColor = accent;
        setBackgroundColor(surface);
        invalidateViews();
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

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void scrub(View view) {
        Holder holder = (Holder) view.getTag();
        if (holder == null) return;
        holder.title.setText("");
        holder.subtitle.setText("");
        holder.icon.setImageDrawable(null);
        holder.chevron.setText("");
        view.setContentDescription("");
    }

    private void paint(View view, boolean selected) {
        Holder holder = (Holder) view.getTag();
        int foreground = selected ? selectedTextColor : textColor;
        view.setBackgroundColor(selected ? selectedColor : surfaceColor);
        holder.title.setTextColor(foreground);
        holder.subtitle.setTextColor(selected ? foreground : mutedColor);
        holder.chevron.setTextColor(selected ? foreground : mutedColor);
        if (holder.preview) holder.icon.clearColorFilter();
        else holder.icon.setColorFilter(selected ? foreground : accentColor);
    }

    private static final class Holder {
        ImageView icon;
        TextView title, subtitle, chevron;
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
                row.setLayoutParams(new ListView.LayoutParams(-1, dp(56)));
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
                holder.title.setTextSize(16);
                holder.subtitle = new TextView(getContext());
                holder.subtitle.setSingleLine(true);
                holder.subtitle.setTextSize(12);
                text.addView(holder.title);
                text.addView(holder.subtitle);
                row.addView(text, new LinearLayout.LayoutParams(0, -2, 1));
                holder.chevron = new TextView(getContext());
                holder.chevron.setTextSize(22);
                row.addView(holder.chevron, new LinearLayout.LayoutParams(dp(18), -2));
                row.setTag(holder);
                recycled = row;
            } else holder = (Holder) recycled.getTag();
            holder.title.setText(titles[position]);
            holder.subtitle.setText(subtitles[position]);
            holder.subtitle.setVisibility(subtitles[position].isEmpty() ? View.GONE : View.VISIBLE);
            holder.icon.setImageBitmap(thumbnails.get(position,
                    folders[position] ? folderIcon : fileIcon));
            holder.preview = thumbnails.get(position) != null;
            holder.chevron.setText(folders[position] ? "›" : "");
            recycled.setActivated(isItemChecked(position));
            paint(recycled, isItemChecked(position));
            recycled.setContentDescription(titles[position] + (folders[position] ? ". Folder" : ". File"));
            if (listener != null && observeRows) listener.onVisible(position, generation);
            return recycled;
        }
    }
}
