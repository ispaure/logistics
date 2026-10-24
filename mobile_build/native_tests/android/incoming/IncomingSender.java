package io.github.ispaure.logisticsincomingsender;

import android.app.Activity;
import android.content.*;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.*;
import android.provider.OpenableColumns;
import java.io.*;
import java.util.ArrayList;

/** Disposable cross-app content-URI sender for the receiving acceptance checks. */
public class IncomingSender extends Activity {
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        String target = getIntent().getStringExtra("target");
        if (target == null) target = "io.github.ispaure.logisticsinboxqa";
        int count = getIntent().getIntExtra("count", 1);
        boolean hostile = getIntent().getBooleanExtra("hostile", false);
        boolean slow = getIntent().getBooleanExtra("slow", false);
        ArrayList<Uri> uris = new ArrayList<>();
        for (int i = 0; i < count; i++) uris.add(Uri.parse("content://io.github.ispaure.logisticsincomingsender.files/" + (hostile ? "hostile" : slow ? "slow" : i)));
        Intent outgoing = new Intent(count == 1 ? Intent.ACTION_SEND : Intent.ACTION_SEND_MULTIPLE);
        outgoing.setType("application/octet-stream");
        outgoing.setComponent(new ComponentName(target, "io.github.ispaure.logisticsmobile.ReceiveActivity"));
        outgoing.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        if (count == 1) outgoing.putExtra(Intent.EXTRA_STREAM, uris.get(0));
        else outgoing.putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris);
        ClipData clip = ClipData.newRawUri("Synthetic incoming files", uris.get(0));
        for (int i = 1; i < uris.size(); i++) clip.addItem(new ClipData.Item(uris.get(i)));
        outgoing.setClipData(clip);
        startActivity(outgoing);
        finish();
    }

    public static class Files extends ContentProvider {
        @Override public boolean onCreate() { return true; }
        @Override public String getType(Uri uri) { return "application/octet-stream"; }
        @Override public Cursor query(Uri uri, String[] projection, String s, String[] a, String order) {
            MatrixCursor cursor = new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME});
            cursor.addRow(new Object[]{uri.getLastPathSegment().equals("hostile") ? "../escape.txt" : "Inbox fixture " + uri.getLastPathSegment() + ".txt"});
            return cursor;
        }
        @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
            if (uri.getLastPathSegment().equals("slow")) {
                try {
                    ParcelFileDescriptor[] pipe = ParcelFileDescriptor.createPipe();
                    new Thread(() -> {
                        try (OutputStream output = new ParcelFileDescriptor.AutoCloseOutputStream(pipe[1])) {
                            byte[] block = new byte[256 * 1024];
                            for (int i = 0; i < 256; i++) { output.write(block); Thread.sleep(25); }
                        } catch (IOException | InterruptedException expected) { /* Receiver can cancel. */ }
                    }, "Synthetic unknown-length sender").start();
                    return pipe[0];
                } catch (IOException error) { throw new FileNotFoundException("Cannot prepare synthetic pipe"); }
            }
            File file = new File(getContext().getCacheDir(), "synthetic-" + uri.getLastPathSegment());
            try (FileOutputStream output = new FileOutputStream(file)) {
                output.write(("Logistics incoming fixture " + uri.getLastPathSegment() + "\n").getBytes(java.nio.charset.StandardCharsets.UTF_8));
            } catch (IOException error) { throw new FileNotFoundException("Cannot prepare fixture"); }
            return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
        }
        @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
        @Override public int delete(Uri uri, String s, String[] a) { throw new UnsupportedOperationException(); }
        @Override public int update(Uri uri, ContentValues values, String s, String[] a) { throw new UnsupportedOperationException(); }
    }
}
