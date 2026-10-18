package io.github.ispaure.logistics.books;

import android.speech.tts.UtteranceProgressListener;

/** Speech events carry only opaque generation IDs; never book text or paths. */
public final class BookSpeechListener extends UtteranceProgressListener {
    public interface Listener {
        void started(String token);
        void progress(String token, int start, int end);
        void completed(String token);
        void failed(String token);
    }
    private volatile Listener listener;
    public BookSpeechListener(Listener value) { listener = value; }
    public void detach() { listener = null; }
    @Override public void onStart(String token) {
        Listener value = listener;
        if (value != null) value.started(token);
    }
    @Override public void onRangeStart(String token, int start, int end, int frame) {
        Listener value = listener;
        if (value != null) value.progress(token, start, end);
    }
    @Override public void onDone(String token) {
        Listener value = listener;
        if (value != null) value.completed(token);
    }
    @Override public void onError(String token) {
        Listener value = listener;
        if (value != null) value.failed(token);
    }
    @Override public void onError(String token, int errorCode) { onError(token); }
}
