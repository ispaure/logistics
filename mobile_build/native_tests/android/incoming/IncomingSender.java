// TEST_STAGE = TestStage.REGRESSION
package io.github.ispaure.logisticsincomingsender;

import android.app.Activity;
import android.content.ClipData;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Intent;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.provider.OpenableColumns;
import android.util.Log;
import android.widget.TextView;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.Semaphore;

/** Disposable source app for the native Sharesheet and incoming-file acceptance checks. */
public final class IncomingSender extends Activity {
    private static final String AUTHORITY = "io.github.ispaure.logisticsincomingsender.files";
    private static final String MIME = "application/octet-stream";
    private static final String TAG = "LogisticsInboxSender";
    private static final int MAX_BYTES = 256 * 1024;
    private static final int GATE_BYTES = 4096;
    private static final long GATE_MILLIS = 45_000;
    private static final String[][] FIXTURES = {
        {"cold", "SF06 05 Duplicate.txt"},
        {"warm-a", "SF06 02 Warm A.txt"},
        {"warm-b", "SF06 03 Warm B.txt"},
        {"resume", "SF06 04 Resume.txt"},
        {"duplicate-a", "SF06 05 Duplicate.txt"},
        {"duplicate-b", "SF06 05 Duplicate.txt"},
        {"dismiss", "SF06 06 Dismissed.txt"},
        {"cancel-first", "SF06 07 Cancel First.txt"},
        {"cancel-second", "SF06 08 Cancel Second.txt"},
        {"error-first", "SF06 09 Error First.txt"},
        {"error-second", "SF06 10 Error Second.txt"},
        {"leave-first", "SF06 11 Leave First.txt"},
        {"leave-second", "SF06 12 Leave Second.txt"},
        {"death-first", "SF06 13 Death First.txt"},
        {"death-second", "SF06 14 Death Second.txt"},
    };

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        try {
            if (getIntent().getBooleanExtra("seed", false)) {
                seed();
                finish();
                return;
            }
            share();
        } catch (IOException | IllegalArgumentException error) {
            Log.e(TAG, "Fixture action failed", error);
            TextView message = new TextView(this);
            message.setText("Fixture action failed: " + error.getMessage());
            setContentView(message);
        }
    }

    private void seed() throws IOException {
        File root = new File(getFilesDir(), "fixtures");
        for (String[] fixture : FIXTURES) {
            File directory = new File(root, fixture[0]);
            if (!directory.isDirectory() && !directory.mkdirs()) {
                throw new IOException("Cannot make fixture directory");
            }
            String marker = "SendFile06 marker " + fixture[0];
            byte[] contents = (marker + "\nCafé · 雪\n\n").getBytes(StandardCharsets.UTF_8);
            if (fixture[0].endsWith("-second")) {
                byte[] longContents = new byte[128 * 1024];
                for (int i = 0; i < longContents.length; i++) {
                    longContents[i] = (byte) ((i * 31) ^ (i >>> 8));
                }
                System.arraycopy(contents, 0, longContents, 0, contents.length);
                contents = longContents;
            }
            writeOriginal(new File(directory, "name"), fixture[1].getBytes(StandardCharsets.UTF_8));
            writeOriginal(new File(directory, "payload"), contents);
        }
    }

    private static void writeOriginal(File path, byte[] expected) throws IOException {
        if (path.exists()) {
            if (path.length() != expected.length ||
                    !Arrays.equals(Files.readAllBytes(path.toPath()), expected)) {
                throw new IOException("Fixture original changed: " + path.getName());
            }
            return;
        }
        Files.write(path.toPath(), expected, StandardOpenOption.CREATE_NEW);
    }

    private void share() throws IOException {
        String selection = getIntent().getStringExtra("items");
        String token = getIntent().getStringExtra("token");
        String mode = getIntent().getStringExtra("mode");
        if (selection == null || token == null || mode == null || !token.matches("[a-f0-9]{32}")
                || !mode.matches("plain|slow|error")) {
            throw new IllegalArgumentException("Provide fixture items, token and mode");
        }
        String[] ids = selection.split(",", -1);
        if (ids.length > 2 || (ids.length != 2 && !mode.equals("plain"))
                || (ids.length == 2 && ids[0].equals(ids[1]))) {
            throw new IllegalArgumentException("Invalid fixture batch");
        }
        ArrayList<Uri> uris = new ArrayList<>();
        for (int i = 0; i < ids.length; i++) {
            String id = ids[i];
            File directory = fixtureDirectory(getFilesDir(), id);
            payload(directory);
            Uri uri = new Uri.Builder().scheme("content").authority(AUTHORITY)
                    .appendPath(id).appendPath(i == 0 ? "plain" : mode).appendPath(token).build();
            uris.add(uri);
        }
        Intent outgoing = new Intent(ids.length == 1 ? Intent.ACTION_SEND : Intent.ACTION_SEND_MULTIPLE);
        outgoing.setType(MIME);
        outgoing.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        if (ids.length == 1) {
            outgoing.putExtra(Intent.EXTRA_STREAM, uris.get(0));
        } else {
            outgoing.putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris);
        }
        ClipData clip = ClipData.newRawUri("SendFile06 fixtures", uris.get(0));
        for (int i = 1; i < uris.size(); i++) {
            clip.addItem(new ClipData.Item(uris.get(i)));
        }
        outgoing.setClipData(clip);
        startActivity(Intent.createChooser(outgoing, null));
        finish();
    }

    private static File fixtureDirectory(File files, String id) {
        for (String[] fixture : FIXTURES) {
            if (fixture[0].equals(id)) return new File(new File(files, "fixtures"), id);
        }
        throw new IllegalArgumentException("Unknown fixture ID");
    }

    private static File payload(File directory) throws FileNotFoundException {
        File file = new File(directory, "payload");
        if (!file.isFile() || file.length() == 0 || file.length() > MAX_BYTES) {
            throw new FileNotFoundException("Missing or oversized fixture");
        }
        return file;
    }

    public static final class FilesProvider extends ContentProvider {
        private final Semaphore gates = new Semaphore(4);

        @Override public boolean onCreate() { return true; }

        private List<String> parts(Uri uri) {
            List<String> parts = uri.getPathSegments();
            if (!AUTHORITY.equals(uri.getAuthority()) || parts.size() != 3
                    || !parts.get(1).matches("plain|slow|error") || !parts.get(2).matches("[a-f0-9]{32}")) {
                throw new IllegalArgumentException("Invalid fixture URI");
            }
            return parts;
        }

        @Override public String getType(Uri uri) {
            parts(uri);
            return MIME;
        }

        @Override public Cursor query(Uri uri, String[] projection, String selection,
                String[] arguments, String order) {
            List<String> parts = parts(uri);
            File directory = fixtureDirectory(getContext().getFilesDir(), parts.get(0));
            try {
                File original = payload(directory);
                File name = new File(directory, "name");
                if (!name.isFile() || name.length() < 1 || name.length() > 240) {
                    throw new FileNotFoundException("Missing or invalid display name");
                }
                String displayName = new String(Files.readAllBytes(name.toPath()), StandardCharsets.UTF_8);
                String[] columns = projection == null
                        ? new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE} : projection;
                MatrixCursor cursor = new MatrixCursor(columns, 1);
                Object[] row = new Object[columns.length];
                for (int i = 0; i < columns.length; i++) {
                    if (OpenableColumns.DISPLAY_NAME.equals(columns[i])) row[i] = displayName;
                    if (OpenableColumns.SIZE.equals(columns[i]) && parts.get(1).equals("plain")) {
                        row[i] = original.length();
                    }
                }
                cursor.addRow(row);
                return cursor;
            } catch (IOException error) {
                throw new IllegalArgumentException("Fixture metadata is unavailable", error);
            }
        }

        @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
            if (!mode.equals("r")) throw new FileNotFoundException("Fixture streams are read-only");
            List<String> parts = parts(uri);
            File original = payload(fixtureDirectory(getContext().getFilesDir(), parts.get(0)));
            if (parts.get(1).equals("plain")) {
                return ParcelFileDescriptor.open(original, ParcelFileDescriptor.MODE_READ_ONLY);
            }
            if (!gates.tryAcquire()) throw new FileNotFoundException("Too many gated streams");
            try {
                ParcelFileDescriptor[] pipe = ParcelFileDescriptor.createReliablePipe();
                File gate = new File(new File(getContext().getFilesDir(), "gates"), parts.get(2));
                new Thread(() -> stream(original, gate, parts.get(1), pipe[1]),
                        "SendFile06-" + parts.get(0)).start();
                return pipe[0];
            } catch (IOException error) {
                gates.release();
                throw new FileNotFoundException("Cannot prepare fixture pipe: " + error);
            }
        }

        private void stream(File original, File gate, String mode, ParcelFileDescriptor writer) {
            String token = gate.getName();
            try (FileInputStream input = new FileInputStream(original)) {
                FileOutputStream output = new FileOutputStream(writer.getFileDescriptor());
                byte[] block = new byte[GATE_BYTES];
                int first = input.read(block);
                if (first <= 0) throw new IOException("Missing gated prefix");
                output.write(block, 0, first);
                Log.i(TAG, "prefix " + token + " " + first);
                long deadline = SystemClock.elapsedRealtime() + GATE_MILLIS;
                while (!gate.isFile() && SystemClock.elapsedRealtime() < deadline) {
                    Thread.sleep(25);
                }
                if (!gate.isFile()) throw new IOException("Timed out waiting for fixture gate");
                if (mode.equals("error")) {
                    writer.closeWithError("SendFile06 injected source read error");
                    Log.i(TAG, "source-error " + token);
                    return;
                }
                for (int count; (count = input.read(block)) != -1;) {
                    output.write(block, 0, count);
                }
                writer.close();
                Log.i(TAG, "complete " + token);
            } catch (IOException | InterruptedException error) {
                try {
                    writer.closeWithError("SendFile06 stream terminated: " + error.getMessage());
                } catch (IOException closed) {
                    Log.i(TAG, "reader-closed " + token);
                }
                Log.i(TAG, "stream-ended " + token + " " + error.getMessage());
            } finally {
                gates.release();
            }
        }

        @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
        @Override public int delete(Uri uri, String s, String[] a) { throw new UnsupportedOperationException(); }
        @Override public int update(Uri uri, ContentValues values, String s, String[] a) {
            throw new UnsupportedOperationException();
        }
    }
}
