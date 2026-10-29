package io.github.ispaure.logistics.video;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.PictureInPictureParams;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Color;
import android.media.AudioAttributes;
import android.media.AudioDeviceCallback;
import android.media.AudioDeviceInfo;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.accessibility.AccessibilityManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.ScrollView;
import android.widget.PopupMenu;
import org.json.JSONArray;
import org.json.JSONObject;
import org.videolan.libvlc.LibVLC;
import org.videolan.libvlc.Media;
import org.videolan.libvlc.MediaPlayer;
import org.videolan.libvlc.RendererDiscoverer;
import org.videolan.libvlc.RendererItem;
import org.videolan.libvlc.util.VLCVideoLayout;
import java.util.ArrayList;

/** In-process VLC surface. No file intents, storage permissions or plaintext files. */
public final class VideoPlayer {
    public interface Listener {
        String controlInsets(String metrics);
        boolean allowed(boolean external);
        boolean requestPlay();
        void closed();
        void command(String name, String value);
    }

    final Activity activity;
    private final String sourceURL;
    private String transportFailure;
    private boolean playbackFailed, optionsReloadPending;
    Listener listener;
    private final boolean restricted;
    private final LibVLC vlc;
    final MediaPlayer player;
    final FrameLayout root;
    final VLCVideoLayout video;
    final LinearLayout controls;
    private final ScrollView controlsScroll;
    private final LinearLayout videoHeader;
    private final TextView videoTitle, sourceLabel;
    private Boolean chromeShown;
    private LinearLayout buttonGroups, transportButtons, utilityButtons;
    private boolean controlsArranged, controlsWide;
    private final TextView message;
    private final LinearLayout bufferingOverlay;
    private final TextView bufferingLabel;
    private boolean buffering;
    private boolean networkWaiting, networkResumePending, playRequested;
    private long bufferPosition, observedClock = -1, observedFrames, lastPlaybackProgress, lastFrameProgress, lastRenderedClock;
    private final TextView timeLabel;
    final SeekBar seek;
    private final Button play;
    private final Button fullscreenButton;
    boolean fullscreen, controlsVisible = true, wasPip;
    private int previousSystemUi, previousBarBehavior, previousVisibleBars;
    private final Runnable hideControls = new Runnable() {
        @Override public void run() {
            AccessibilityManager accessibility = (AccessibilityManager) activity.getSystemService(Context.ACCESSIBILITY_SERVICE);
            if (fullscreen && attached && !buffering && player.isPlaying() && !seek.isPressed()
                    && (openDialog == null || !openDialog.isShowing()) && !accessibility.isTouchExplorationEnabled())
                setControlsVisible(false);
            else if (fullscreen && attached) scheduleControls();
        }
    };
    final Handler handler = new Handler(Looper.getMainLooper());
    private final JSONArray subtitles;
    private final ArrayList<RendererDiscoverer> discoverers = new ArrayList<>();
    private final ArrayList<RendererItem> renderers = new ArrayList<>();
    private boolean done, ended, attached, casting, wasSecure;
    private long resume, lastPosition;
    private int resumeVolume = 100;
    private boolean audioSuppressed;
    private int previousCapturePolicy = -1;
    private AlertDialog openDialog;
    private PopupMenu optionsMenu;
    private PlaybackControls tools;
    private PausePresentation pausePresentation;
    private final AudioManager audio;
    private AudioFocusRequest focusRequest;
    private boolean focusHeld, manualResumeRequired, pausePending, lockHidden, playbackActive;
    private final AudioManager.OnAudioFocusChangeListener focusListener = change -> {
        if (change != AudioManager.AUDIOFOCUS_GAIN) {
            focusHeld = false;
            pause();
        }
        // Gaining focus never grants permission to auto-resume.
    };
    private final AudioDeviceCallback deviceCallback = new AudioDeviceCallback() {
        @Override public void onAudioDevicesAdded(AudioDeviceInfo[] devices) {
            if (restricted && hasExternalAudio()) pause();
        }
        @Override public void onAudioDevicesRemoved(AudioDeviceInfo[] devices) {
            for (AudioDeviceInfo device : devices) {
                if (device.isSink()) { pause(); break; }
            }
        }
    };

