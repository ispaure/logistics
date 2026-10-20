package io.github.ispaure.logistics.books;

import io.github.ispaure.commonutils.SpeechListener;

/** Compatibility name for clients of the former feature-owned bridge. */
public final class BookSpeechListener extends SpeechListener {
    public interface Listener extends SpeechListener.Listener {}
    public BookSpeechListener(Listener listener) { super(listener); }
}
