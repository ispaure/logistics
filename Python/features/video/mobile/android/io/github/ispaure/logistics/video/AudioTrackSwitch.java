package io.github.ispaure.logistics.video;

/** Tracks the native events for one audio selection and seek. */
final class AudioTrackSwitch {
    private static final long TIMEOUT_MS = 20000;
    private static final long SEEK_TOLERANCE_MS = 2000;
    private enum Stage { SEEK, BUFFERING, DECODING }

    final int track;
    long position;
    private boolean selected, clockReady;
    private Stage stage = Stage.SEEK;
    private long audioAtPreroll;
    private long deadline = -1;
    private Integer nextTrack;
    private long nextPosition;

    void request(int targetTrack, long targetPosition) {
        nextTrack = targetTrack;
        nextPosition = targetPosition;
    }

    int requestedTrack() { return nextTrack == null ? track : nextTrack; }
    long requestedPosition() { return nextTrack == null ? position : nextPosition; }
    boolean hasReplacement() { return nextTrack != null; }

    AudioTrackSwitch(int track) {
        this.track = track;
    }

    void seek(long target) {
        position = target;
        stage = Stage.SEEK;
        clockReady = false;
    }

    void selected(int actual) {
        selected = actual == track;
        if (!selected) seek(position);
    }

    void buffering(float percent, long playedAudioBuffers) {
        if (!selected) return;
        if (percent == 0f) {
            stage = Stage.BUFFERING;
            clockReady = false;
        } else if (percent >= 100f && stage == Stage.BUFFERING) {
            stage = Stage.DECODING;
            audioAtPreroll = playedAudioBuffers;
        }
    }

    void timeChanged(long time) {
        if (stage == Stage.DECODING && time >= 0 && Math.abs(time - position) <= SEEK_TOLERANCE_MS)
            clockReady = true;
    }

    boolean ready(int actualTrack, long playedAudioBuffers, boolean renderedLocally) {
        // LibVLC announces 100% before waiting on the decoders. The subsequent
        // clock event follows that wait. Local playback also needs fresh audio.
        return selected && actualTrack == track && clockReady &&
            (!renderedLocally || playedAudioBuffers > audioAtPreroll);
    }

    void playing(boolean playing, long now) {
        if (!playing) deadline = -1;
        else if (deadline < 0) deadline = now + TIMEOUT_MS;
    }

    boolean expired(long now) {
        return deadline >= 0 && now >= deadline;
    }
}
