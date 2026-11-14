package io.github.ispaure.logistics.video;

import android.app.AlertDialog;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.net.Uri;
import android.view.GestureDetector;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import org.json.JSONArray;
import org.json.JSONObject;
import org.videolan.libvlc.Media;
import org.videolan.libvlc.MediaPlayer;

/** Playback tools kept separate from decoder, privacy and audio-focus lifetime. */
final class PlaybackControls {
    final VideoPlayer owner;
    JSONObject settings = new JSONObject();
    JSONArray queue = new JSONArray();
    boolean locked, cacheApproximate;
    private final Button unlock;
    private final CacheStrip cache;

    PlaybackControls(VideoPlayer owner, View tapSurface) {
        this.owner = owner;
        cache = new CacheStrip();
        cache.setVisibility(View.GONE);
        owner.controls.addView(cache, owner.controls.indexOfChild(owner.seek) + 1,
            new android.widget.LinearLayout.LayoutParams(-1, owner.dp(3)));
        unlock = new Button(owner.activity); unlock.setText("Unlock controls");
        FrameLayout.LayoutParams frame = new FrameLayout.LayoutParams(-2, owner.dp(48), Gravity.BOTTOM | Gravity.END);
        owner.root.addView(unlock, frame); unlock.setVisibility(View.GONE);
        unlock.setOnClickListener(v -> lock(false));
        GestureDetector gestures = new GestureDetector(owner.activity, new GestureDetector.SimpleOnGestureListener() {
            @Override public boolean onDown(android.view.MotionEvent event) { return true; }
            @Override public boolean onSingleTapConfirmed(android.view.MotionEvent event) {
                if (!locked) tapSurface.performClick();
                return true;
            }
            @Override public boolean onDoubleTap(android.view.MotionEvent event) {
                if (locked || !owner.allowed(false)) return true;
                float fraction = event.getX() / Math.max(1, tapSurface.getWidth());
                if (fraction < .4) owner.seekTo(owner.position() - 10000);
                else if (fraction > .6) owner.seekTo(owner.position() + 10000);
                else owner.togglePlayback();
                return true;
            }
        });
        tapSurface.setOnTouchListener((v, event) -> gestures.onTouchEvent(event));
        owner.root.setFocusableInTouchMode(true); owner.root.requestFocus();
        owner.root.setOnKeyListener((v, code, event) -> {
            if (event.getAction() != KeyEvent.ACTION_UP || !owner.allowed(false)) return false;
            if (code == KeyEvent.KEYCODE_ESCAPE) { if (locked) lock(false); else owner.setFullscreen(false); return true; }
            if (locked) return true;
            switch (code) {
                case KeyEvent.KEYCODE_SPACE: case KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE: owner.togglePlayback(); break;
                case KeyEvent.KEYCODE_DPAD_LEFT: owner.seekTo(owner.position() - 10000); break;
                case KeyEvent.KEYCODE_DPAD_RIGHT: owner.seekTo(owner.position() + 10000); break;
                case KeyEvent.KEYCODE_M: mute(); break;
                case KeyEvent.KEYCODE_G: prompt("Go to time", "", "seek"); break;
                case KeyEvent.KEYCODE_N: emit("next", ""); break;
                case KeyEvent.KEYCODE_P: emit("previous", ""); break;
                case KeyEvent.KEYCODE_F: owner.setFullscreen(!owner.fullscreen); break;
                default: return false;
            }
            return true;
        });
    }

    void layoutUnlock(FrameLayout.LayoutParams controls) {
        FrameLayout.LayoutParams frame = (FrameLayout.LayoutParams) unlock.getLayoutParams();
        frame.setMargins(controls.leftMargin, controls.topMargin, controls.rightMargin, controls.bottomMargin);
        unlock.setLayoutParams(frame);
    }

