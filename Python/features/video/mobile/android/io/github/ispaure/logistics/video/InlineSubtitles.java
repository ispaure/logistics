// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package io.github.ispaure.logistics.video;

import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.Build;
import android.os.Handler;
import android.view.PixelCopy;
import android.view.Surface;
import android.view.SurfaceView;
import android.view.View;
import android.widget.ScrollView;
import org.videolan.libvlc.interfaces.IMedia;
import org.videolan.libvlc.MediaPlayer;
import java.util.HashSet;
import java.util.function.BooleanSupplier;

/** Positions the independent VLC subtitle surface without changing its buffer or the video. */
final class InlineSubtitles {
    private static final int MAX_SAMPLE_EDGE = 480;
    private static final int SAMPLE_INTERVAL_MS = 50;

    private final VideoPlayer owner;
    private final Handler handler;
    private final ScrollView deck;
    private final BooleanSupplier inline;
    private final Runnable sample = this::sample;
    private final int surfaceId;
    private final int[] location = new int[2];
    private int[] pixels;
    private SurfaceView shifted;
    private Bitmap bitmap;
    private boolean copying;
    private int generation;
    private final HashSet<Integer> sidecarTextTracks = new HashSet<>();
    private HashSet<Integer> tracksBeforeSidecar;
    private boolean restoringSidecar;

    InlineSubtitles(VideoPlayer owner, Handler handler, ScrollView deck, BooleanSupplier inline) {
        this.owner = owner;
        this.handler = handler;
        this.deck = deck;
        this.inline = inline;
        surfaceId = owner.video.getResources().getIdentifier("surface_subtitles", "id", owner.activity.getPackageName());
    }

    void refresh() {
        handler.removeCallbacks(sample);
        if (!copying) sample();
        else if (!enabled()) reset();
    }

    void reset() {
        generation++;
        handler.removeCallbacks(sample);
        place(null, 0);
        if (!copying) releaseBitmap();
    }

    void inputChanged(boolean restoringSrt) {
        sidecarTextTracks.clear();
        tracksBeforeSidecar = null;
        restoringSidecar = restoringSrt;
        reset();
    }

    void attachedSubtitle(boolean srt, MediaPlayer.TrackDescription[] before) {
        tracksBeforeSidecar = null;
        restoringSidecar = false;
        if (!srt) return;
        tracksBeforeSidecar = new HashSet<>();
        if (before != null)
            for (MediaPlayer.TrackDescription track : before) tracksBeforeSidecar.add(track.id);
    }

    private boolean enabled() {
        return Build.VERSION.SDK_INT >= 26 && deck.getVisibility() == View.VISIBLE && inline.getAsBoolean();
    }

    private void releaseBitmap() {
        if (bitmap != null) bitmap.recycle();
        bitmap = null;
        pixels = null;
    }

    private SurfaceView surface() {
        View view = owner.video.findViewById(surfaceId);
        return view instanceof SurfaceView && view.getVisibility() == View.VISIBLE ? (SurfaceView)view : null;
    }

    private int plainTextTrack() {
        int selected = owner.player.getSpuTrack();
        if (selected < 0) return -1;
        IMedia media = owner.player.getMedia();
        if (media == null) return -1;
        try {
            // The pinned Java SDK returns libvlc's codec descriptions here.
            HashSet<Integer> embedded = restoringSidecar ? new HashSet<>() : null;
            for (int i = 0; i < media.getTrackCount(); i++) {
                IMedia.Track track = media.getTrack(i);
                if (!(track instanceof IMedia.SubtitleTrack)) continue;
                if (track.id == selected)
                    return "Text subtitles with various tags".equals(track.codec) ||
                        "Plain text subtitles".equals(track.codec) ? selected : -1;
                if (embedded != null) embedded.add(track.id);
            }
            // LibVLC's media descriptor can omit slaves. Admit the sole track
            // added by an explicit SRT attachment or restored SRT option.
            if (embedded != null && media.getTrackCount() > 0) rememberSidecarTrack(embedded);
            if (tracksBeforeSidecar != null) rememberSidecarTrack(tracksBeforeSidecar);
            return sidecarTextTracks.contains(selected) ? selected : -1;
        } finally {
            media.release();
        }
    }

