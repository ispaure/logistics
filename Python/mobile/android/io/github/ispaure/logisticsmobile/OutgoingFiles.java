package io.github.ispaure.logisticsmobile;

import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import androidx.core.content.FileProvider;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.util.List;

/** Read-only, time-limited grants from the app's private outgoing cache. */
public final class OutgoingFiles extends FileProvider {
    private static final long MAX_AGE_MS = 15 * 60 * 1000L;

    public static Intent chooser(Context context, Uri uri, String mime) {
        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType(mime);
        send.putExtra(Intent.EXTRA_STREAM, uri);
        send.setClipData(ClipData.newUri(context.getContentResolver(), "Shared file", uri));
        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);

        Intent selected = new Intent(context, TargetChosen.class);
        // The URI distinguishes simultaneous sends. Only dispatch is needed,
        // so the system does not need to fill in any mutable extras.
        selected.setData(uri);
        PendingIntent receipt = PendingIntent.getBroadcast(context, 0, selected,
            PendingIntent.FLAG_ONE_SHOT | PendingIntent.FLAG_IMMUTABLE);
        return Intent.createChooser(send, null, receipt.getIntentSender());
    }

    private static File stagedFile(Context context, Uri uri) {
        List<String> segments = uri.getPathSegments();
        if (segments.size() != 4 || !"outgoing".equals(segments.get(0))
                || !segments.get(1).matches("share-[a-z0-9_]+")
                || !"payload".equals(segments.get(2))
                || !new File(segments.get(3)).getName().equals(segments.get(3))
                || ".".equals(segments.get(3)) || "..".equals(segments.get(3))) {
            return null;
        }
        File directory = new File(new File(context.getCacheDir(), "OutgoingShares"), segments.get(1));
        return new File(new File(directory, "payload"), segments.get(3));
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        File file = stagedFile(getContext(), uri);
        long modified = file == null ? 0 : file.lastModified();
        if (!"r".equals(mode) || modified == 0 || System.currentTimeMillis() - modified >= MAX_AGE_MS) {
            throw new FileNotFoundException("This shared file is no longer available.");
        }
        return super.openFile(uri, mode);
    }

    public static final class TargetChosen extends BroadcastReceiver {
        @Override
        public void onReceive(Context context, Intent intent) {
            Uri uri = intent.getData();
            File file = uri == null ? null : stagedFile(context, uri);
            if (file != null && file.isFile()) {
                try {
                    new File(file.getParentFile().getParentFile(), ".target-chosen").createNewFile();
                } catch (IOException ignored) {
                    // The open-file grant still has its own expiry.
                }
            }
        }
    }
}
