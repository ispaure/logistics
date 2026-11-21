// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package io.github.ispaure.logistics.video;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import org.json.JSONArray;
import org.json.JSONObject;
import org.videolan.libvlc.MediaPlayer;
import org.videolan.libvlc.interfaces.IMedia;
import java.io.File;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;

/** Production VideoPlayer playing synthetic Matroska fixtures. */
public final class VideoAudioTailQAActivity extends Activity {
    private enum BackgroundPhase { STARTUP, PAUSED, FOREGROUND_PLAY, SWITCH_PAUSE, SETTINGS, RETURN_PLAY }

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final JSONArray samples = new JSONArray();
    private final String run = Long.toString(SystemClock.elapsedRealtimeNanos());
    private VideoPlayer video;
    private File movie;
    private boolean finished, videoTail, captions;
    private int stage, selectedTrack, originalAudioTrack = -1, audioBeforeSwitch;
    private long started, changed, held;
    private BackgroundPhase backgroundPhase;
    private boolean backgroundStopped, backgroundReturned;
    private int resumedFrames, resumedAudio;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(new FrameLayout(this));
        try {
            videoTail = getIntent().getBooleanExtra("video_tail", false);
            captions = getIntent().getBooleanExtra("captions", false);
            if (getIntent().getBooleanExtra("background_resume", false)) backgroundPhase = BackgroundPhase.STARTUP;
            movie = new File(getCacheDir(), "tail.mkv");
            try (InputStream input = getAssets().open(movie.getName())) {
                Files.copy(input, movie.toPath(), StandardCopyOption.REPLACE_EXISTING);
            }
            boolean control = backgroundPhase != null || getIntent().getBooleanExtra("startup_control", false);
            stage = control ? -1 : 0;
            openPlayer(control);
        } catch (Throwable error) {
            finishWith(error);
        }
    }

    private void openPlayer(boolean control) {
        video = new VideoPlayer(this, Uri.fromFile(movie).toString(), control ? 0 : 18000, false, "[]",
            new VideoPlayer.Listener() {
                public String controlInsets(String value) { return "[0,0,0,0]"; }
                public boolean allowed(boolean external) { return true; }
                public boolean requestPlay() { return true; }
                public void closed() { finish(); }
                public void command(String name, String value) { }
            });
        video.setKnownDuration(backgroundPhase == null ? 12000 : 25000);
        String bounds = videoTail ? "\"video\":[{\"end_ms\":12000}],\"audio\":[{\"end_ms\":3000},{\"end_ms\":3000}]" :
            "\"video\":[{\"end_ms\":4000}],\"audio\":[{\"end_ms\":12000}]";
        if (backgroundPhase == null) {
            video.configurePlayback("{\"video_title\":\"Native video tail QA\",\"media_bounds\":{\"end_ms\":12000," + bounds + "}" +
                (captions ? ",\"subtitle_language\":\"eng\"}" : "}"), "[]");
        } else {
            video.configurePlayback("{\"video_title\":\"Native background resume QA\"}", "[]");
        }
        if (control && backgroundPhase == null) {
            // Match the language used by the post-tail normal input.
            org.videolan.libvlc.Media media = (org.videolan.libvlc.Media) video.player.getMedia();
            try { media.addOption(":audio-track-id=2"); }
            finally { media.release(); }
        }
        if (!control) {
            require(video.position() == 11999 && !video.player.isPlaying(),
                "A stale checkpoint was not clamped when the declared A/V end arrived");
            video.seekTo(6000);
        }
        video.show();
        if (captions) {
            // Sample only an actual video-player window, never its Android splash.
            View marker = new View(this);
            marker.setBackgroundColor(0xffff16e6);
            FrameLayout.LayoutParams box = new FrameLayout.LayoutParams(video.dp(12), video.dp(12),
                Gravity.TOP | Gravity.START);
            box.leftMargin = video.dp(12);
            box.topMargin = video.dp(100);
            video.root.addView(marker, box);
        }
    }

    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (!focused || video == null || finished) return;
        if (backgroundPhase == BackgroundPhase.SETTINGS && backgroundStopped) backgroundReturned = true;
        if (started != 0) return;
        started = changed = SystemClock.uptimeMillis();
        handler.postDelayed(() -> {
            if (finished) return;
            video.startByUser();
            sample();
        }, 500);
    }

    @Override public void onStop() {
        super.onStop();
        if (backgroundPhase != BackgroundPhase.SETTINGS || finished) return;
        video.background();
        backgroundStopped = true;
        try {
            Files.write(new File(getCacheDir(), "background-resume-ready").toPath(),
                "ready".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        } catch (Exception error) {
            finishWith(error);
        }
    }

    private void backgroundPhase(BackgroundPhase phase, long now) {
        backgroundPhase = phase;
        changed = now;
        resumedFrames = -1;
    }

    private void checkBackground(long now, long position, boolean playing, boolean buffering, int frames, int audio) {
        long elapsed = now - changed;
        switch (backgroundPhase) {
            case STARTUP:
                if (!playing || position < 650 || frames < 6 || audio < 10) return;
                held = position;
                video.pause();
                backgroundPhase(BackgroundPhase.PAUSED, now);
                break;
            case PAUSED:
            case SWITCH_PAUSE:
                if (elapsed < 650) return;
                require(!playing && Math.abs(position - held) <= 250, "Pause did not hold its position");
                if (backgroundPhase == BackgroundPhase.PAUSED) {
                    video.startByUser();
                    backgroundPhase(BackgroundPhase.FOREGROUND_PLAY, now);
                } else {
                    backgroundPhase(BackgroundPhase.SETTINGS, now);
                    startActivity(new Intent(Settings.ACTION_SETTINGS));
                }
                break;
            case SETTINGS:
                if (!backgroundReturned) return;
                require(!playing && Math.abs(position - held) <= 250, "Returning to the app changed Pause or position");
                video.startByUser();
                backgroundPhase(BackgroundPhase.RETURN_PLAY, now);
                break;
            case FOREGROUND_PLAY:
            case RETURN_PLAY:
                if (elapsed >= 1150 && resumedFrames < 0) {
                    resumedFrames = frames;
                    resumedAudio = audio;
                }
                if (elapsed < 3300) return;
                require(playing && !buffering && position > held + 1500 &&
                    frames > resumedFrames + 12 && audio > resumedAudio + 30,
                    "Picture and audio stalled after explicit Play in " + backgroundPhase);
                if (backgroundPhase == BackgroundPhase.RETURN_PLAY) {
                    finishWith(null);
                } else {
                    held = position;
                    video.pause();
                    backgroundPhase(BackgroundPhase.SWITCH_PAUSE, now);
                }
                break;
        }
    }

    private boolean spinnerShown(View view, String label) {
        if (label.contentEquals(view.getContentDescription() == null ? "" :
                view.getContentDescription()) && view.isShown()) return true;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup)view;
            for (int i = 0; i < group.getChildCount(); i++)
                if (spinnerShown(group.getChildAt(i), label)) return true;
        }
        return false;
    }

    private void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private void checkTailRecoveryDuringAudioSwitch(long clock) throws ReflectiveOperationException {
        require(video.selectAudioTrack(1, true), "Could not begin the ordinary audio switch");
        require(spinnerShown(video.root, "Switching audio"), "Audio switch did not enter preroll");
        Class<?> tail = Class.forName(VideoPlayer.class.getName() + "$Tail");
        java.lang.reflect.Field videoOnly = tail.getDeclaredField("VIDEO");
        videoOnly.setAccessible(true);
        // Inject the fallback trigger while the live decoder is switching
        // tracks, without depending on a device-specific scheduling stall.
        java.lang.reflect.Method recover = VideoPlayer.class.getDeclaredMethod("recoverTail", long.class, tail);
        recover.setAccessible(true);
        require(!((Boolean) recover.invoke(video, clock, videoOnly.get(null))),
            "Video-only tail recovery replaced an active audio switch");
    }

    private boolean capture(String kind, long clock) throws Exception {
        if (!captions) return true;
        require(video.player.getSpuTrack() >= 0, "No embedded subtitle selected for " + kind);
        if (new File(getCacheDir(), "caption-" + run + "-" + kind + ".done").exists()) return true;
        JSONObject request = new JSONObject().put("kind", kind).put("clock", clock).put("run", run);
        Files.write(new File(getCacheDir(), "caption-request.json").toPath(),
            request.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
        handler.postDelayed(this::sample, 100);
        return false;
    }

    private void selectOtherAudio() {
        int before = video.player.getAudioTrack();
        if (before < 0) before = originalAudioTrack;
        selectedTrack = -1;
        MediaPlayer.TrackDescription[] tracks = video.player.getAudioTracks();
        if (tracks != null) for (MediaPlayer.TrackDescription track : tracks)
            if (track.id >= 0 && track.id != before) { selectedTrack = track.id; break; }
        require(selectedTrack >= 0 && video.selectAudioTrack(selectedTrack, true),
            "The alternative audio language could not be selected");
    }

    private void sample() {
        if (finished) return;
        try {
            long now = SystemClock.uptimeMillis();
            long clock = video.player.getTime(), position = video.position(), progress = video.progressPosition();
            boolean playing = video.player.isPlaying(), spinning = spinnerShown(video.root, "Buffering video");
            boolean switching = spinnerShown(video.root, "Switching audio");
            IMedia media = video.player.getMedia();
            IMedia.Stats stats;
            try { stats = media == null ? null : media.getStats(); }
            finally { if (media != null) media.release(); }
            int frames = stats == null ? 0 : stats.displayedPictures;
            int audio = stats == null ? 0 : stats.playedAbuffers;
            samples.put(new JSONObject().put("stage", stage).put("time", now - started)
                .put("clock", clock).put("position", position).put("progress", progress)
                .put("frames", frames).put("audio", audio).put("playing", playing)
                .put("spinning", spinning).put("switching", switching)
                .put("seekEnabled", video.seek.isEnabled()).put("track", video.player.getAudioTrack())
                .put("subtitle", video.player.getSpuTrack()).put("duration", video.durationMilliseconds())
                .put("backgroundPhase", backgroundPhase == null ? JSONObject.NULL : backgroundPhase.name())
                .put("vlcViewsAttached", video.player.getVLCVout().areViewsAttached()));
            require(now - started < 75000, "Playback or the recovery check timed out at stage " + stage);
            if (backgroundPhase != null) {
                checkBackground(now, position, playing, spinning, frames, audio);
                if (!finished) scheduleSample();
                return;
            }
            if (stage == -1) {
                require(now - started < 20000, "Ordinary startup control produced no picture and audio within 20 seconds");
                if (playing && frames > 0 && audio > 0 && clock > 300) {
                    require(video.player.getVideoTrack() >= 0 && video.player.getAudioTrack() == 2,
                        "Ordinary startup control did not open the matching picture and audio tracks");
                    checkTailRecoveryDuringAudioSwitch(clock);
                    video.dispose();
                    openPlayer(false);
                    video.startByUser();
                    next(now);
                }
            } else if (stage == 0) {
                require(position >= 6000 && !video.completed(), "Saved audio-tail target regressed before readiness");
                long ready = captions ? 7000 : 6500;
                if (playing && progress >= ready && clock >= ready && (videoTail ? frames : audio) > 0) {
                    require(!spinning && video.seek.isEnabled(), "Audio tail appears stalled or unseekable");
                    if (!videoTail) require(video.player.getVideoTrack() < 0, "Audio tail retained the finished video track");
                    if (captions && videoTail) {
                        require(clock < 10500, "Saved-tail caption was not rendered before 10.5 seconds");
                        if (!capture("saved-tail", clock)) return;
                    }
                    if (!videoTail) {
                        audioBeforeSwitch = audio;
                        selectOtherAudio();
                        require(spinnerShown(video.root, "Switching audio"), "Language switch did not show its wait");
                        stage = 10;
                        scheduleSample();
                        return;
                    }
                    held = position;
                    video.pause();
                    next(now);
                }
            } else if (stage == 1 && now - changed > 700) {
                require(!playing && Math.abs(position - held) <= 200, "Pause rewound or resumed the audio tail");
                video.seekTo(0);
                require(video.position() == 0 && !video.player.isPlaying(), "Start over ignored pause or its target");
                next(now);
            } else if (stage == 2 && now - changed > 350) {
                require(!playing && position == 0, "Seeking while paused started playback");
                video.startByUser();
                next(now);
            } else if (stage == 3 && playing && frames > 0 && (!videoTail || audio > 0) && progress > 300) {
                require(progress < 3850, "Start over did not restore the picture and its cue near the beginning");
                require(video.player.getVideoTrack() >= 0,
                    "Start over did not restore the original video track");
                if (!capture("baseline", clock)) return;
                originalAudioTrack = video.player.getAudioTrack();
                video.seekTo(6000);
                require(video.position() == 6000 && video.progressPosition() < 0, "Live seek was accepted before output");
                next(now);
            } else if (stage == 4) {
                require(position >= 6000 && !video.completed(), "Live audio-tail target regressed before readiness");
                long target = videoTail ? 7000 : 8500;
                if (playing && progress >= target && clock >= target && (videoTail ? frames : audio) > 0) {
                    require(!spinning, "Live audio-tail playback remained buffering");
                    if (!videoTail) require(video.player.getVideoTrack() < 0, "Live seek reopened the finished video stream");
                    if (videoTail) {
                        selectOtherAudio();
                        stage = 8;
                    } else {
                        video.seekTo(captions ? 550 : 0);
                        next(now);
                    }
                }
            } else if (stage == 5 && playing && frames > 0 && progress > (captions ? 650 : 300)) {
                require(progress < 3850, "Backseek did not restore the original picture and its spanning cue");
                require(video.player.getVideoTrack() >= 0, "Backseek did not restore the original video track");
                require(video.player.getAudioTrack() == selectedTrack,
                    "Backseek did not restore the selected audio language");
                if (!capture("backseek", clock)) return;
                next(now);
            } else if (stage == 6 && playing && progress >= (captions ? 10200 : 7000) &&
                    clock >= (captions ? 10200 : 7000) &&
                    (videoTail ? frames : audio) > 0) {
                require(!spinning && video.seek.isEnabled(), "Natural video EOF stalled the continuing audio");
                if (!videoTail) require(video.player.getVideoTrack() < 0, "Natural audio continuation is not audio-only");
                if (captions && videoTail) {
                    require(clock < 11600, "Natural tail caption was not rendered before A/V EOF");
                    if (!capture("natural-tail", clock)) return;
                }
                held = position;
                video.pause();
                next(now);
            } else if (stage == 7 && now - changed > 700) {
                require(!playing && Math.abs(position - held) <= 200, "Pause rewound the clock after natural video EOF");
                if (captions) {
                    video.startByUser();
                    stage = 9;
                } else {
                    finishWith(null);
                    return;
                }
            } else if (stage == 8) {
                require(!video.completed(), "Waiting for audio after its EOF outlasted the video");
                if (playing && !switching && !spinning && progress >= 9000 &&
                        frames > 0 && audio == 0 && video.player.getAudioTrack() < 0) {
                    video.seekTo(captions ? 550 : 0);
                    stage = 5;
                }
            } else if (stage == 9) {
                require(clock <= 12500, "Subtitles extended playback past the final A/V sample");
                require(video.durationMilliseconds() == 12000, "Subtitle length extended the displayed duration");
                if (video.completed()) {
                    if (videoTail) {
                        finishWith(null);
                        return;
                    }
                    video.startByUser();
                    require(video.position() == 0 && video.progressPosition() < 0, "Replay did not start from zero");
                    stage = 11;
                }
            } else if (stage == 10) {
                require(clock < 11100 && !video.completed(), "Audio-tail language switch did not complete in time");
                if (playing && !switching && progress >= 0 && audio > audioBeforeSwitch &&
                        video.player.getAudioTrack() == selectedTrack) {
                    require(video.player.getVideoTrack() < 0, "Audio-tail language switch restored the finished picture");
                    held = position;
                    video.pause();
                    changed = now;
                    stage = 1;
                }
            } else if (stage == 11 && playing && frames > 0 && audio > 0 && progress > 300) {
                require(progress < 3850 && video.player.getVideoTrack() >= 0,
                    "Replay did not restore the original picture near the start");
                require(video.player.getAudioTrack() == selectedTrack, "Replay lost the selected audio language");
                if (!capture("replay", clock)) return;
                finishWith(null);
                return;
            }
            scheduleSample();
        } catch (Throwable error) {
            finishWith(error);
        }
    }

    private void scheduleSample() {
        handler.postDelayed(this::sample, 100);
    }

    private void next(long now) {
        stage++;
        changed = now;
    }

    private void finishWith(Throwable error) {
        finished = true;
        if (video != null) video.dispose();
        try {
            JSONObject report = new JSONObject().put("success", error == null).put("samples", samples).put("run", run)
                .put("error", error == null ? "" : error.toString());
            Files.write(new File(getCacheDir(), "audio-tail-result.json").toPath(),
                report.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
        } catch (Exception caught) {
            android.util.Log.e("AudioTailQA", "Could not write test report", caught);
        }
    }

    @Override public void onDestroy() {
        finished = true;
        if (video != null) video.dispose();
        super.onDestroy();
    }
}