    public VideoPlayer(Activity activity, String url, long start, boolean restricted,
                       String subtitles, Listener listener) {
        this.activity = activity;
        this.sourceURL = url;
        audio = (AudioManager) activity.getSystemService(Context.AUDIO_SERVICE);
        activity.setVolumeControlStream(android.media.AudioManager.STREAM_MUSIC);
        this.listener = listener;
        this.restricted = restricted;
        if (restricted && Build.VERSION.SDK_INT >= 29) {
            previousCapturePolicy = audio.getAllowedCapturePolicy();
            audio.setAllowedCapturePolicy(AudioAttributes.ALLOW_CAPTURE_BY_NONE);
        }
        this.resume = start;
        this.lastPosition = start;
        try { this.subtitles = new JSONArray(subtitles); }
        catch (Exception error) { throw new IllegalArgumentException("Invalid subtitle list", error); }
        ArrayList<String> options = new ArrayList<>();
        options.add("--no-video-title-show");
        options.add("--no-snapshot-preview");
        options.add("--stats");
        options.add("--quiet");
        vlc = new LibVLC(activity, options);
        player = new MediaPlayer(vlc);
        root = new FrameLayout(activity) {
            @Override protected void onMeasure(int widthSpec, int heightSpec) {
                // Choose the rows before children are measured. A change during
                // layout would place stale full-width rows side by side.
                arrangeControls(View.MeasureSpec.getSize(widthSpec));
                super.onMeasure(widthSpec, heightSpec);
            }
        };
        root.setBackgroundColor(Color.BLACK);
        root.setClickable(true);
        video = new VLCVideoLayout(activity);
        root.addView(video, new FrameLayout.LayoutParams(-1, -1));
        View tapSurface = new View(activity);
        tapSurface.setContentDescription("Show or hide video controls");
        tapSurface.setOnClickListener(view -> {
            if (!fullscreen) setFullscreen(true);
            else setControlsVisible(!controlsVisible);
        });
        root.addView(tapSurface, new FrameLayout.LayoutParams(-1, -1));
        bufferingOverlay = new LinearLayout(activity);
        bufferingOverlay.setOrientation(LinearLayout.VERTICAL);
        bufferingOverlay.setGravity(Gravity.CENTER);
        bufferingOverlay.addView(new android.widget.ProgressBar(activity));
        bufferingLabel = new TextView(activity);
        bufferingLabel.setTextColor(Color.WHITE);
        bufferingLabel.setVisibility(View.GONE);
        bufferingOverlay.setContentDescription("Buffering video");
        bufferingOverlay.addView(bufferingLabel);
        bufferingOverlay.setVisibility(View.GONE);
        root.addView(bufferingOverlay, new FrameLayout.LayoutParams(-2, -2, Gravity.CENTER));
        controls = new LinearLayout(activity);
        controls.setOrientation(LinearLayout.VERTICAL);
        controls.setBackgroundColor(0xcc000000);
        controls.setPadding(dp(8), dp(4), dp(8), 0);
        controlsScroll = new ScrollView(activity);
        controlsScroll.setFillViewport(false);
        controlsScroll.setOnTouchListener((view, event) -> {
            if (event.getActionMasked() == android.view.MotionEvent.ACTION_DOWN) handler.removeCallbacks(hideControls);
            if (event.getActionMasked() == android.view.MotionEvent.ACTION_UP
                    || event.getActionMasked() == android.view.MotionEvent.ACTION_CANCEL) scheduleControls();
            return false;
        });
        controlsScroll.addView(controls, new ScrollView.LayoutParams(-1, -2));
        FrameLayout.LayoutParams bottom = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        root.addView(controlsScroll, bottom);
        videoHeader = new LinearLayout(activity);
        videoHeader.setOrientation(LinearLayout.VERTICAL);
        videoHeader.setBackgroundColor(0xa6000000);
        videoHeader.setPadding(dp(12), dp(8), dp(12), dp(8));
        videoTitle = new TextView(activity);
        videoTitle.setTextColor(Color.WHITE);
        videoTitle.setTextSize(18);
        videoTitle.setTypeface(null, android.graphics.Typeface.BOLD);
        videoTitle.setSingleLine(true);
        videoTitle.setEllipsize(android.text.TextUtils.TruncateAt.MIDDLE);
        videoHeader.addView(videoTitle);
        sourceLabel = new TextView(activity);
        sourceLabel.setTextColor(Color.WHITE);
        sourceLabel.setTextSize(12);
        videoHeader.addView(sourceLabel);
        root.addView(videoHeader, new FrameLayout.LayoutParams(-1, -2, Gravity.TOP));
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            FrameLayout.LayoutParams frame = (FrameLayout.LayoutParams) controlsScroll.getLayoutParams();
            int margin = dp(12), extent = dp(48);
            JSONObject layout = tools == null ? null : tools.settings.optJSONObject("reader_layout");
            if (layout != null) { margin = dp(layout.optInt("margin", 12)); extent = dp(layout.optInt("extent", 48)); }
            frame.setMargins(insets.getSystemWindowInsetLeft() + margin, insets.getSystemWindowInsetTop() + margin,
                insets.getSystemWindowInsetRight() + margin, insets.getSystemWindowInsetBottom());
            try {
                JSONObject metrics = new JSONObject();
                metrics.put("width", root.getWidth()); metrics.put("height", root.getHeight());
                metrics.put("safe", new JSONArray(new int[]{insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom()}));
                metrics.put("margin", margin); metrics.put("extent", extent);
                JSONArray corners = new JSONArray();
                if (Build.VERSION.SDK_INT >= 31) {
                    for (int position = 0; position < 4; position++) {
                        android.view.RoundedCorner corner = insets.getRoundedCorner(position);
                        if (corner == null) continue;
                        corners.put(new JSONArray().put(position == 1 || position == 2).put(position >= 2)
                            .put(corner.getCenter().x).put(corner.getCenter().y).put(corner.getRadius()));
                    }
                }
                metrics.put("corners", corners);
                JSONArray fitted = new JSONArray(listener.controlInsets(metrics.toString()));
                frame.setMargins((int)Math.ceil(fitted.getDouble(0)), (int)Math.ceil(fitted.getDouble(1)),
                    (int)Math.ceil(fitted.getDouble(2)), (int)Math.ceil(fitted.getDouble(3)));
            } catch (Exception ignored) { /* System safe insets remain the fallback. */ }
            controlsScroll.setLayoutParams(frame);
            FrameLayout.LayoutParams header = (FrameLayout.LayoutParams) videoHeader.getLayoutParams();
            header.setMargins(frame.leftMargin, frame.topMargin, frame.rightMargin, 0);
            videoHeader.setLayoutParams(header);
            return insets;
        });
        message = new TextView(activity);
        message.setTextColor(Color.WHITE);
        message.setText("Ready. Press Play to start.");
        controls.addView(message);
        timeLabel = new TextView(activity);
        timeLabel.setTextColor(Color.WHITE);
        timeLabel.setText("0:00 / 0:00");
        timeLabel.setContentDescription("Playback time");
        controls.addView(timeLabel);
        seek = new SeekBar(activity);
        seek.setMax(10000);
        seek.setContentDescription("Video position");
        seek.setMinimumHeight(dp(48));
        seek.setProgressTintList(android.content.res.ColorStateList.valueOf(Color.WHITE));
        seek.setProgressBackgroundTintList(android.content.res.ColorStateList.valueOf(0xffaaaaaa));
        seek.setThumbTintList(android.content.res.ColorStateList.valueOf(Color.WHITE));
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onStartTrackingTouch(SeekBar bar) { handler.removeCallbacks(hideControls); }
            public void onProgressChanged(SeekBar bar, int value, boolean user) { }
            public void onStopTrackingTouch(SeekBar bar) {
                seekTo(Math.round(player.getLength() * bar.getProgress() / 10000d));
                scheduleControls();
            }
        });
        // Keep the timeline closest to the bottom edge.

        buttonGroups = new LinearLayout(activity);
        buttonGroups.setBaselineAligned(false);
        controls.addView(buttonGroups, new LinearLayout.LayoutParams(-1, -2));
        transportButtons = new LinearLayout(activity);
        utilityButtons = new LinearLayout(activity);
        buttonGroups.addView(transportButtons);
        buttonGroups.addView(utilityButtons);
        button(transportButtons, "−10s", "Back 10 seconds", () -> seekTo(position() - 10000));
        play = button(transportButtons, "▶", "Play", this::togglePlayback);
        button(transportButtons, "+10s", "Forward 10 seconds", () -> seekTo(position() + 10000));
        button(utilityButtons, "♫", "Audio tracks", () -> tracks(false));
        button(utilityButtons, "CC", "Subtitles", () -> tracks(true));
        button(utilityButtons, "☷", "Chapters", this::chapters);
        fullscreenButton = button(utilityButtons, "⛶", "Fullscreen", () -> setFullscreen(!fullscreen));
        {
            Button more = button(utilityButtons, "⋮", "More playback options", () -> { });
            more.setOnClickListener(view -> {
                PopupMenu menu = optionsMenu = new PopupMenu(activity, more);
                menu.getMenu().add("Show in folder").setOnMenuItemClickListener(item -> { tools.emit("showInFolder", ""); return true; });
                menu.getMenu().add("Playback…").setOnMenuItemClickListener(item -> { tools.show(); return true; });
                if (!restricted) menu.getMenu().add("Picture in picture").setOnMenuItemClickListener(item -> { pip(); return true; });
                if (!restricted) menu.getMenu().add("Cast…").setOnMenuItemClickListener(item -> { cast(); return true; });
                menu.setOnDismissListener(value -> { optionsMenu = null; scheduleControls(); });
                handler.removeCallbacks(hideControls);
                menu.show();
            });
        }
        button(utilityButtons, "×", "Close video player", listener::closed);
        controls.addView(seek);
        arrangeControls(activity.getResources().getDisplayMetrics().widthPixels);
        player.setEventListener(event -> {
            if (done) return;
            if (event.type == MediaPlayer.Event.Stopped && optionsReloadPending) return;
            // Native buffering percentages also describe prefetch while video
            // is flowing. updatePlaybackProgress owns the stall indicator.
            if (event.type == MediaPlayer.Event.Paused || event.type == MediaPlayer.Event.Stopped)
                pausePending = false;
            if (event.type == MediaPlayer.Event.Paused && playRequested && !manualResumeRequired
                    && !networkResumePending && focusHeld && allowed(casting ||
                    (Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode()))) player.play();
            if (event.type == MediaPlayer.Event.Playing) {
                optionsReloadPending = false;
                playbackActive = true;
                if (tools != null) tools.apply();
                ended = false;
                if (manualResumeRequired || !focusHeld || !allowed(false)) { pause(); return; }
                if (resume >= 0) { player.setTime(resume); resume = -1; }
                if ("Ready. Press Play to start.".contentEquals(message.getText())) {
                    message.setText("");
                    message.setVisibility(View.GONE);
                }
                scheduleControls();
            }
            if (event.type == MediaPlayer.Event.EndReached) { ended = true; playRequested = false; lastPosition = 0; setControlsVisible(true); if (tools != null) tools.emit("ended", ""); }
            if (event.type == MediaPlayer.Event.EncounteredError ||
                    (event.type == MediaPlayer.Event.Stopped && playbackActive && playRequested && !ended)) {
                playbackFailed = true;
                long position = Math.max(0, lastPosition);
                pause();
                resume = position;
                status(transportFailure != null ? transportFailure :
                    "Playback stopped unexpectedly. Press Play to retry from this position.");
            }
            if (event.type == MediaPlayer.Event.Playing) updateScreenAwake();
            else if (event.type == MediaPlayer.Event.Paused || event.type == MediaPlayer.Event.Stopped
                    || event.type == MediaPlayer.Event.EndReached || event.type == MediaPlayer.Event.EncounteredError) {
                playbackActive = false;
                if (!networkWaiting) {
                    buffering = false;
                    bufferingOverlay.setVisibility(View.GONE);
                }
                root.setKeepScreenOn(false);
            }
        });
        pausePresentation = new PausePresentation(this);
        tools = new PlaybackControls(this, tapSurface);
        installMedia();
        activity.registerReceiver(screenOff, new IntentFilter(Intent.ACTION_SCREEN_OFF));
        activity.registerReceiver(noisy, new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY));
        audio.registerAudioDeviceCallback(deviceCallback, handler);
        handler.post(tick);
    }

    boolean allowed(boolean external) {
        if (done || (external && restricted) || (restricted && (lockHidden || hasExternalAudio()))) return false;
        if (audio.getMode() == AudioManager.MODE_IN_CALL || audio.getMode() == AudioManager.MODE_IN_COMMUNICATION ||
                audio.getMode() == AudioManager.MODE_RINGTONE) return false;
        PowerManager power = (PowerManager) activity.getSystemService(Context.POWER_SERVICE);
        return power.isInteractive() && listener.allowed(external);
    }

    private boolean hasExternalAudio() {
        for (AudioDeviceInfo device : audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) {
            int type = device.getType();
            if (type == AudioDeviceInfo.TYPE_HDMI || type == AudioDeviceInfo.TYPE_HDMI_ARC ||
                    (Build.VERSION.SDK_INT >= 31 && type == AudioDeviceInfo.TYPE_HDMI_EARC) ||
                    type == AudioDeviceInfo.TYPE_REMOTE_SUBMIX) return true;
        }
        return false;
    }

    int dp(int value) { return Math.round(value * activity.getResources().getDisplayMetrics().density); }

    private void arrangeControls(int width) {
        if (buttonGroups == null) return;
        boolean wide = width >= dp(500);
        if (controlsArranged && controlsWide == wide) return;
        controlsArranged = true;
        controlsWide = wide;
        buttonGroups.setOrientation(wide ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        buttonGroups.setWeightSum(wide ? 3 + utilityButtons.getChildCount() : 0);
        transportButtons.setLayoutParams(new LinearLayout.LayoutParams(wide ? 0 : -1, -2, wide ? 3 : 0));
        utilityButtons.setLayoutParams(new LinearLayout.LayoutParams(wide ? 0 : -1, -2, wide ? utilityButtons.getChildCount() : 0));
    }

    private Button button(LinearLayout row, String text, String label, Runnable action) {
        Button button = new Button(activity);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextSize(16);
        button.setTextColor(Color.WHITE);
        button.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xff303030));
        button.setPadding(dp(4), 0, dp(4), 0);
        button.setMinWidth(dp(48));
        button.setMinimumWidth(dp(48));
        button.setMinHeight(dp(48));
        button.setMinimumHeight(dp(48));
        button.setContentDescription(label);
        if (Build.VERSION.SDK_INT >= 26) button.setTooltipText(label);
        button.setOnClickListener(view -> { action.run(); scheduleControls(); });
        row.addView(button, new LinearLayout.LayoutParams(0, -2, 1));
        return button;
    }

    public void setFullscreen(boolean value) {
        fullscreen = value;
        fullscreenButton.setText(value ? "⤡" : "⛶");
        fullscreenButton.setContentDescription(value ? "Exit fullscreen" : "Fullscreen");
        if (Build.VERSION.SDK_INT >= 26) fullscreenButton.setTooltipText(fullscreenButton.getContentDescription());
        setControlsVisible(!value);
    }

    void setControlsVisible(boolean visible) {
        if (tools != null && tools.locked) visible = false;
        controlsVisible = visible;
        updateChrome();
        scheduleControls();
    }

    private void scheduleControls() {
        handler.removeCallbacks(hideControls);
        boolean pip = Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode();
        if (fullscreen && controlsVisible && attached && player.isPlaying() && !pip)
            handler.postDelayed(hideControls, 3000);
    }

    private void updateChrome() {
        if (!attached) return;
        boolean pip = Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode();
        boolean shown = controlsVisible && !pip;
        boolean immediate = pip || lockHidden || done;
        if (chromeShown == null || chromeShown != shown || immediate) {
            chromeShown = shown;
            fadeChrome(controlsScroll, shown, immediate);
            fadeChrome(videoHeader, shown, immediate);
        }
        View decor = activity.getWindow().getDecorView();
        bufferingOverlay.setVisibility(buffering && !pip && !lockHidden ? View.VISIBLE : View.GONE);
        boolean immersive = fullscreen && !controlsVisible && !pip;
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController controller = decor.getWindowInsetsController();
            if (controller != null) {
                controller.setSystemBarsBehavior(immersive ? WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE : previousBarBehavior);
                if (immersive) controller.hide(WindowInsets.Type.systemBars());
                else {
                    controller.show(previousVisibleBars);
                    controller.hide(WindowInsets.Type.systemBars() & ~previousVisibleBars);
                }
            }
        } else {
            decor.setSystemUiVisibility(immersive ? previousSystemUi | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION : previousSystemUi);
        }
    }

    void setVideoHeader(String title, String label, boolean remote) {
        videoTitle.setText(title);
        sourceLabel.setText(label);
        sourceLabel.setCompoundDrawablesWithIntrinsicBounds(new SourceIcon(remote), null, null, null);
        sourceLabel.setCompoundDrawablePadding(dp(6));
    }

    private final class SourceIcon extends android.graphics.drawable.Drawable {
        final boolean remote;
        final android.graphics.Paint paint = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
        SourceIcon(boolean remote) { this.remote = remote; paint.setColor(Color.WHITE); }
        @Override public int getIntrinsicWidth() { return dp(18); }
        @Override public int getIntrinsicHeight() { return dp(18); }
        @Override public void draw(android.graphics.Canvas canvas) {
            canvas.save();
            canvas.translate(getBounds().left, getBounds().top);
            canvas.scale(getBounds().width() / 24f, getBounds().height() / 24f);
            paint.setStyle(android.graphics.Paint.Style.STROKE); paint.setStrokeWidth(1.6f);
            if (remote) {
                android.graphics.Path path = new android.graphics.Path();
                path.moveTo(6, 19); path.cubicTo(0, 19, 0, 10, 6, 10);
                path.cubicTo(6, 2, 18, 2, 19, 10); path.cubicTo(25, 10, 25, 19, 19, 19);
                path.close(); canvas.drawPath(path, paint);
            } else {
                canvas.drawRoundRect(3, 4, 21, 20, 2, 2, paint);
                canvas.drawLine(3, 14, 21, 14, paint);
                canvas.drawCircle(17, 17, .7f, paint);
            }
            canvas.restore();
        }
        @Override public void setAlpha(int alpha) { paint.setAlpha(alpha); }
        @Override public void setColorFilter(android.graphics.ColorFilter filter) { paint.setColorFilter(filter); }
        @Override public int getOpacity() { return android.graphics.PixelFormat.TRANSLUCENT; }
    }

    private void fadeChrome(View view, boolean shown, boolean immediate) {
        view.animate().cancel();
        view.setImportantForAccessibility(shown ? View.IMPORTANT_FOR_ACCESSIBILITY_AUTO : View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        if (shown) view.setVisibility(View.VISIBLE);
        // System privacy/PiP transitions conceal immediately. Animator duration
        // scale also honors the device's reduced-animation preference.
        view.animate().alpha(shown ? 1f : 0f).setDuration(immediate ? 0 : 200)
            .withEndAction(() -> { if (!shown) view.setVisibility(View.INVISIBLE); }).start();
    }

    private void restoreChrome() {
        handler.removeCallbacks(hideControls);
        View decor = activity.getWindow().getDecorView();
        decor.setSystemUiVisibility(previousSystemUi);
        if (Build.VERSION.SDK_INT >= 30 && decor.getWindowInsetsController() != null) {
            WindowInsetsController controller = decor.getWindowInsetsController();
            controller.setSystemBarsBehavior(previousBarBehavior);
            controller.show(previousVisibleBars);
            controller.hide(WindowInsets.Type.systemBars() & ~previousVisibleBars);
        }
    }

    private final BroadcastReceiver screenOff = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) {
            if (restricted) hide(); else pause(); // Includes receiver and PiP playback.
        }
    };

    private final BroadcastReceiver noisy = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) { pause(); }
    };

    private boolean requestFocus() {
        if (Build.VERSION.SDK_INT >= 26) {
            if (focusRequest == null) focusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MOVIE).build())
                .setWillPauseWhenDucked(true).setOnAudioFocusChangeListener(focusListener, handler).build();
            return audio.requestAudioFocus(focusRequest) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED;
        }
        return audio.requestAudioFocus(focusListener, AudioManager.STREAM_MUSIC,
            AudioManager.AUDIOFOCUS_GAIN) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED;
    }


    void togglePlayback() {
        if (tools != null && tools.locked) return;
        if (playRequested) pause(); else startByUser();
    }
    void toggleMute() {
        if (!allowed(false)) return;
        int volume = audioSuppressed ? resumeVolume : player.getVolume();
        int next = volume == 0 ? 100 : 0;
        if (audioSuppressed) resumeVolume = next; else player.setVolume(next);
        status(next == 0 ? "Muted" : "Sound on");
    }
    void showPlaybackDialog(AlertDialog dialog) {
        if (!allowed(false)) return;
        if (openDialog != null) openDialog.dismiss();
        openDialog = dialog;
        handler.removeCallbacks(hideControls);
        dialog.setOnDismissListener(value -> { if (openDialog == dialog) openDialog = null; scheduleControls(); });
        dialog.show();
    }
    public void configurePlayback(String options, String queue) {
        if (!done) { tools.configure(options, queue); root.requestApplyInsets(); }
    }
    public void showSubtitleBrowser(String json) { if (!done) tools.browser(json); }
    public void showCachedRanges(String json) { if (!done && allowed(false)) tools.cached(json); }
    public void attachSubtitleURL(String url) { if (allowed(false)) player.addSlave(Media.Slave.Type.Subtitle, Uri.parse(url), true); }
    void reloadPlaybackOptions() {
        if (done) return;
        boolean requested = playRequested;
        long position = position();
        optionsReloadPending = true;
        player.stop(); installMedia(); resume = position;
        if (requested && !manualResumeRequired && allowed(false)) startByUser();
    }

    private void installMedia() {
        Media media = new Media(vlc, Uri.parse(sourceURL));
        media.setHWDecoderEnabled(true, false);
        media.addOption(":network-caching=3000");
        media.addOption(":file-caching=1500");
        if (tools != null) tools.mediaOptions(media);
        player.setMedia(media);
        media.release();
    }

    public void setTransportFailure(String value) { transportFailure = value; }

    public void seekTo(long target) {
        if (tools != null && tools.locked) return;
        if (tools != null && allowed(false)) tools.rememberSeek(target);
        if (!allowed(false) || !player.isSeekable()) return;
        target = Math.max(0, target);
        if (player.getLength() > 0) target = Math.min(target, player.getLength() - 1);
        ended = false;
        lastPlaybackProgress = lastFrameProgress = android.os.SystemClock.elapsedRealtime();
        lastRenderedClock = target;
        if (networkResumePending) bufferPosition = target;
        resume = player.isPlaying() ? -1 : target;
        player.setTime(target);
    }

    private void chapters() {
        if (!allowed(false)) return;
        handler.removeCallbacks(hideControls);
        MediaPlayer.Chapter[] chapters = player.getChapters(player.getTitle());
        if (chapters == null || chapters.length == 0) {
            openDialog = new AlertDialog.Builder(activity).setTitle("Chapters")
                .setMessage("This video has no embedded chapters.").setPositiveButton("Done", null).create();
        } else {
            String[] labels = new String[chapters.length];
            for (int i = 0; i < chapters.length; i++) {
                String name = chapters[i].name;
                labels[i] = clock(chapters[i].timeOffset) + " · " +
                    (name == null || name.isEmpty() ? "Chapter " + (i + 1) : name);
            }
            openDialog = new AlertDialog.Builder(activity).setTitle("Chapters")
                .setSingleChoiceItems(labels, player.getChapter(), (dialog, index) -> {
                    seekTo(chapters[index].timeOffset);
                    dialog.dismiss();
                }).setNegativeButton("Cancel", null).create();
        }
        openDialog.setOnDismissListener(dialog -> { openDialog = null; scheduleControls(); });
        openDialog.show();
    }

    public void startByUser() {
        if (listener == null || !listener.requestPlay() || !allowed(false) || !requestFocus()) return;
        focusHeld = true;
        if (!allowed(false)) { pause(); return; } // Focus acquisition can change output.
        if (ended) { resume = 0; ended = false; playbackFailed = true; }
        if (playbackFailed) {
            playbackActive = false;
            player.stop();
            installMedia();
            playbackFailed = false;
        }
        transportFailure = null;
        message.setText("");
        message.setVisibility(View.GONE);
        manualResumeRequired = false;
        pausePending = false;
        if (audioSuppressed) { player.setVolume(resumeVolume); audioSuppressed = false; }
        playRequested = true;
        pausePresentation.clear();
        if (resume >= 0 && player.isPlaying()) { player.setTime(resume); resume = -1; }
        lastPlaybackProgress = lastFrameProgress = android.os.SystemClock.elapsedRealtime();
        play.setText("Pause");
        play.setContentDescription("Pause");
        networkResumePending = false;
        player.play();
    }

    public void setNetworkWaiting(boolean waiting) {
        if (done) return;
        networkWaiting = waiting;
        if (!waiting && networkResumePending) {
            networkResumePending = false;
            lastPlaybackProgress = lastFrameProgress = android.os.SystemClock.elapsedRealtime();
            boolean external = casting || (Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode());
            if (playRequested && !manualResumeRequired && focusHeld && allowed(external)) {
                resume = bufferPosition;
                player.setTime(bufferPosition);
                player.play();
            }
        }
    }

    private void updatePlaybackProgress() {
        long now = android.os.SystemClock.elapsedRealtime(), clock = player.getTime(), frames = 0;
        org.videolan.libvlc.interfaces.IMedia media = player.getMedia();
        try {
            if (media != null && media.getStats() != null) frames = media.getStats().displayedPictures;
        } finally { if (media != null) media.release(); }
        boolean progressed = frames != observedFrames || clock != observedClock;
        if (progressed) lastPlaybackProgress = now;
        if (frames != observedFrames || (frames == 0 && clock != observedClock)) {
            lastRenderedClock = clock; lastFrameProgress = now;
        }
        observedFrames = frames;
        observedClock = clock;
        boolean renderStalled = frames > 0 && now - lastFrameProgress >= 6000;
        boolean stalled = playRequested && !manualResumeRequired && !ended &&
            (now - lastPlaybackProgress >= 3000 || (networkWaiting && renderStalled));
        if (stalled && transportFailure != null) {
            String failure = transportFailure;
            playbackFailed = true;
            pause();
            status(failure);
            return;
        }
        if (stalled && networkWaiting && !networkResumePending) {
            bufferPosition = Math.max(0, lastRenderedClock);
            networkResumePending = true;
            if (player.isPlaying()) player.pause();
        }
        boolean changed = buffering != stalled;
        buffering = stalled;
        boolean pip = Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode();
        bufferingOverlay.setVisibility(stalled && !pip && !lockHidden ? View.VISIBLE : View.GONE);
        if (changed) { if (stalled) setControlsVisible(true); else scheduleControls(); }
    }

    private void updateScreenAwake() {
        boolean pip = Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode();
        root.setKeepScreenOn(attached && !done && !lockHidden && !manualResumeRequired
                && playRequested && !pausePending && !ended && !casting && !pip);
    }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (done) return;
            updatePlaybackProgress();
            updateScreenAwake();
            long time = position(), length = player.getLength();
            if (time >= 0 && !ended) lastPosition = time;
            if (!seek.isPressed() && length > 0) seek.setProgress((int)(time * 10000 / length));
            play.setText(playRequested ? "Pause" : "Play");
            play.setContentDescription(playRequested ? "Pause" : "Play");
            timeLabel.setText(clock(time) + " / " + clock(length) + (tools != null && tools.cacheApproximate ? " · Cache ≈" : ""));
            seek.setContentDescription("Video position: " + timeLabel.getText());
            boolean pip = Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode();
            if (pip != wasPip) { wasPip = pip; setControlsVisible(true); }
            if (!allowed(false)) pause();
            handler.postDelayed(this, 500);
        }
    };

    private String clock(long milliseconds) {
        long seconds = Math.max(0, milliseconds / 1000);
        return String.format(java.util.Locale.ROOT, "%d:%02d:%02d", seconds / 3600, seconds / 60 % 60, seconds % 60);
    }

    private String trackLabel(MediaPlayer.TrackDescription track, boolean text) {
        java.util.LinkedHashSet<String> parts = new java.util.LinkedHashSet<>();
        if (track.name != null && !track.name.trim().isEmpty()) parts.add(track.name);
        org.videolan.libvlc.interfaces.IMedia media = player.getMedia();
        try {
            if (media != null) for (int index = 0; index < media.getTrackCount(); index++) {
                org.videolan.libvlc.interfaces.IMedia.Track info = media.getTrack(index);
                int type = text ? org.videolan.libvlc.interfaces.IMedia.Track.Type.Text
                                : org.videolan.libvlc.interfaces.IMedia.Track.Type.Audio;
                if (info == null || info.id != track.id || info.type != type) continue;
                if (info.language != null && !info.language.isEmpty() && !"und".equals(info.language)) {
                    java.util.Locale language = java.util.Locale.forLanguageTag(info.language.replace('_', '-'));
                    String name = language.getDisplayLanguage(java.util.Locale.getDefault());
                    parts.add(name.isEmpty() ? info.language : name);
                }
                if (info.description != null && !info.description.isEmpty()) parts.add(info.description);
                if (info.codec != null && !info.codec.isEmpty()) parts.add(info.codec);
            }
        } finally {
            if (media != null) media.release();
        }
        return parts.isEmpty() ? "Track " + track.id : android.text.TextUtils.join(" · ", parts);
    }

    private void tracks(boolean subtitlesOnly) {
        if (!allowed(false)) return;
        ArrayList<String> labels = new ArrayList<>();
        ArrayList<Runnable> actions = new ArrayList<>();
        if (subtitlesOnly) { labels.add("Subtitles off"); actions.add(() -> player.setSpuTrack(-1)); }
        MediaPlayer.TrackDescription[] audio = player.getAudioTracks();
        if (!subtitlesOnly && audio != null) for (MediaPlayer.TrackDescription track : audio) {
            labels.add((player.getAudioTrack() == track.id ? "✓ " : "") + trackLabel(track, false)); actions.add(() -> player.setAudioTrack(track.id));
        }
        MediaPlayer.TrackDescription[] text = player.getSpuTracks();
        if (subtitlesOnly && text != null) for (MediaPlayer.TrackDescription track : text) {
            labels.add((player.getSpuTrack() == track.id ? "✓ " : "") + trackLabel(track, true)); actions.add(() -> player.setSpuTrack(track.id));
        }
        for (int index = 0; subtitlesOnly && index < subtitles.length(); index++) {
            final int selected = index;
            labels.add("External: " + subtitles.optJSONObject(index).optString("name"));
            actions.add(() -> player.addSlave(Media.Slave.Type.Subtitle,
                Uri.parse(subtitles.optJSONObject(selected).optString("url")), true));
        }
        openDialog = new AlertDialog.Builder(activity).setTitle(subtitlesOnly ? "Subtitles" : "Audio tracks")
            .setItems(labels.toArray(new String[0]), (dialog, index) -> {
                if (allowed(false)) actions.get(index).run();
            }).setNegativeButton("Cancel", null).create();
        openDialog.show();
    }

    private void pip() {
        if (!allowed(true)) return;
        if (Build.VERSION.SDK_INT >= 26 && activity.getPackageManager().hasSystemFeature("android.software.picture_in_picture")) {
            activity.enterPictureInPictureMode(new PictureInPictureParams.Builder().build());
        } else status("Picture in picture is unavailable on this device.");
    }

    private void cast() {
        if (!allowed(true)) return;
        if (discoverers.isEmpty()) {
            for (RendererDiscoverer.Description description : RendererDiscoverer.list(vlc)) {
                RendererDiscoverer discoverer = new RendererDiscoverer(vlc, description.name);
                discoverer.setEventListener(event -> {
                    if (done) return;
                    if (event.type == RendererDiscoverer.Event.ItemAdded) {
                        event.getItem().retain(); renderers.add(event.getItem());
                    } else if (event.type == RendererDiscoverer.Event.ItemDeleted) {
                        if (renderers.remove(event.getItem())) event.getItem().release();
                    }
                });
                discoverer.start(); discoverers.add(discoverer);
            }
        }
        ArrayList<String> labels = new ArrayList<>();
        ArrayList<RendererItem> choices = new ArrayList<>(renderers);
        for (RendererItem item : choices) item.retain();
        labels.add("This device");
        for (RendererItem item : choices) labels.add(item.name);
        if (renderers.isEmpty()) status("Looking for receivers. Open Cast again in a few seconds.");
        AlertDialog dialog = new AlertDialog.Builder(activity).setTitle("Cast video")
            .setItems(labels.toArray(new String[0]), (selectionDialog, index) -> {
                if (!allowed(true)) return;
                RendererItem selected = index == 0 ? null : choices.get(index - 1);
                if (selected != null && !renderers.contains(selected)) {
                    status("This receiver disconnected. Choose Cast again.");
                    return;
                }
                resume = Math.max(0, player.getTime());
                player.stop();
                player.setRenderer(selected);
                casting = index != 0;
                startByUser();
            }).setNegativeButton("Cancel", null).create();
        dialog.setOnDismissListener(value -> {
            for (RendererItem item : choices) item.release();
        });
        openDialog = dialog;
        dialog.show();
    }

    public void show() {
        if (done || attached) return;
        lockHidden = false;
        FrameLayout decor = (FrameLayout) activity.getWindow().getDecorView();
        previousSystemUi = decor.getSystemUiVisibility();
        if (Build.VERSION.SDK_INT >= 30) previousVisibleBars = WindowInsets.Type.systemBars();
        if (Build.VERSION.SDK_INT >= 30 && decor.getRootWindowInsets() != null && decor.getWindowInsetsController() != null) {
            previousBarBehavior = decor.getWindowInsetsController().getSystemBarsBehavior();
            WindowInsets insets = decor.getRootWindowInsets();
            previousVisibleBars = (insets.isVisible(WindowInsets.Type.statusBars()) ? WindowInsets.Type.statusBars() : 0)
                | (insets.isVisible(WindowInsets.Type.navigationBars()) ? WindowInsets.Type.navigationBars() : 0)
                | (insets.isVisible(WindowInsets.Type.captionBar()) ? WindowInsets.Type.captionBar() : 0);
        }
        decor.addView(root, new FrameLayout.LayoutParams(-1, -1));
        attached = true;
        root.requestApplyInsets();
        wasSecure = (activity.getWindow().getAttributes().flags & WindowManager.LayoutParams.FLAG_SECURE) != 0;
        if (restricted) activity.getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        player.attachViews(video, null, true, true);
        setControlsVisible(true);
    }

    public void hide() {
        pausePresentation.clear();
        if (done || lockHidden) return;
        lockHidden = true;
        if (optionsMenu != null) optionsMenu.dismiss();
        if (openDialog != null) { openDialog.dismiss(); openDialog = null; }
        pause();
        resume = position();
        player.stop();  // Retire buffered private frames before the host lock.
        if (attached) {
            restoreChrome();
            player.detachViews();
            ((ViewGroup) root.getParent()).removeView(root);
            attached = false;
            if (restricted && !wasSecure) activity.getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);
        }
    }

    public long position() {
        if (ended) return 0;
        if (networkResumePending) return bufferPosition;
        if (resume >= 0) return resume;
        long value = player.getTime();
        return value >= 0 ? value : lastPosition;
    }
    public boolean completed() { return ended; }
    public void pause() {
        if (done) return;
        if (resume < 0) resume = position();
        pausePresentation.hold();
        root.setKeepScreenOn(false);
        setControlsVisible(true);
        manualResumeRequired = true;
        playRequested = false;
        play.setText("Play");
        play.setContentDescription("Play");
        if (networkResumePending) resume = bufferPosition;
        networkResumePending = false;
        buffering = false;
        bufferingOverlay.setVisibility(View.GONE);
        if (!audioSuppressed) {
            int current = player.getVolume();
            resumeVolume = current >= 0 ? current : 100;
            audioSuppressed = true;
        }
        player.setVolume(0); // Keep unexpected OS/decoder restarts silent until explicit Play.
        if (player.isPlaying() && !pausePending) {
            pausePending = true;
            player.pause(); // Guard and coalesce the native pause; never toggle OS state.
        }
    }
    public void background() {
        pausePresentation.clear();
        root.setKeepScreenOn(false);
        boolean pip = Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode();
        if (restricted) hide(); else if (!pip && !casting) pause();
        pausePresentation.clear();
    }
    public void status(String text) {
        message.setText(text);
        message.setVisibility(text.isEmpty() ? View.GONE : View.VISIBLE);
        setControlsVisible(true);
    }
    public void dispose() {
        pausePresentation.clear();
        if (done) return;
        hide();
        done = true;
        handler.removeCallbacks(tick);
        activity.unregisterReceiver(screenOff);
        activity.unregisterReceiver(noisy);
        audio.unregisterAudioDeviceCallback(deviceCallback);
        if (Build.VERSION.SDK_INT >= 29 && previousCapturePolicy != -1 &&
                audio.getAllowedCapturePolicy() == AudioAttributes.ALLOW_CAPTURE_BY_NONE) {
            audio.setAllowedCapturePolicy(previousCapturePolicy);
        }
        if (Build.VERSION.SDK_INT >= 26 && focusRequest != null) audio.abandonAudioFocusRequest(focusRequest);
        else audio.abandonAudioFocus(focusListener);
        for (RendererDiscoverer discoverer : discoverers) { discoverer.stop(); discoverer.release(); }
        for (RendererItem item : renderers) item.release();
        renderers.clear(); discoverers.clear();
        player.setEventListener(null);
        player.stop(); player.release(); vlc.release();
        listener = null;
        controls.removeAllViews();
    }
}
