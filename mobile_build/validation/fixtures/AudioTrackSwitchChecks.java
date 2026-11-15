package io.github.ispaure.logistics.video;

/** Run with the production AudioTrackSwitch class on the host JVM. */
final class AudioTrackSwitchChecks {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        AudioTrackSwitch newest = new AudioTrackSwitch(2);
        newest.seek(5000);
        newest.playing(true, 200);

        newest.selected(1);
        newest.buffering(0, 22);
        newest.buffering(100, 22);
        newest.timeChanged(5000);
        check(!newest.ready(2, 23, true), "An earlier selection finished the latest switch");

        newest.selected(2);
        newest.buffering(100, 22);
        newest.timeChanged(5000);
        check(!newest.ready(2, 23, true), "Completion without a new seek reset was accepted");

        newest.buffering(0, 22);
        newest.buffering(100, 23);
        check(!newest.ready(2, 24, true), "The cache filled before decoder readiness");
        newest.timeChanged(5060);
        check(!newest.ready(2, 23, true), "The old audio count was accepted");
        check(!newest.ready(1, 24, true), "The previously selected audio was accepted");
        check(newest.ready(2, 24, true), "A selected track with fresh audio did not become ready");

        newest.seek(17000);
        newest.buffering(0, 24);
        newest.buffering(100, 24);
        newest.timeChanged(5100);
        check(!newest.ready(2, 25, true), "A prior seek's clock completed the replacement seek");
        newest.timeChanged(17000);
        check(newest.ready(2, 25, true), "The replacement seek did not become ready");

        newest.playing(false, 700);
        check(!newest.expired(50000), "A paused switch can expire before the user resumes");
        newest.playing(true, 50000);
        check(!newest.expired(50001) && newest.expired(70001), "Playback must have a bounded wait");
        // Native A is still selected when B is requested, then the user
        // immediately requests A again. The latest choice is queued, so an
        // entire old A cycle cannot be reinterpreted as A's new seek.
        AudioTrackSwitch inFlight = new AudioTrackSwitch(2);
        inFlight.seek(5000);
        inFlight.selected(1);
        inFlight.request(1, 5000);
        inFlight.buffering(0, 40);
        inFlight.buffering(100, 40);
        inFlight.timeChanged(5000);
        check(!inFlight.ready(1, 41, true), "A full stale cycle completed the queued A replacement");
        check(inFlight.track == 2 && inFlight.requestedTrack() == 1 && inFlight.hasReplacement(),
            "A replacement overwrote the native operation before its events drained");
        inFlight.request(3, 9000);
        check(inFlight.requestedTrack() == 3 && inFlight.requestedPosition() == 9000,
            "Only the latest replacement should survive");
        inFlight.selected(2);
        inFlight.buffering(0, 41);
        inFlight.buffering(100, 42);
        inFlight.timeChanged(5000);
        check(inFlight.ready(2, 43, true), "The original operation did not drain");
        AudioTrackSwitch replacement = new AudioTrackSwitch(inFlight.requestedTrack());
        replacement.seek(inFlight.requestedPosition());
        replacement.selected(3);
        replacement.buffering(100, 43);
        replacement.timeChanged(9000);
        check(!replacement.ready(3, 44, true), "Trailing old completion released a new operation");
        replacement.buffering(0, 44);
        replacement.buffering(100, 45);
        replacement.timeChanged(9000);
        check(replacement.ready(3, 46, true), "The latest operation never became ready");
        System.out.println("Android audio switch: event order, replacement seek, output readiness and timeout passed.");
    }
}
