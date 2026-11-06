package io.github.ispaure.logistics.video;

import android.app.Activity;
import android.app.RemoteAction;
import android.app.PictureInPictureParams;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.Handler;
import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.widget.FrameLayout;
import android.widget.ImageButton;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.file.Files;
import java.util.List;

/** Compiled with the unchanged production player; only synthetic local media. */
public final class VideoPipQAActivity extends Activity {
    private VideoPlayer video;
    private PictureInPictureParams submittedParams;
    private final Handler handler = new Handler();
    private final JSONArray samples = new JSONArray();
    private int stage = -1;
    private long started, stageAt, before, target, lastPlayAttempt;
    private int playAttempts;
    private boolean waiting, completed;
    private int subtitleTrack;
    private String pausedCapture;
    private File file(String name) { return new File(getCacheDir(), name); }
    private void next() { stage++; stageAt = SystemClock.uptimeMillis(); }
    private void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
    @Override public boolean enterPictureInPictureMode(PictureInPictureParams params) {
        submittedParams = params;
        return super.enterPictureInPictureMode(params);
    }
    @Override public void setPictureInPictureParams(PictureInPictureParams params) {
        submittedParams = params;
        super.setPictureInPictureParams(params);
    }
    private List<RemoteAction> actions() { return submittedParams.getActions(); }
    private void action(int index) throws Exception { actions().get(index).getActionIntent().send(); }
    private void capture(String name) throws Exception {
        Rect bounds = getWindowManager().getCurrentWindowMetrics().getBounds();
        JSONObject value = new JSONObject().put("name", name).put("bounds", new JSONArray(new int[]{bounds.left,bounds.top,bounds.right,bounds.bottom}))
            .put("clock", video.player.getTime()).put("subtitleTrack", video.player.getSpuTrack());
        Files.write(file("pip-capture.json").toPath(), value.toString().getBytes());
        waiting = true;
    }
    private void sample(String event) throws Exception {
        samples.put(new JSONObject().put("event", event).put("decoder", video.player.getTime()).put("position", video.position()));
    }
    private ImageButton findIcon(View view, String label) {
        if (view instanceof ImageButton && label.equals(view.getContentDescription())) return (ImageButton)view;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup)view;
            for (int i = 0; i < group.getChildCount(); i++) {
                ImageButton match = findIcon(group.getChildAt(i), label);
                if (match != null) return match;
            }
        }
        return null;
    }
    private void checkFullscreenControls() throws Exception {
        WindowInsets insets = video.root.getRootWindowInsets();
        require(video.controlsVisible && !insets.isVisible(WindowInsets.Type.navigationBars())
            && !insets.isVisible(WindowInsets.Type.statusBars()), "System bars visible over fullscreen controls");
        int bottom = insets.getInsetsIgnoringVisibility(WindowInsets.Type.navigationBars()).bottom;
        video.showCachedRanges("{\"ranges\":[[0,0.6]],\"approximate\":false}");
        View cache = video.controls.getChildAt(video.controls.indexOfChild(video.seek) + 1);
        require("Timestamp indexed cached ranges".contentEquals(cache.getContentDescription()),
            "Cached range strip is separated from the timeline");
        for (String label : new String[]{"Back 10 seconds", "Play", "Forward 10 seconds", "Exit fullscreen"}) {
            ImageButton button = findIcon(video.controls, label);
            require(button != null && button.getDrawable() != null && button.isShown(), "Missing fullscreen icon: " + label);
            int[] position = new int[2];
            button.getLocationOnScreen(position);
            require(button.getHeight() >= video.dp(44)
                && position[1] + button.getHeight() <= video.root.getHeight() - bottom,
                "Fullscreen button overlaps navigation area: " + label);
        }
        sample("fullscreen-controls");
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(new FrameLayout(this));
        try {
            for (String name : new String[]{"fixture.mp4", "captions.srt"}) {
                try (java.io.InputStream input = getAssets().open(name)) {
                    Files.copy(input, file(name).toPath(), java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                }
            }
            video = new VideoPlayer(this, android.net.Uri.fromFile(file("fixture.mp4")).toString(), 0, false, "[]", new VideoPlayer.Listener() {
                public String controlInsets(String metrics) {
                    try {
                        JSONArray safe = new JSONObject(metrics).getJSONArray("safe");
                        return new JSONArray(new int[]{safe.getInt(0) + 8, safe.getInt(1) + 8,
                            safe.getInt(2) + 8, safe.getInt(3)}).toString();
                    } catch (Exception invalid) { return ""; }
                }
                public boolean allowed(boolean external) { return true; }
                public boolean requestPlay() { return true; }
                public void closed() { finish(); }
                public void command(String name, String value) { }
            });
            if (getIntent().getBooleanExtra("software_decode", false)) {
                org.videolan.libvlc.Media media = (org.videolan.libvlc.Media) video.player.getMedia();
                try { media.setHWDecoderEnabled(false, false); media.addOption(":codec=avcodec"); }
                finally { media.release(); }
            }
            video.show();
            video.enterFullscreenWithControls();
        } catch (Throwable error) { result(error); }
    }
    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        // Android 15+ admits audio focus only after the activity is foreground.
        if (focused && video != null && started == 0 && !completed) {
            started = stageAt = SystemClock.uptimeMillis();
            handler.postDelayed(() -> {
                try {
                    samples.put(new JSONObject().put("event", "play-admission")
                        .put("allowed", video.allowed(false)).put("focused", hasWindowFocus())
                        .put("interactive", ((android.os.PowerManager)getSystemService(POWER_SERVICE)).isInteractive())
                        .put("audioMode", ((android.media.AudioManager)getSystemService(AUDIO_SERVICE)).getMode()));
                    checkFullscreenControls();
                    lastPlayAttempt = SystemClock.uptimeMillis(); playAttempts++;
                    video.startByUser(); tick();
                } catch (Throwable error) { result(error); }
            }, 500);
        }
    }
    private boolean playRequested() throws Exception {
        java.lang.reflect.Field requested = VideoPlayer.class.getDeclaredField("playRequested");
        requested.setAccessible(true);
        return requested.getBoolean(video);
    }
    private void tick() {
        if (completed) return;
        try {
            long now = SystemClock.uptimeMillis();
            require(now - started < 90000, "PiP stages timed out at " + stage);
            if (waiting) {
                if (file("pip-capture-done").delete()) {
                    if (stage == 2) action(1);
                    waiting = false; next();
                }
            } else switch (stage) {
                case -1:
                    if (!playRequested() && video.allowed(false) && hasWindowFocus() && now - lastPlayAttempt > 1000) {
                        lastPlayAttempt = now; playAttempts++;
                        video.startByUser();
                    }
                    if (video.player.isPlaying() && video.player.getTime() > 500) {
                        video.setControlsVisible(true);
                        capture("fullscreen");
                    }
                    break;
                case 0:
                    if (video.player.isPlaying()) {
                        video.attachSubtitleURL(android.net.Uri.fromFile(file("captions.srt")).toString()); next();
                    }
                    break;
                case 1:
                    if (video.player.getSpuTracksCount() > 0 && now - stageAt > 800) {
                        video.seekTo(2000);
                        java.lang.reflect.Method pip = VideoPlayer.class.getDeclaredMethod("pip");
                        pip.setAccessible(true); pip.invoke(video); next();
                    }
                    break;
                case 2:
                    Rect pipBounds = getWindowManager().getCurrentWindowMetrics().getBounds();
                    Rect displayBounds = getWindowManager().getMaximumWindowMetrics().getBounds();
                    if ("white".equals(pausedCapture) && !video.player.isPlaying()) {
                        pausedCapture = null; capture("white");
                    } else if (isInPictureInPictureMode() && pipBounds.width() < displayBounds.width()
                            && pipBounds.height() < displayBounds.height() && now - stageAt > 1000) {
                        pausedCapture = "white"; action(1);
                    }
                    break;
                case 3:
                    if (!video.player.isPlaying() || !actions().get(1).getTitle().toString().equals("Pause")) break;
                    require(actions().size() == 3, "PiP did not expose three actions");
                    require(actions().get(0).getTitle().toString().equals("Back 10 seconds") && actions().get(1).getTitle().toString().equals("Pause") && actions().get(2).getTitle().toString().equals("Forward 10 seconds"), "Unexpected PiP actions");
                    for (RemoteAction action : actions()) require(action.isEnabled(), "PiP action was disabled");
                    action(1); next(); break;
                case 4:
                    if (!video.player.isPlaying() && actions().get(1).getTitle().toString().equals("Play")) {
                        before = video.position(); target = before + 10000; action(2); next();
                    }
                    break;
                case 5:
                    if (Math.abs(video.position() - target) < 1000) {
                        require(!video.player.isPlaying(), "Paused PiP seek resumed playback");
                        sample("paused-forward-10s"); action(1); next();
                    }
                    break;
                case 6:
                    if ("yellow".equals(pausedCapture) && !video.player.isPlaying()) {
                        pausedCapture = null; capture("yellow");
                    } else if (video.player.isPlaying() && Math.abs(video.player.getTime() - target) < 2000 && now - stageAt > 800) {
                        pausedCapture = "yellow"; action(1);
                    }
                    break;
                case 7: next(); break;
                case 8:
                    if (!video.player.isPlaying()) { before = video.position(); target = Math.max(0, before - 10000); action(0); next(); }
                    break;
                case 9:
                    if (Math.abs(video.position() - target) < 1000) {
                        require(!video.player.isPlaying(), "Paused backward PiP seek resumed playback");
                        sample("paused-backward-10s"); action(1); next();
                    }
                    break;
                case 10:
                    if ("back".equals(pausedCapture) && !video.player.isPlaying()) {
                        pausedCapture = null; capture("back");
                    } else if (video.player.isPlaying() && Math.abs(video.player.getTime() - target) < 2000 && now - stageAt > 800) {
                        pausedCapture = "back"; action(1);
                    }
                    break;
                case 11:
                    subtitleTrack = video.player.getSpuTrack();
                    require(subtitleTrack >= 0, "Subtitle track was not selected");
                    action(1); video.seekTo(2000); video.selectSubtitleTrack(-1); next(); break;
                case 12: if (now - stageAt > 800) capture("off"); break;
                case 13: video.selectSubtitleTrack(subtitleTrack); next(); break;
                case 14: if (now - stageAt > 800) capture("restored"); break;
                case 15:
                    before = video.position(); target = before + 10000; action(2); next(); break;
                case 16:
                    if (video.player.isPlaying() && Math.abs(video.player.getTime() - target) < 2000) {
                        sample("playing-forward-10s"); before = video.position(); target = Math.max(0, before - 10000); action(0); next();
                    }
                    break;
                case 17:
                    if (!video.player.isPlaying() || Math.abs(video.player.getTime() - target) >= 2000) break;
                    sample("playing-backward-10s");
                    require(isInPictureInPictureMode(), "PiP stopped during the checks");
                    result(null); return;
            }
            handler.postDelayed(this::tick, 100);
        } catch (Throwable error) { result(error); }
    }
    private void result(Throwable error) {
        if (completed) return;
        completed = true;
        try {
            JSONObject report = new JSONObject().put("success", error == null).put("stage", stage).put("samples", samples)
                .put("playAttempts", playAttempts);
            if (video != null) report.put("nativeState", video.player.getPlayerState()).put("clock", video.player.getTime())
                .put("playing", video.player.isPlaying()).put("surfaceAttached", video.player.getVLCVout().areViewsAttached())
                .put("surfaceWidth", video.video.getWidth()).put("surfaceHeight", video.video.getHeight());
            if (error != null) report.put("error", android.util.Log.getStackTraceString(error));
            if (video != null) {
                video.dispose();
                if (video.root.getParent() != null)
                    report.put("success", false).put("error", "Retirement retained the video root");
            }
            Files.write(file("video-pip-result.json").toPath(), report.toString().getBytes());
        } catch (Exception failure) { android.util.Log.e("VideoPipQA", "Report failed", failure); }
    }
    @Override protected void onStop() { super.onStop(); if (video != null && !completed) video.background(); }
    @Override protected void onDestroy() {
        completed = true;
        handler.removeCallbacksAndMessages(null);
        if (video != null) { video.dispose(); video = null; }
        super.onDestroy();
    }
}
