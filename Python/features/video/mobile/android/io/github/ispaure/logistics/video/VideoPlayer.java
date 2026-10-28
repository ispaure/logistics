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
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;
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
    private final TextView message;
    private final SeekBar seek;
    private final Button play;
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
    private final AudioManager audio;
    private AudioFocusRequest focusRequest;
    private boolean focusHeld, manualResumeRequired, pausePending, lockHidden;
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
        root = new FrameLayout(activity);
        root.setBackgroundColor(Color.BLACK);
        root.setClickable(true);
        video = new VLCVideoLayout(activity);
        root.addView(video, new FrameLayout.LayoutParams(-1, -1));
        controls = new LinearLayout(activity);
        controls.setOrientation(LinearLayout.VERTICAL);
        controls.setBackgroundColor(0xcc000000);
        FrameLayout.LayoutParams bottom = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        root.addView(controls, bottom);
        message = new TextView(activity);
        message.setTextColor(Color.WHITE);
        message.setText("Ready. Press Play to start.");
        controls.addView(message);
        seek = new SeekBar(activity);
        seek.setMax(10000);
        seek.setContentDescription("Video position");
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onStartTrackingTouch(SeekBar bar) { }
            public void onProgressChanged(SeekBar bar, int value, boolean user) { }
            public void onStopTrackingTouch(SeekBar bar) {
                if (allowed(false)) player.setPosition(bar.getProgress() / 10000f);
            }
        });
        controls.addView(seek);
        LinearLayout buttons = new LinearLayout(activity);
        controls.addView(buttons);
        play = button(buttons, "Play", () -> {
            if (!allowed(false)) return;
            if (player.isPlaying()) pause(); else startByUser();
        });
        button(buttons, "−10s", () -> { if (allowed(false)) player.setTime(Math.max(0, player.getTime() - 10000)); });
        button(buttons, "+10s", () -> { if (allowed(false)) player.setTime(player.getTime() + 10000); });
        button(buttons, "Tracks", this::tracks);
        button(buttons, "Done", listener::closed);
        LinearLayout external = new LinearLayout(activity);
        controls.addView(external);
        if (!restricted) {
            button(external, "Picture in picture", this::pip);
            button(external, "Cast…", this::cast);
        }
        player.setEventListener(event -> {
            if (done) return;
            if (event.type == MediaPlayer.Event.Paused || event.type == MediaPlayer.Event.Stopped)
                pausePending = false;
            if (event.type == MediaPlayer.Event.Playing) {
                ended = false;
                if (manualResumeRequired || !focusHeld || !allowed(false)) { pause(); return; }
                if (resume > 0) { player.setTime(resume); resume = 0; }
            }
            if (event.type == MediaPlayer.Event.EndReached) { ended = true; lastPosition = 0; }
            if (event.type == MediaPlayer.Event.EncounteredError)
                status("Playback failed. Close and reopen this video to retry.");
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

    private Button button(LinearLayout row, String text, Runnable action) {
        Button button = new Button(activity);
        button.setText(text);
        button.setOnClickListener(view -> action.run());
        row.addView(button, new LinearLayout.LayoutParams(0, -2, 1));
        return button;
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
        if (!allowed(false) || !requestFocus()) return;
        focusHeld = true;
        manualResumeRequired = false;
        pausePending = false;
        if (audioSuppressed) { player.setVolume(resumeVolume); audioSuppressed = false; }
        player.play();
    }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (done) return;
            long time = player.getTime(), length = player.getLength();
            if (time >= 0 && !ended) lastPosition = time;
            if (!seek.isPressed() && length > 0) seek.setProgress((int)(time * 10000 / length));
            play.setText(player.isPlaying() ? "Pause" : "Play");
            boolean pip = Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode();
            controls.setVisibility(pip ? View.GONE : View.VISIBLE);
            if (!allowed(false)) pause();
            handler.postDelayed(this, 500);
        }
    };

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
        decor.addView(root, new FrameLayout.LayoutParams(-1, -1));
        attached = true;
        wasSecure = (activity.getWindow().getAttributes().flags & WindowManager.LayoutParams.FLAG_SECURE) != 0;
        if (restricted) activity.getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        player.attachViews(video, null, true, false);
    }

    public void hide() {
        if (done || lockHidden) return;
        lockHidden = true;
        if (openDialog != null) { openDialog.dismiss(); openDialog = null; }
        pause();
        resume = position();
        player.stop();  // Retire buffered private frames before the host lock.
        if (attached) {
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
        boolean pip = Build.VERSION.SDK_INT >= 26 && activity.isInPictureInPictureMode();
        if (restricted) hide(); else if (!pip && !casting) pause();
    }
    public void status(String text) { message.setText(text); }
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
