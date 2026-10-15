package io.github.ispaure.logistics.books;

import android.speech.tts.UtteranceProgressListener;

/** Speech events carry only opaque generation IDs; never book text or paths. */
public final class BookSpeechListener extends UtteranceProgressListener {
    public interface Listener {
        void completed(String token);
        void failed(String token);
    }
    private volatile Listener listener;
    public BookSpeechListener(Listener value) { listener = value; }
    public void detach() { listener = null; }
    @Override public void onStart(String token) { }
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