    void emit(String name, String value) {
        if (owner.allowed(false) && owner.listener != null) owner.listener.command(name, value);
    }
    void configure(String options, String rows) {
        try {
            JSONObject updated = new JSONObject(options);
            boolean reload = !updated.optString("audio_language").equals(settings.optString("audio_language"))
                || !updated.optString("subtitle_language").equals(settings.optString("subtitle_language"))
                || updated.optDouble("subtitle_scale", 1) != settings.optDouble("subtitle_scale", 1);
            settings = updated; queue = new JSONArray(rows);
            owner.setVideoHeader(settings.optString("video_title"), settings.optString("video_path"), settings.optString("source_label"), settings.optBoolean("source_remote"));
            cache.setVisibility(settings.optBoolean("source_remote") ? View.VISIBLE : View.GONE);
            if (!settings.optBoolean("source_remote")) cacheApproximate = false;
            if (reload) owner.reloadPlaybackOptions();
            apply();
        } catch (Exception error) { owner.status("Invalid playback preferences."); }
    }
    void mediaOptions(Media media) {
        media.addOption(":audio-time-stretch");
        for (String[] entry : new String[][] {{"audio_language", "audio-language"}, {"subtitle_language", "sub-language"}}) {
            String value = settings.optString(entry[0]);
            if (value.matches("[a-zA-Z-]{1,16}")) media.addOption(":" + entry[1] + "=" + value);
        }
        media.addOption(":freetype-rel-fontsize=" + Math.round(16 / settings.optDouble("subtitle_scale", 1)));
    }
    void apply() {
        if (!settings.isNull("subtitle_track")) owner.pendingSubtitleURL = null;
        if (owner.pendingSubtitleURL != null) owner.attachSubtitleURL(owner.pendingSubtitleURL);
        int audio = resolveTrack("audio_track", owner.player.getAudioTracks(), false);
        int text = resolveTrack("subtitle_track", owner.player.getSpuTracks(), true);
        if (audio != Integer.MIN_VALUE && owner.player.getAudioTrack() != audio) owner.player.setAudioTrack(audio);
        if (text != Integer.MIN_VALUE && owner.player.getSpuTrack() != text) owner.selectSubtitleTrack(text);
        owner.player.setRate((float) settings.optDouble("rate", 1));
        owner.player.setAudioDelay(settings.optLong("audio_delay_ms") * 1000);
        owner.player.setSpuDelay(settings.optLong("subtitle_delay_ms") * 1000);
        String aspect = settings.optString("aspect", "fit");
        owner.player.setVideoScale(aspect.equals("fill") ? MediaPlayer.ScaleType.SURFACE_FIT_SCREEN :
            aspect.equals("original") ? MediaPlayer.ScaleType.SURFACE_ORIGINAL : MediaPlayer.ScaleType.SURFACE_BEST_FIT);
    }
    private int resolveTrack(String field, MediaPlayer.TrackDescription[] tracks, boolean text) {
        int id = settings.optInt(field, Integer.MIN_VALUE);
        if (id == -1) return id;
        String key = settings.optString(field + "_key", "");
        int match = Integer.MIN_VALUE;
        if (tracks != null) for (MediaPlayer.TrackDescription track : tracks) {
            if (track.id < 0) continue;
            if (key.isEmpty() ? track.id != id : !key.equals(owner.trackKey(track, text))) continue;
            if (match != Integer.MIN_VALUE) return Integer.MIN_VALUE;
            match = track.id;
        }
        return match;
    }
    void selectTrack(String field, int id, String key) {
        try {
            JSONObject next = new JSONObject();
            next.put(field, id);
            next.put(field + "_key", key);
            if (field.equals("subtitle_track")) next.put("subtitle_file", "");
            emit("settings", next.toString());
        } catch (Exception error) { owner.status("Invalid playback track."); }
    }
    void setting(String key, Object value) {
        try {
            JSONObject next = new JSONObject(); next.put(key, value);
            emit("settings", next.toString());
        } catch (Exception error) { owner.status("Invalid playback preference."); }
    }
    void choose(String title, String[] labels, java.util.function.IntConsumer action) {
        owner.showPlaybackDialog(new AlertDialog.Builder(owner.activity).setTitle(title)
            .setItems(labels, (dialog, index) -> action.accept(index)).setNegativeButton("Cancel", null).create());
    }
    void prompt(String title, String initial, String key) {
        EditText field = new EditText(owner.activity); field.setSingleLine(true); field.setText(initial);
        owner.showPlaybackDialog(new AlertDialog.Builder(owner.activity).setTitle(title).setView(field)
            .setPositiveButton("Apply", (dialog, index) -> {
                String text = field.getText().toString().trim();
                if (key.equals("seek")) { emit("seek", text); return; }
                try { setting(key, key.endsWith("_ms") ? Long.valueOf(text) : text); }
                catch (NumberFormatException error) { owner.status("Enter a delay in milliseconds."); }
            }).setNegativeButton("Cancel", null).create());
    }
    void show() {
        if (!owner.allowed(false) || locked) return;
        choose("Playback", new String[] {"Go to time…", "Start over", "Speed…", "Picture size…",
            "Subtitles and audio…", "Current folder…", "Previous episode", "Next episode",
            (settings.optBoolean("autoplay_next") ? "✓ " : "") + "Play next automatically", "Mute / unmute", "Lock controls", "Show in folder", "Favourite file"}, index -> {
            switch (index) {
                case 0: prompt("Seconds, MM:SS or HH:MM:SS", "", "seek"); break;
                case 1: owner.seekTo(0); break;
                case 2:
                    double[] rates = {.5, .75, 1, 1.25, 1.5, 1.75, 2};
                    String[] labels = {"0.5×", "0.75×", "1×", "1.25×", "1.5×", "1.75×", "2×"};
                    choose("Speed · pitch preserved", labels, i -> setting("rate", rates[i])); break;
                case 3: choose("Picture size", new String[] {"Fit", "Fill (crop edges)", "Original size"},
                    i -> setting("aspect", new String[] {"fit", "fill", "original"}[i])); break;
                case 4: subtitles(); break;
                case 5:
                    String[] names = new String[queue.length()];
                    for (int i=0; i<names.length; i++) names[i] = queue.optJSONObject(i).optString("name");
                    choose("Current folder", names, i -> emit("queue", queue.optJSONObject(i).optString("path"))); break;
                case 6: emit("previous", ""); break;
                case 7: emit("next", ""); break;
                case 8: setting("autoplay_next", !settings.optBoolean("autoplay_next")); break;
                case 9: mute(); break;
                case 10: lock(true); break;
                case 11: emit("showInFolder", ""); break;
                case 12: emit("favourite", ""); break;
            }
        });
    }
    void subtitles() {
        choose("Subtitles and audio", new String[] {"Choose subtitle file…", "Subtitle size…", "Subtitle delay (ms; positive = later)",
            "Audio delay (ms; positive = later)", "Preferred audio language (e.g. fr)", "Preferred subtitle language (e.g. en)"}, index -> {
            if (index == 0) emit("subtitleBrowse", "");
            else if (index == 1) choose("Subtitle size", new String[] {"0.75×", "1×", "1.25×", "1.5×", "2×"},
                i -> setting("subtitle_scale", new double[] {.75, 1, 1.25, 1.5, 2}[i]));
            else {
                String key = new String[] {"", "", "subtitle_delay_ms", "audio_delay_ms", "audio_language", "subtitle_language"}[index];
                prompt(index < 4 ? "Delay in ms; positive = later" : "Language code; blank = default", settings.optString(key), key);
            }
        });
    }
    void browser(String json) {
        if (!owner.allowed(false)) return;
        try {
            JSONArray rows = new JSONArray(json); String[] labels = new String[rows.length()];
            for (int i=0;i<labels.length;i++) { JSONObject row=rows.getJSONObject(i); labels[i]=(row.optBoolean("directory") ? "▸ " : "")+row.optString("name"); }
            choose("Choose subtitles · current source", labels, index -> {
                JSONObject row=rows.optJSONObject(index);
                emit(row.optBoolean("directory") ? "subtitleBrowse" : "subtitleAttach", row.optString("path"));
            });
        } catch (Exception error) { owner.status("Could not list subtitle files."); }
    }
    void lock(boolean value) {
        if (!owner.allowed(false)) return;
        locked = value; unlock.setVisibility(value ? View.VISIBLE : View.GONE);
        owner.seek.setEnabled(!value); owner.setControlsVisible(!value); unlock.bringToFront();
    }
    void mute() { owner.toggleMute(); }
    void cached(String json) {
        try {
            JSONObject value = new JSONObject(json);
            boolean local = value.optBoolean("local") || !settings.optBoolean("source_remote");
            cacheApproximate = !local && value.optBoolean("approximate", true);
            cache.setVisibility(local ? View.GONE : View.VISIBLE);
            cache.ranges = local ? null : value.optJSONArray("ranges");
            cache.setContentDescription(cacheApproximate ? "Approximate cached file ranges" : "Timestamp indexed cached ranges");
            cache.invalidate();
        }
        catch (Exception ignored) { cache.ranges = null; cache.invalidate(); }
    }
    private final class CacheStrip extends View {
        JSONArray ranges;
        final Paint paint = new Paint(3);
        CacheStrip() { super(owner.activity); paint.setColor(0xff72c3ad); setContentDescription("Approximate cached byte ranges; variable bitrate can shift time mapping"); }
        @Override protected void onDraw(Canvas canvas) {
            // Draw the whole timeline grey, with only cached ranges green.
            // SeekBar progress travels between its padded thumb centres.
            float left = owner.seek.getX() + owner.seek.getPaddingLeft() - getX();
            float right = owner.seek.getX() + owner.seek.getWidth() - owner.seek.getPaddingRight() - getX();
            if (right <= left) { left = 0; right = getWidth(); }
            float width = right - left;
            paint.setColor(0xff888888);
            canvas.drawRect(left, 0, right, getHeight(), paint);
            paint.setColor(0xff35bf77);
            if (ranges == null) return;
            for (int i=0;i<ranges.length();i++) {
                JSONArray range = ranges.optJSONArray(i); if (range == null || range.length() != 2) continue;
                double start = range.optDouble(0, Double.NaN), end = range.optDouble(1, Double.NaN);
                if (!Double.isFinite(start) || !Double.isFinite(end) || end < start) continue;
                canvas.drawRect(left+(float)Math.max(0, Math.min(1, start))*width, 0,
                    left+(float)Math.max(0, Math.min(1, end))*width, getHeight(), paint);
            }
        }
    }
}
