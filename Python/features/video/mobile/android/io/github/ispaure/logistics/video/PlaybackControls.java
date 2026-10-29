package io.github.ispaure.logistics.video;

import android.app.AlertDialog;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.net.Uri;
import android.os.SystemClock;
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
    private final Button unlock, undo;
    private final CacheStrip cache;
    private long undoPosition, undoUntil;

    PlaybackControls(VideoPlayer owner, View tapSurface) {
        this.owner = owner;
        cache = new CacheStrip();
        owner.controls.addView(cache, new android.widget.LinearLayout.LayoutParams(-1, owner.dp(3)));
        undo = new Button(owner.activity); undo.setText("Undo seek");
        undo.setOnClickListener(v -> undo());
        owner.controls.addView(undo); undo.setVisibility(View.GONE);
        unlock = new Button(owner.activity); unlock.setText("Unlock controls");
        FrameLayout.LayoutParams frame = new FrameLayout.LayoutParams(-2, owner.dp(48), Gravity.BOTTOM | Gravity.END);
        frame.setMargins(16, 16, 16, 32);
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
            owner.setVideoHeader(settings.optString("video_title"), settings.optString("source_label"), settings.optBoolean("source_remote"));
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
        owner.player.setRate((float) settings.optDouble("rate", 1));
        owner.player.setAudioDelay(settings.optLong("audio_delay_ms") * 1000);
        owner.player.setSpuDelay(settings.optLong("subtitle_delay_ms") * 1000);
        String aspect = settings.optString("aspect", "fit");
        owner.player.setVideoScale(aspect.equals("fill") ? MediaPlayer.ScaleType.SURFACE_FIT_SCREEN :
            aspect.equals("original") ? MediaPlayer.ScaleType.SURFACE_ORIGINAL : MediaPlayer.ScaleType.SURFACE_BEST_FIT);
    }
    void setting(String key, Object value) {
        try {
            JSONObject next = new JSONObject(settings.toString()); next.put(key, value);
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
        choose("Playback", new String[] {"Go to time…", "Start over", "Undo seek", "Speed…", "Picture size…",
            "Subtitles and audio…", "Current folder…", "Previous episode", "Next episode",
            (settings.optBoolean("autoplay_next") ? "✓ " : "") + "Play next automatically", "Mute / unmute", "Lock controls", "Show in folder"}, index -> {
            switch (index) {
                case 0: prompt("Seconds, MM:SS or HH:MM:SS", "", "seek"); break;
                case 1: owner.seekTo(0); break;
                case 2: undo(); break;
                case 3:
                    double[] rates = {.5, .75, 1, 1.25, 1.5, 1.75, 2};
                    String[] labels = {"0.5×", "0.75×", "1×", "1.25×", "1.5×", "1.75×", "2×"};
                    choose("Speed · pitch preserved", labels, i -> setting("rate", rates[i])); break;
                case 4: choose("Picture size", new String[] {"Fit", "Fill (crop edges)", "Original size"},
                    i -> setting("aspect", new String[] {"fit", "fill", "original"}[i])); break;
                case 5: subtitles(); break;
                case 6:
                    String[] names = new String[queue.length()];
                    for (int i=0; i<names.length; i++) names[i] = queue.optJSONObject(i).optString("name");
                    choose("Current folder", names, i -> emit("queue", queue.optJSONObject(i).optString("path"))); break;
                case 7: emit("previous", ""); break;
                case 8: emit("next", ""); break;
                case 9: setting("autoplay_next", !settings.optBoolean("autoplay_next")); break;
                case 10: mute(); break;
                case 11: lock(true); break;
                case 12: emit("showInFolder", ""); break;
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
    void rememberSeek(long target) {
        if (Math.abs(target - owner.position()) >= 10000) {
            undoPosition = owner.position(); undoUntil = SystemClock.elapsedRealtime() + 8000;
            undo.setVisibility(View.VISIBLE);
            owner.handler.postDelayed(() -> { if (SystemClock.elapsedRealtime() >= undoUntil) undo.setVisibility(View.GONE); }, 8100);
        }
    }
    void undo() {
        if (SystemClock.elapsedRealtime() <= undoUntil) {
            long position = undoPosition; undoUntil = 0; owner.seekTo(position); undoUntil = 0; undo.setVisibility(View.GONE);
        }
    }
    void lock(boolean value) {
        if (!owner.allowed(false)) return;
        locked = value; unlock.setVisibility(value ? View.VISIBLE : View.GONE);
        owner.seek.setEnabled(!value); owner.setControlsVisible(!value); unlock.bringToFront();
    }
    void mute() { owner.toggleMute(); }
    void cached(String json) {
        try { JSONObject value = new JSONObject(json); cacheApproximate = !value.optBoolean("local"); cache.ranges = value.optBoolean("local") ? new JSONArray("[[0,1]]") : value.optJSONArray("ranges"); cache.invalidate(); }
        catch (Exception ignored) { cache.ranges = null; cache.invalidate(); }
    }
    private final class CacheStrip extends View {
        JSONArray ranges;
        final Paint paint = new Paint();
        CacheStrip() { super(owner.activity); paint.setColor(0xff72c3ad); setContentDescription("Approximate cached byte ranges; variable bitrate can shift time mapping"); }
        @Override protected void onDraw(Canvas canvas) {
            if (ranges == null) return;
            float width = Math.max(0, getWidth() - owner.dp(32));
            for (int i=0;i<ranges.length();i++) {
                JSONArray range = ranges.optJSONArray(i); if (range == null || range.length() != 2) continue;
                canvas.drawRect(owner.dp(16)+(float)range.optDouble(0)*width, 0,
                    owner.dp(16)+(float)range.optDouble(1)*width, getHeight(), paint);
            }
        }
    }
}
