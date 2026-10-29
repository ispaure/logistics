package io.github.ispaure.logistics.books;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.media.*;
import android.media.session.*;
import android.os.*;

/** Process-owned, non-exported speech controls; private sources stay generic. */
public final class SpeechMediaService extends Service {
    public interface Listener { void command(String action); }
    private static volatile Listener listener;
    private static volatile SpeechMediaService instance;
    private static volatile boolean playing;
    private static volatile String timerText = "";
    private static volatile String title = "Read aloud";
    private static volatile long epoch;
    private MediaSession session;
    private AudioManager audio;
    private AudioFocusRequest focus;
    private boolean focused;
    private PowerManager.WakeLock wake;
    private static final String CHANNEL = "logistics-read-aloud";
    private static final int NOTICE = 8715;

    public static synchronized void attach(Context context, Listener value) {
        epoch++; playing = true; timerText = ""; title = "Read aloud"; listener = value;
        Intent intent = new Intent(context, SpeechMediaService.class);
        if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent);
        else context.startService(intent);
    }
    public static void update(Context context, boolean value, String timer) {
        playing = value; timerText = timer;
        SpeechMediaService service = instance;
        if (service != null) service.render();
    }
    public static void updateTimer(Context context, String timer) {
        timerText = timer;
        SpeechMediaService service = instance;
        if (service != null) service.publish(false);
    }
    public static void updateContent(Context context, String name) {
        title = name;
        SpeechMediaService service = instance;
        if (service != null) service.publish(false);
    }
    public static synchronized void detach(Context context, Listener value) {
        if (listener != value) return;
        epoch++; playing = false; timerText = ""; title = "Read aloud"; listener = null;
        context.stopService(new Intent(context, SpeechMediaService.class));
        SpeechMediaService service = instance;
        if (service != null) service.cleanup();
    }
    private void dispatch(String action) {
        Listener value = listener;
        if (value != null) value.command(action);
    }
    @Override public void onCreate() {
        super.onCreate(); instance = this;
        audio = (AudioManager)getSystemService(AUDIO_SERVICE);
        wake = ((PowerManager)getSystemService(POWER_SERVICE)).newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK, getPackageName() + ":speech");
        wake.setReferenceCounted(false);
        if (Build.VERSION.SDK_INT >= 26) {
            ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(
                new NotificationChannel(CHANNEL, "Read aloud", NotificationManager.IMPORTANCE_LOW));
            focus = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setOnAudioFocusChangeListener(change -> {
                    if (change < 0) { focused = false; dispatch("interrupt"); }
                }).build();
        }
        session = new MediaSession(this, "LogisticsReadAloud");
        session.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS | MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);
        session.setPlaybackToLocal(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());
        Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (launch != null) session.setSessionActivity(PendingIntent.getActivity(this, 0, launch,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        final Listener controls = listener;
        session.setCallback(new MediaSession.Callback() {
            private void send(String action) {
                if (controls != null && listener == controls) controls.command(action);
            }
            @Override public void onPlay() { send("play"); }
            @Override public void onPause() { send("pause"); }
            @Override public void onStop() { send("stop"); }
            @Override public void onRewind() { send("back"); }
            @Override public void onFastForward() { send("forward"); }
            @Override public void onSkipToNext() { send("forward"); }
            @Override public void onSkipToPrevious() { send("back"); }
            @Override public void onCustomAction(String action, Bundle extras) {
                if ("back15".equals(action)) send("back");
                else if ("forward15".equals(action)) send("forward");
            }
        });
        session.setActive(true);
        // A short passage can detach before Android delivers onCreate. Fulfil
        // startForegroundService even then, before focus or listener dispatch.
        // onStartCommand will retire an ownerless service normally.
        publish(true);
    }
    private PendingIntent action(String action, int code) {
        Intent intent = new Intent(this, SpeechMediaService.class).setAction("speech." + epoch + "." + action)
            .putExtra("command", action).putExtra("epoch", epoch);
        return PendingIntent.getService(this, code, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
    private int skipIcon(String name) {
        return getResources().getIdentifier("speech_" + name, "drawable", getPackageName());
    }
    private void render() {
        if (listener == null || session == null) return;
        if (playing && !focused && Build.VERSION.SDK_INT >= 26) {
            focused = audio.requestAudioFocus(focus) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED;
            if (!focused) { playing = false; dispatch("pause"); }
        }
        if (!playing && focused && Build.VERSION.SDK_INT >= 26) {
            audio.abandonAudioFocusRequest(focus); focused = false;
        }
        if (playing) wake.acquire(15 * 60 * 1000L);
        else if (!playing && wake.isHeld()) wake.release();
        PlaybackState.Builder state = new PlaybackState.Builder()
            .setState(playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED,
                PlaybackState.PLAYBACK_POSITION_UNKNOWN, playing ? 1f : 0f)
            .setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE
                | PlaybackState.ACTION_STOP)
            .addCustomAction("back15", "Back 15 seconds", skipIcon("back15"))
            .addCustomAction("forward15", "Forward 15 seconds", skipIcon("forward15"));
        session.setPlaybackState(state.build());
        publish(true);
    }
    private void publish(boolean foreground) {
        if (session == null) return;
        String subtitle = timerText.isEmpty() ? "Logisticks" : timerText;
        session.setMetadata(new MediaMetadata.Builder()
            .putString(MediaMetadata.METADATA_KEY_TITLE, title)
            .putString(MediaMetadata.METADATA_KEY_DISPLAY_TITLE, title)
            .putString(MediaMetadata.METADATA_KEY_ARTIST, subtitle)
            .putString(MediaMetadata.METADATA_KEY_DISPLAY_SUBTITLE, subtitle).build());
        Notification.Builder notice = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (launch != null) notice.setContentIntent(PendingIntent.getActivity(this, 0, launch,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        Notification notification = notice.setContentTitle(title).setContentText(subtitle)
            .setSmallIcon(android.R.drawable.ic_media_play).setVisibility(Notification.VISIBILITY_PUBLIC)
            .setOnlyAlertOnce(true).setOngoing(playing)
            .addAction(skipIcon("back15"), "Back 15 seconds", action("back", 1))
            .addAction(playing ? android.R.drawable.ic_media_pause : android.R.drawable.ic_media_play,
                playing ? "Pause" : "Play", action(playing ? "pause" : "play", 2))
            .addAction(skipIcon("forward15"), "Forward 15 seconds", action("forward", 3))
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", action("stop", 4))
            .setStyle(new Notification.MediaStyle().setMediaSession(session.getSessionToken()).setShowActionsInCompactView(0, 1, 2)).build();
        if (!foreground) ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).notify(NOTICE, notification);
        else if (Build.VERSION.SDK_INT >= 29) startForeground(NOTICE, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        else startForeground(NOTICE, notification);
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (listener == null) { stopSelf(); return START_NOT_STICKY; }
        if (intent != null && intent.hasExtra("command")) {
            if (intent.getLongExtra("epoch", -1) == epoch) dispatch(intent.getStringExtra("command"));
        } else render();
        return START_NOT_STICKY;
    }
    private void cleanup() {
        if (session != null) { session.setActive(false); session.release(); session = null; }
        if (wake != null && wake.isHeld()) wake.release();
        if (focused && Build.VERSION.SDK_INT >= 26) audio.abandonAudioFocusRequest(focus);
        focused = false;
        stopForeground(true);
    }
    @Override public void onDestroy() { cleanup(); if (instance == this) instance = null; super.onDestroy(); }
    @Override public void onTaskRemoved(Intent rootIntent) { dispatch("stop"); cleanup(); stopSelf(); }
    @Override public IBinder onBind(Intent intent) { return null; }
}
