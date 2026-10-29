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
        boolean allowed(boolean external);
        boolean requestPlay();
        void closed();
    }

    private final Activity activity;
    private Listener listener;
    private final boolean restricted;
    private final LibVLC vlc;
    private final MediaPlayer player;
    private final FrameLayout root;
    private final VLCVideoLayout video;
    private final LinearLayout controls;
    private final ScrollView controlsScroll;
    private LinearLayout buttonGroups, transportButtons, utilityButtons;
    private boolean controlsArranged, controlsWide;
    private final TextView message;
    private final TextView timeLabel;
    private final SeekBar seek;
    private final Button play;
    private final Button fullscreenButton;
    private boolean fullscreen, controlsVisible = true, wasPip;
    private int previousSystemUi, previousBarBehavior, previousVisibleBars;
    private final Runnable hideControls = new Runnable() {
        @Override public void run() {
            AccessibilityManager accessibility = (AccessibilityManager) activity.getSystemService(Context.ACCESSIBILITY_SERVICE);
            if (fullscreen && attached && player.isPlaying() && !seek.isPressed()
                    && (openDialog == null || !openDialog.isShowing()) && !accessibility.isTouchExplorationEnabled())
                setControlsVisible(false);
            else if (fullscreen && attached) scheduleControls();
        }
    };
    private final Handler handler = new Handler(Looper.getMainLooper());
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
        options.add("--no-stats");
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
        controls = new LinearLayout(activity);
        controls.setOrientation(LinearLayout.VERTICAL);
        controls.setBackgroundColor(0xcc000000);
        controls.setPadding(dp(8), dp(8), dp(8), dp(8));
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
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            FrameLayout.LayoutParams frame = (FrameLayout.LayoutParams) controlsScroll.getLayoutParams();
            frame.setMargins(insets.getSystemWindowInsetLeft() + dp(8), insets.getSystemWindowInsetTop() + dp(8),
                insets.getSystemWindowInsetRight() + dp(8), insets.getSystemWindowInsetBottom() + dp(8));
            controlsScroll.setLayoutParams(frame);
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
                if (allowed(false)) player.setPosition(bar.getProgress() / 10000f);
                scheduleControls();
            }
        });
        controls.addView(seek);
        buttonGroups = new LinearLayout(activity);
        buttonGroups.setBaselineAligned(false);
        controls.addView(buttonGroups, new LinearLayout.LayoutParams(-1, -2));
        transportButtons = new LinearLayout(activity);
        utilityButtons = new LinearLayout(activity);
        buttonGroups.addView(transportButtons);
        buttonGroups.addView(utilityButtons);
        button(transportButtons, "−10s", "Back 10 seconds", () -> { if (allowed(false)) player.setTime(Math.max(0, player.getTime() - 10000)); });
        play = button(transportButtons, "Play", "Play", () -> {
            if (player.isPlaying()) pause(); else startByUser();
        });
        button(transportButtons, "+10s", "Forward 10 seconds", () -> { if (allowed(false)) player.setTime(player.getTime() + 10000); });
        button(utilityButtons, "CC", "Audio and subtitles", this::tracks);
        fullscreenButton = button(utilityButtons, "⛶", "Fullscreen", () -> setFullscreen(!fullscreen));
        if (!restricted) {
            Button more = button(utilityButtons, "⋮", "More playback options", () -> { });
            more.setOnClickListener(view -> {
                PopupMenu menu = optionsMenu = new PopupMenu(activity, more);
                menu.getMenu().add("Picture in picture").setOnMenuItemClickListener(item -> { pip(); return true; });
                menu.getMenu().add("Cast…").setOnMenuItemClickListener(item -> { cast(); return true; });
                menu.setOnDismissListener(value -> { optionsMenu = null; scheduleControls(); });
                handler.removeCallbacks(hideControls);
                menu.show();
            });
        }
        button(utilityButtons, "×", "Close video player", listener::closed);
        arrangeControls(activity.getResources().getDisplayMetrics().widthPixels);
        player.setEventListener(event -> {
            if (done) return;
            if (event.type == MediaPlayer.Event.Paused || event.type == MediaPlayer.Event.Stopped)
                pausePending = false;
            if (event.type == MediaPlayer.Event.Playing) {
                playbackActive = true;
                ended = false;
                if (manualResumeRequired || !focusHeld || !allowed(false)) { pause(); return; }
                if (resume > 0) { player.setTime(resume); resume = 0; }
                if ("Ready. Press Play to start.".contentEquals(message.getText())) {
                    message.setText("");
                    message.setVisibility(View.GONE);
                }
                scheduleControls();
            }
            if (event.type == MediaPlayer.Event.EndReached) { ended = true; lastPosition = 0; setControlsVisible(true); }
            if (event.type == MediaPlayer.Event.EncounteredError)
                status("Playback failed. Close and reopen this video to retry.");
            if (event.type == MediaPlayer.Event.Playing) updateScreenAwake();
            else if (event.type == MediaPlayer.Event.Paused || event.type == MediaPlayer.Event.Stopped
                    || event.type == MediaPlayer.Event.EndReached || event.type == MediaPlayer.Event.EncounteredError) {
                playbackActive = false;
                root.setKeepScreenOn(false);
            }
        });
        Media media = new Media(vlc, Uri.parse(url));
        media.addOption(":network-caching=500");
        player.setMedia(media);
        media.release();
        activity.registerReceiver(screenOff, new IntentFilter(Intent.ACTION_SCREEN_OFF));
        activity.registerReceiver(noisy, new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY));
        audio.registerAudioDeviceCallback(deviceCallback, handler);
        handler.post(tick);
    }

    private boolean allowed(boolean external) {
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

    private int dp(int value) { return Math.round(value * activity.getResources().getDisplayMetrics().density); }

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

    private void setControlsVisible(boolean visible) {
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
        controls.setVisibility(pip || !controlsVisible ? View.GONE : View.VISIBLE);
        controlsScroll.setVisibility(controls.getVisibility());
        View decor = activity.getWindow().getDecorView();
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

    private void startByUser() {
        if (listener == null || !listener.requestPlay() || !allowed(false) || !requestFocus()) return;
        focusHeld = true;
        if (!allowed(false)) { pause(); return; } // Focus acquisition can change output.
        manualResumeRequired = false;
        pausePending = false;
        if (audioSuppressed) { player.setVolume(resumeVolume); audioSuppressed = false; }
        player.play();
    }

    private void updateScreenAwake() {
        boolean pip = Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode();
        root.setKeepScreenOn(attached && !done && !lockHidden && !manualResumeRequired
                && playbackActive && !pausePending && !ended && !casting && !pip && player.isPlaying());
    }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (done) return;
            updateScreenAwake();
            long time = player.getTime(), length = player.getLength();
            if (time >= 0 && !ended) lastPosition = time;
            if (!seek.isPressed() && length > 0) seek.setProgress((int)(time * 10000 / length));
            play.setText(player.isPlaying() ? "Pause" : "Play");
            play.setContentDescription(player.isPlaying() ? "Pause" : "Play");
            timeLabel.setText(clock(time) + " / " + clock(length));
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

    private void tracks() {
        if (!allowed(false)) return;
        ArrayList<String> labels = new ArrayList<>();
        ArrayList<Runnable> actions = new ArrayList<>();
        labels.add("Subtitles off"); actions.add(() -> player.setSpuTrack(-1));
        MediaPlayer.TrackDescription[] audio = player.getAudioTracks();
        if (audio != null) for (MediaPlayer.TrackDescription track : audio) {
            labels.add("Audio: " + track.name); actions.add(() -> player.setAudioTrack(track.id));
        }
        MediaPlayer.TrackDescription[] text = player.getSpuTracks();
        if (text != null) for (MediaPlayer.TrackDescription track : text) {
            labels.add("Subtitle: " + track.name); actions.add(() -> player.setSpuTrack(track.id));
        }
        for (int index = 0; index < subtitles.length(); index++) {
            final int selected = index;
            labels.add("External: " + subtitles.optJSONObject(index).optString("name"));
            actions.add(() -> player.addSlave(Media.Slave.Type.Subtitle,
                Uri.parse(subtitles.optJSONObject(selected).optString("url")), true));
        }
        openDialog = new AlertDialog.Builder(activity).setTitle("Audio and subtitles")
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
        player.attachViews(video, null, true, false);
        setControlsVisible(true);
    }

    public void hide() {
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
        if (resume > 0) return resume;
        long value = player.getTime();
        return value >= 0 ? value : lastPosition;
    }
    public boolean completed() { return ended; }
    public void pause() {
        if (done) return;
        root.setKeepScreenOn(false);
        setControlsVisible(true);
        manualResumeRequired = true;
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
        root.setKeepScreenOn(false);
        boolean pip = Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode();
        if (restricted) hide(); else if (!pip && !casting) pause();
    }
    public void status(String text) {
        message.setText(text);
        message.setVisibility(text.isEmpty() ? View.GONE : View.VISIBLE);
        setControlsVisible(true);
    }
    public void dispose() {
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