    private void rememberSidecarTrack(HashSet<Integer> existing) {
        MediaPlayer.TrackDescription[] tracks = owner.player.getSpuTracks();
        if (tracks == null) return;
        int added = -1;
        for (MediaPlayer.TrackDescription track : tracks) {
            if (track.id < 0 || existing.contains(track.id)) continue;
            if (added >= 0) return;
            added = track.id;
        }
        if (added >= 0) {
            sidecarTextTracks.add(added);
            restoringSidecar = false;
            tracksBeforeSidecar = null;
        }
    }

    private Rect frame(View view) {
        view.getLocationInWindow(location);
        return new Rect(location[0], location[1], location[0] + view.getWidth(), location[1] + view.getHeight());
    }

    private Rect naturalFrame(SurfaceView surface) {
        Rect bounds = frame(surface);
        bounds.offset(0, -Math.round(surface.getTranslationY()));
        return bounds;
    }

    private void place(SurfaceView surface, int clearance) {
        if (shifted != null && (shifted != surface || clearance == 0)) shifted.setTranslationY(0);
        if (clearance > 0) surface.setTranslationY(-clearance);
        shifted = clearance > 0 ? surface : null;
    }

    private void sample() {
        if (!enabled()) { reset(); return; }
        SurfaceView surface = surface();
        Rect bounds = surface == null ? new Rect() : naturalFrame(surface);
        int track = plainTextTrack();
        if (track < 0 || bounds.isEmpty() || !Rect.intersects(bounds, frame(deck))) {
            place(null, 0);
            releaseBitmap();
            handler.postDelayed(sample, SAMPLE_INTERVAL_MS);
            return;
        }
        Surface buffer = surface.getHolder().getSurface();
        if (!buffer.isValid()) {
            place(null, 0);
            handler.postDelayed(sample, SAMPLE_INTERVAL_MS);
            return;
        }
        // Copy only the transparent SPU buffer. PixelCopy uses source
        // coordinates, independent of the SurfaceView's on-screen translation.
        double scale = Math.min(1.0, (double)MAX_SAMPLE_EDGE / Math.max(bounds.width(), bounds.height()));
        int width = Math.max(1, (int)Math.ceil(bounds.width() * scale));
        int height = Math.max(1, (int)Math.ceil(bounds.height() * scale));
        if (bitmap == null || bitmap.getWidth() != width || bitmap.getHeight() != height) {
            releaseBitmap();
            bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
            pixels = new int[width * height];
        }
        int requestGeneration = generation;
        copying = true;
        try {
            PixelCopy.request(buffer, bitmap, result -> {
                copying = false;
                if (!enabled()) { reset(); return; }
                if (requestGeneration == generation && surface == surface() &&
                        bounds.equals(naturalFrame(surface)) && track == plainTextTrack()) {
                    place(surface, result == PixelCopy.SUCCESS ? clearance(bounds, frame(deck)) : 0);
                }
                handler.postDelayed(sample, SAMPLE_INTERVAL_MS);
            }, handler);
        } catch (IllegalArgumentException invalidSurface) {
            copying = false;
            place(null, 0);
            handler.postDelayed(sample, SAMPLE_INTERVAL_MS);
        }
    }

    private int clearance(Rect bounds, Rect controls) {
        int width = bitmap.getWidth(), height = bitmap.getHeight();
        bitmap.getPixels(pixels, 0, width, 0, 0, width, height);
        Rect painted = new Rect(width, height, 0, 0);
        for (int y = 0; y < height; y++) {
            int row = y * width;
            for (int x = 0; x < width; x++) {
                if ((pixels[row + x] >>> 24) == 0) continue;
                painted.left = Math.min(painted.left, x);
                painted.top = Math.min(painted.top, y);
                painted.right = Math.max(painted.right, x + 1);
                painted.bottom = y + 1;
            }
        }
        if (painted.isEmpty()) return 0;
        Rect cue = new Rect(
            bounds.left + (int)Math.floor((double)painted.left * bounds.width() / width),
            bounds.top + (int)Math.floor((double)painted.top * bounds.height() / height),
            bounds.left + (int)Math.ceil((double)painted.right * bounds.width() / width),
            bounds.top + (int)Math.ceil((double)painted.bottom * bounds.height() / height));
        if (!Rect.intersects(cue, controls)) return 0;
        int offset = cue.bottom - controls.top;
        return cue.top - offset >= Math.max(bounds.top, frame(owner.video).top) ? offset : 0;
    }
}
